"""Report confirmation must preserve authentication and session boundaries."""
from pathlib import Path
import subprocess
import unittest


class ReportSessionTest(unittest.TestCase):
    def test_confirmation_resubmission_stops_after_session_change_or_401(self):
        source=(Path(__file__).resolve().parents[1]/'src/app/static/app.js').read_text(encoding='utf-8')
        start=source.index('$("#report-agent-form").addEventListener')
        block=source[start:source.index('$("#monitoring-refresh")',start)]
        script=r'''
const vm=require('node:vm'),assert=require('node:assert/strict');
async function check(statusCode,changeSession) {
  let handler,fetches=0,cleared=0,downloads=0;
  const nodes={};
  const context={reportConversationId:'report',sessionGeneration:1,sessionSubject:'user',
    $:key=>nodes[key]||=( {value:'inventory',files:[],dataset:{},addEventListener(event,fn){handler=fn;}} ),
    FormData:class {append(){} set(){}},
    backendFetch:(...args)=>context.fetch(...args),
    fetch:async()=>{fetches++;return {status:statusCode,ok:false,json:async()=>({detail:{confirmation_required:true}})};},
    confirmReportPlan:async()=>{if(changeSession)context.sessionGeneration++;return {templateChoice:'suggested'};},
    clearExpiredSession(){cleared++;},
    URL:{createObjectURL(){downloads++;}},console};
  vm.runInNewContext(BLOCK,context);
  await handler({preventDefault(){}});
  assert.equal(fetches,1);assert.equal(downloads,0);
  assert.equal(cleared,statusCode===401?1:0);
  if(changeSession)assert.equal(nodes['#report-agent-status'].textContent,'Generating report from authorized sources...');
}
(async()=>{await check(409,true);await check(401,false);})().catch(e=>{console.error(e);process.exitCode=1;});
'''
        script='const BLOCK='+__import__('json').dumps(block)+';\n'+script
        result=subprocess.run(['node','-'],input=script,text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr)
