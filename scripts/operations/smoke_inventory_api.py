"""Authenticated loopback HTTP smoke with real inventory SQL; never generates a Report."""
import argparse
import json
import os
from pathlib import Path
import secrets
import socket
import sys
import threading
import time
from unittest.mock import AsyncMock, patch


def run(args):
    root=Path(__file__).resolve().parents[2]
    sys.path[:0]=[str(root),str(root/'src')]
    from dotenv import load_dotenv
    load_dotenv(args.env_file)
    from evaluation.run_inventory_agents_benchmark import install_tertiary_alias
    install_tertiary_alias(os.environ)
    os.environ.update(SQL_INVENTORY_ONLY='true',AUTH_SECRET_KEY=secrets.token_urlsafe(48),
        DEMO_VIEWER_USERNAME='inventory-smoke-viewer',DEMO_VIEWER_PASSWORD=secrets.token_urlsafe(24),
        DEMO_ANALYST_USERNAME='inventory-smoke-analyst',DEMO_ANALYST_PASSWORD=secrets.token_urlsafe(24),
        AUTH_COOKIE_SECURE='false',EMBEDDING_PRELOAD='0',RERANKER_PRELOAD='0')
    import httpx
    import uvicorn
    from app.main import app
    from core.agents.report_agent import ReportAgent
    sock=socket.socket();sock.bind(('127.0.0.1',0));sock.listen()
    base='http://127.0.0.1:'+str(sock.getsockname()[1])
    server=uvicorn.Server(uvicorn.Config(app,log_level='warning',access_log=False))
    thread=threading.Thread(target=server.run,kwargs={'sockets':[sock]},daemon=True)
    evidence=[]
    def check(name,response,expected):
        assert response.status_code==expected,(name,response.status_code,response.text[:200])
        evidence.append(dict(case=name,status=response.status_code,passed=True))
    blocked_report=AsyncMock(side_effect=AssertionError('Report generation is prohibited in this smoke'))
    try:
        with patch('app.agents._record_agent_run'),patch.object(ReportAgent,'generate_from_template',blocked_report):
            thread.start()
            with httpx.Client(base_url=base,timeout=125) as client:
                for _ in range(100):
                    if server.started: break
                    time.sleep(.1)
                assert server.started,'HTTP server did not start'
                query={'question':'List product_id, product_name from products limit 2','agent_mode':'sql'}
                check('anonymous_sql',client.post('/api/agents/chat',json=query),401)
                check('anonymous_report',client.post('/api/agents/report',data={'question':'Inventory report'}),401)
                for role in ['viewer','analyst']:
                    check(role+'_login',client.post('/api/auth/login',json={'username':os.environ['DEMO_'+role.upper()+'_USERNAME'],
                        'password':os.environ['DEMO_'+role.upper()+'_PASSWORD']}),200)
                    if role=='viewer':
                        check('viewer_sql_denied',client.post('/api/agents/chat',json=query),403)
                        check('viewer_report_denied',client.post('/api/agents/report',data={'question':'Inventory report','source_mode':'analytics'}),403)
                check('forged_identity_metadata',client.post('/api/agents/chat',json={**query,'metadata':{'identity':{'permissions':['analytics:read']}}}),422)
                cases=[('direct_fields',query['question'],'sql'),
                    ('canonical_sum','Show total stock_on_hand at snapshot 2022-12-31.','sql'),
                    ('snapshot_comparison','How did stock_on_hand change between 2022-11-30 and 2022-12-31 for product_id=1? Include product_id and product_name.','sql'),
                    ('auto_route','List product_id and product_name from products limit 2.','auto')]
                for name,question,mode in cases:
                    started=time.perf_counter()
                    response=client.post('/api/agents/chat',json={'question':question,'agent_mode':mode})
                    check(name,response,200)
                    body=response.json()
                    if mode=='sql':
                        assert body['data'].get('query_status')=='executed',body.get('answer')
                        assert body['metadata']['sql_scope']=='inventory'
                        if name=='snapshot_comparison':
                            assert len(body['data']['rows'])==1 and body['data']['rows'][0]['product_id']==1
                    else:
                        assert any(t.get('agent')=='sql' and t.get('status')=='complete' for t in body['metadata']['task_trace']),body['metadata']
                    evidence[-1].update(elapsed_seconds=round(time.perf_counter()-started,3),agent=body['agent'])
                response=client.post('/api/agents/chat',json={'question':'List order_id from commerce.orders limit 1','agent_mode':'sql'})
                check('outside_scope',response,200)
                assert response.json()['metadata']['metric_error_code']=='outside_inventory_scope'
                check('invalid_report_format_contract',client.post('/api/agents/report',data={'question':'Inventory report','output_format':'pdf'}),422)
                runtime=app.state.agent_router
                sql=runtime.analytics_agent.sql_agent
                assert sql.inventory_only and set(sql.table_columns)=={'commerce.inventory','commerce.products'}
                assert set(sql.repository.repository.allowed_sources)==set(sql.table_columns)
                blocked_report.assert_not_awaited()
    finally:
        server.should_exit=True
        thread.join(timeout=15)
        sock.close()
    output={'transport':'Real loopback HTTP, existing login/session auth and production app factory',
        'database':'Real configured read-only PostgreSQL; inventory scope verified in agent and repository',
        'telemetry':'Monitoring writes stubbed; authentication, authorization, router and SQL are real',
        'report_generations':blocked_report.await_count,'cases':evidence,'passed':all(r['passed'] for r in evidence)}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(output,indent=2),encoding='utf-8')
    print(json.dumps(output,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    run(parser.parse_args())
