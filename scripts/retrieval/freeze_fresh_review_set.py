#!/usr/bin/env python3
"""Freeze user-approved fresh labels; offline verification with the existing scorer."""
import argparse
import copy
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
from core.evaluation.evidence_metrics import score_evidence

DRAFT = ROOT / 'artifacts/evaluation/fresh-review-20261020'
PROPOSALS = ROOT / 'artifacts/evaluation/fresh-review-assessment-20261021/evidence-proposals.json'
OUT = ROOT / 'artifacts/evaluation/fresh-reviewed-v1'
CORPUS = ROOT / 'artifacts/evaluation/vietstyle-bilingual-20261019/dense-evidence-benchmark-v1/indexed-corpus.jsonl'
OLD = ROOT / 'artifacts/evaluation/vietstyle-bilingual-20261019/evidence-v3/evidence.json'

# Explicit reviewed answer components; regexes select text, never retrieval results.
SPECS = [
 [('timing','Ghi nhận trước khi xác nhận nhận hàng',r'trước khi xác nhận nhận hàng',r'before confirming receipt'),('photos','Có ảnh chụp',r'ảnh chụp',r'photos'),('report','Có biên bản',r'biên bản',r'incident report')],
 [('sell_through','Sell-through',r'sell-through',r'sell-through'),('remaining_stock','Tồn còn lại',r'tồn còn lại',r'remaining stock'),('return_rate','Tỷ lệ trả hàng',r'return rate',r'return rate')],
 [('reason','Nguyên nhân PO khẩn cấp',r'nguyên nhân',r'reason'),('impact','Ảnh hưởng dịch vụ',r'ảnh hưởng dịch vụ',r'service impact'),('approver','Người phê duyệt PO',r'người phê duyệt',r'approver')],
 [('assessors','Inventory Manager và Finance đánh giá',r'Inventory Manager và Finance',r'Inventory Manager and Finance'),('actions','Đánh giá dự phòng giảm giá trị hoặc loại bỏ theo quy định kế toán',r'dự phòng giảm giá trị / loại bỏ theo quy định kế toán',r'write-downs or disposal under accounting rules')],
 [('snapshots','Tối đa ba snapshot gần nhất có sẵn cho SKU',r'tối đa 3 snapshot gần nhất có sẵn cho SKU',r'(?:up to the three most recent available snapshots for each SKU|up to 3 most recent available snapshots for the SKU)'),('nonconsecutive','Không bắt buộc ba tháng liên tiếp',r'(?:các snapshot không nhất thiết là 3 tháng liên tiếp|Có thể không phải 3 tháng liên tiếp)',r'(?:snapshots are not necessarily consecutive months|These may not be 3 consecutive months)')],
 [('fields','Giữ policy_id, owner, trigger, action, SLA, approval cùng nhau',r'policy_id, owner, trigger, action, SLA và approval cùng nhau',r'policy_id, owner, trigger, action, SLA, and approval together')],
 [('assignment','Warehouse Supervisor phân công người đếm',r'Warehouse Supervisor phân công người đếm',r'Warehouse Supervisor assigns counters'),('blindness','Người đếm không xem lượng hệ thống khi blind count',r'người đếm không được xem số lượng hệ thống nếu tổ chức áp dụng blind count',r'counters must not see system quantities when blind counting is used')],
 [('dimensions','Đếm theo SKU, size, color, vị trí',r'SKU \+ size \+ color \+ vị trí',r'SKU \+ size \+ color \+ location'),('no_merge','Không gộp biến thể gần giống nhau',r'không gộp các biến thể gần giống nhau',r'do not combine similar variants')],
 [('approver','Theo bảng Manual: Warehouse Supervisor duyệt',r'Warehouse Supervisor',r'Warehouse Supervisor'),('deadline','Trong một ngày làm việc',r'Trong 1 ngày làm việc',r'Within 1 business day')],
 [('approvers','QA, Inventory Manager và Finance duyệt',r'QA \+ Inventory Manager \+ Finance',r'QA \+ Inventory Manager \+ Finance'),('authority','Theo thẩm quyền tài chính',r'Theo thẩm quyền tài chính',r'According to financial authority')],
 [('share','Nhóm B là khoảng 15% tiếp theo của giá trị tiêu thụ',r'Nhóm tiếp theo đóng góp xấp xỉ 15%',r'Next group contributing approximately 15%'),('frequency','Kiểm kê hằng tháng',r'Hằng tháng',r'Monthly'),('sla','Điều tra trong hai ngày làm việc',r'Điều tra trong 2 ngày làm việc',r'Investigate within 2 business days')],
 [('hold','Giữ giao dịch liên quan',r'Giữ giao dịch liên quan',r'Hold related transactions'),('investigate','Điều tra nguyên nhân gốc',r'điều tra nguyên nhân gốc',r'investigate the root cause'),('approvers','Theo SOP: Inventory Manager và Finance duyệt',r'Inventory Manager\s*\+\s*Finance',r'Inventory Manager\s*\+\s*Finance')],
]

def read(path): return json.loads(path.read_text(encoding='utf-8'))
def canonical(path): return path.read_bytes().replace(b'\r\n', b'\n')
def sha(data): return hashlib.sha256(data).hexdigest()
def rel(path): return path.relative_to(ROOT).as_posix()
def require(ok, msg):
    if not ok: raise ValueError(msg)
def save(path, obj): path.write_bytes((json.dumps(obj,ensure_ascii=False,indent=2)+'\n').encode())
def source_context():
    rows=[json.loads(l) for l in CORPUS.read_text(encoding='utf-8').splitlines()]
    byid={f"{r['document_id']}::chunk::{r['chunk_index']}":r for r in rows}
    info=read(OLD)['sources']
    sources={lang:{(r['document_id'],r.get('parser_chunk_index',r.get('chunk_index'))):r['content'] for r in [json.loads(l) for l in (ROOT/meta['path']).read_text(encoding='utf-8').splitlines()]} for lang,meta in info.items()}
    return rows,byid,info,sources

def mapped_spans(row,a,b,source):
    """Convert using exact saved mapping, without substring-guessing parser offsets."""
    parts=[]; covered=set()
    for m in row['metadata']['source_spans']:
        c,d=max(a,m['chunk_start']),min(b,m['chunk_end'])
        if c>=d: continue
        x=m['source_start']+c-m['chunk_start']; y=x+d-c
        require(source[x:y]==row['content'][c:d], 'Invalid source mapping')
        parts.append((x,y)); covered.update(range(c,d))
    require(all(i in covered or row['content'][i].isspace() for i in range(a,b)), 'Unmapped evidence characters')
    require(bool(parts),'Empty mapping')
    return parts

def build():
    require(not OUT.exists(),'Frozen output exists; use --verify-only, or a NEW version for changes')
    rows,byid,info,sources=source_context()
    original=read(DRAFT/'cases.json'); cases=copy.deepcopy(original)
    edits={
      'F04':{'vi':'Với SKU có days of supply trên 240 ngày, ai cần đánh giá và xem xét những phương án nào theo quy định kế toán?','en':'For a SKU with more than 240 days of supply, who assesses it and which accounting actions are considered?'},
      'F09':{'vi':'Theo bảng phê duyệt trong Inventory Management Policy Manual, ai duyệt điều chỉnh tồn nhỏ có đủ bằng chứng và thời hạn xử lý là bao lâu?','en':'According to the Inventory Management Policy Manual approval table, who approves a small inventory adjustment with sufficient evidence, and what is the processing deadline?'}}
    cases['dataset_id']='fresh-reviewed-v1'
    for c in cases['cases']:
        if c['intent_id'] in edits:c['question']=edits[c['intent_id']][c['query_language']]
    proposals=read(PROPOSALS)['evidence']; spans={}; intents=[]
    for number,components in enumerate(SPECS,1):
        intent=f'F{number:02}'; group=[c for c in cases['cases'] if c['intent_id']==intent]
        q={'id':intent,'question':{lang:next(c['question'] for c in group if c['query_language']==lang) for lang in ('vi','en')},'category':group[0]['category'],'full_intent_ready':True,'requirements':[]}
        for slug,desc,vi,en in components:
            component={'id':intent+'.'+slug,'description_vi':desc,'required':True,'status':'ready','evidence_by_language':{}}
            for lang,pattern in [('vi',vi),('en',en)]:
                options=[]
                for ai,alt in enumerate(proposals[intent+'-'+lang]['alternatives']):
                    bundle=[]
                    for entry in alt['spans']:
                        row=byid[entry['chunk_id']]; text=row['content']; meta=row['metadata']
                        require(sha(text.encode())==entry['chunk_content_sha256'] and text[entry['start_char']:entry['end_char']]==entry['quote'],'Changed proposal source')
                        matches=list(re.finditer(pattern,entry['quote'],re.I))
                        require(len(matches)==1,f'{intent}/{slug}/{lang}: selector ambiguous or missing')
                        match=matches[0]; a=entry['start_char']+match.start(); b=entry['start_char']+match.end()
                        key=(row['document_id'],meta['source_parser_index']); source=sources[lang][key]
                        require(sha(source.encode())==meta['source_content_sha256'],'Changed parser source')
                        for pi,(x,y) in enumerate(mapped_spans(row,a,b,source)):
                            sid=f'{intent}.{slug}.{lang}.a{ai}.s{pi}'
                            spans[sid]={'id':sid,'language':lang,'document_id':row['document_id'],'document_name':row['document_name'],'source_parser_index':key[1],'source_content_sha256':sha(source.encode()),'start_char':x,'end_char':y,'quote':source[x:y],'location':{k:meta[k] for k in ('page_number','sheet_name','slide_number','table_index') if meta.get(k) is not None},'origin_chunk_id':entry['chunk_id']}
                            bundle.append(sid)
                    options.append({'all_of':bundle})
                component['evidence_by_language'][lang]={'alternatives':options}
            q['requirements'].append(component)
        intents.append(q)
    evidence={'schema_version':1,'dataset_id':'fresh-reviewed-v1','annotation_status':'assistant-prepared and reviewed; user-approved in chat 2026-10-21; not independently human-certified or held-out','offset_basis':'parser-source Unicode characters, converted via indexed chunk source_spans','sources':{lang:{'path':meta['path'],'sha256':sha(canonical(ROOT/meta['path'])),'hash_encoding':'UTF-8 file bytes with CRLF normalized to LF'} for lang,meta in info.items()},'rules':{'evaluation_only':True,'never_index_labels_questions_or_answers':True,'requirements':'AND required components; OR alternative bundles; AND all_of spans. Only selected original anchors earn coverage; extra reranker context does not.','source_unit':'parser-source Unicode coordinates, end exclusive'},'intents':intents,'spans':spans}
    changes={'question_edits':{intent:{lang:{'before':next(c['question'] for c in original['cases'] if c['intent_id']==intent and c['query_language']==lang),'after':question} for lang,question in versions.items()} for intent,versions in edits.items()},'evidence_changes':'Approved proposals: narrowed F06-F08; alternative training deck F02, workbook README F05, extracted SOP table F12; decomposed into 28 required answer components. F09 separation of duties is supported context, not an extra requirement for its approver/deadline question.','source_role_policy':'F09 Manual-scoped; F12 SOP-scoped; no corpus-wide role reconciliation claimed.'}
    OUT.mkdir()
    save(OUT/'cases.json',cases); save(OUT/'evidence.json',evidence); save(OUT/'changes.json',changes)
    (OUT/'.gitattributes').write_bytes(b'* text eol=lf\n')
    review=['# Frozen fresh questions v1','',evidence['annotation_status'],'','Exact source spans per component and alternatives are in evidence.json. AND across components; OR alternatives. Do not index this file.','']
    for q in intents:
        review.extend([f"## {q['id']}",'',q['question']['vi'],'',q['question']['en'],''])
        for c in q['requirements']:
            review.extend([f"### {c['id']} — {c['description_vi']}",''])
            for lang in ('vi','en'):
                for ai,alt in enumerate(c['evidence_by_language'][lang]['alternatives'],1):
                    review.append(f'{lang.upper()} alternative {ai}:')
                    for sid in alt['all_of']:
                        s=spans[sid]; review.extend(['',f"{s['document_name']}, parser {s['source_parser_index']}, [{s['start_char']}, {s['end_char']}):",'', '> '+s['quote'].replace('\n','\n> ')])
                    review.append('')
    (OUT/'REVIEW.md').write_bytes(('\n'.join(review)+'\n').encode())
    (OUT/'README.md').write_bytes(b'''# Frozen fresh-reviewed-v1

12 bilingual paired intents, 24 texts, 48 directional cases; 28 required components per direction. All 12 eligible. Assistant-prepared and reviewed, user-approved in chat on 2026-10-21; no independent held-out claim. Sources remain simulated business documents. F04 and F09 clarifications are recorded in changes.json. Categories and overlapping intents remain as disclosed in the assessment; no workbook numeric-row question was added.

Original draft, assessment, sources, vectors and production code are unchanged. evidence.json uses the existing score_evidence schema and real parser-source offsets, converted through exact source_spans mappings. No guessed offsets or synthetic parser provenance. F02/F05/F12 accept alternative source passages per component. Evidence units contain the answer detail; document/actor/row identity is fixed by its source coordinates. They measure exact annotated component retrieval, not generated-answer correctness or general relevance.

Verify from project root (no model or network required):

    .venv/bin/python scripts/retrieval/freeze_fresh_review_set.py --verify-only --self-check

The command checks frozen hashes, exact quotes, provenance, bilingual cases, positive/empty/component-omission evidence checks and tamper rejection. It does not rewrite frozen files. Build refuses to overwrite this directory. manifest.json hashes canonical LF file bytes; .gitattributes keeps frozen files LF. External JSONL files are hashed after CRLF-to-LF normalization, without changing JSON content strings. The historical laptop draft manifest used CRLF bytes; its historical hashes are preserved.

The legacy validate_vietstyle_evidence.py and experiment loader are hard-coded to Q01-Q20 and are NOT the validator/runner for this fresh set. Reuse score_evidence with sources loaded from evidence.json; the runner adapter, new query embeddings, frozen E5 candidate pools and new reranker inference remain next steps. No retrieval benchmark has run. Never reuse old-question logits for these questions.

Keep this version fixed during comparisons. Corrections require a new version and consistent rescoring of every method. Do not index questions, labels, review notes or answers. No model download, database change, generation evaluation, candidate selection or production integration occurs in this freeze.
''')
    inputs=[DRAFT/'cases.json',DRAFT/'evidence-draft.json',DRAFT/'manifest.json',PROPOSALS,CORPUS]+[ROOT/m['path'] for m in info.values()]
    files={p.name:sha(canonical(p)) for p in OUT.iterdir() if p.is_file()}
    save(OUT/'manifest.json',{'dataset_id':'fresh-reviewed-v1','status':'frozen_user_approved','review_date':'2026-10-21','review_provenance':'Assistant prepared/reviewed; user approved proposals and authorized freeze in chat. Not independently certified.','counts':{'paired_intents':12,'question_texts':24,'directional_cases':48,'required_components':28,'spans':len(spans)},'hash_encoding':'UTF-8 file bytes, CRLF normalized to LF; original content-string hashes remain exact','files':files,'inputs':{rel(p):sha(canonical(p)) for p in inputs},'inference_run':False})

def verify(self_check=False):
    manifest=read(OUT/'manifest.json')
    for name,digest in manifest['files'].items(): require(sha(canonical(OUT/name))==digest,'Changed frozen file: '+name)
    for name,digest in manifest['inputs'].items(): require(sha(canonical(ROOT/name))==digest,'Changed frozen input: '+name)
    data=read(OUT/'evidence.json'); cases=read(OUT/'cases.json')['cases']
    rows,byid,_,sources=source_context()
    def validate_labels(labels):
        used=set()
        for sid,s in labels['spans'].items():
            source=sources[s['language']][s['document_id'],s['source_parser_index']]
            require(sha(source.encode())==s['source_content_sha256'] and source[s['start_char']:s['end_char']]==s['quote'] and bool(s['quote'].strip()),'Invalid label '+sid)
            row=byid[s['origin_chunk_id']]
            require(row['language']==s['language'] and row['metadata']['source_parser_index']==s['source_parser_index'],'Wrong label provenance')
        for q in labels['intents']:
            for c in q['requirements']:
                for lang,v in c['evidence_by_language'].items():
                    require(bool(v['alternatives']),'Empty alternatives')
                    for alt in v['alternatives']:
                        require(bool(alt['all_of']),'Empty bundle')
                        for sid in alt['all_of']:
                            require(labels['spans'][sid]['language']==lang,'Wrong-language reference'); used.add(sid)
        require(used==set(labels['spans']),'Unused span')
    validate_labels(data)
    require(len(cases)==48 and len(data['intents'])==12 and sum(len(q['requirements']) for q in data['intents'])==28,'Bad frozen counts')
    oracle_checks=0; omission_checks=0
    for q in data['intents']:
        group=[c for c in cases if c['intent_id']==q['id']]
        require({c['direction'] for c in group}=={'vi->vi','vi->en','en->vi','en->en'} and len(group)==4,'Bad directions')
        for c in group:require(c['question']==q['question'][c['query_language']] and c['evidence_id']==q['id']+'-'+c['target_language'],'Case mismatch')
        for lang in ('vi','en'):
            eligible=[{'text':r['content'],'metadata':r['metadata']} for r in rows if r['language']==lang]
            yes=score_evidence(data,q['id'],lang,eligible,sources[lang],k=len(eligible))
            no=score_evidence(data,q['id'],lang,[],sources[lang])
            require(yes['full_evidence_success'] is True and no['required_met']==0,'Oracle/empty mismatch')
            for component in q['requirements']:
                # A fragment covering just one component must not satisfy unrelated requirements.
                fragments=[]
                for sid in component['evidence_by_language'][lang]['alternatives'][0]['all_of']:
                    s=data['spans'][sid]; n=len(s['quote'])
                    fragments.append({'text':s['quote'],'metadata':{'document_id':s['document_id'],'source_parser_index':s['source_parser_index'],'source_content_sha256':s['source_content_sha256'],'source_spans':[{'source_start':s['start_char'],'source_end':s['end_char'],'chunk_start':0,'chunk_end':n}]}})
                result=score_evidence(data,q['id'],lang,fragments,sources[lang],k=len(fragments))
                require(result['required_met']==1,'Component isolation failed')
                omission_checks+=1
            for ai in range(len(q['requirements'][0]['evidence_by_language'][lang]['alternatives'])):
                ids={data['spans'][sid]['origin_chunk_id'] for comp in q['requirements'] for sid in comp['evidence_by_language'][lang]['alternatives'][ai]['all_of']}
                anchors=[{'text':byid[cid]['content'],'metadata':byid[cid]['metadata']} for cid in sorted(ids)]
                require(score_evidence(data,q['id'],lang,anchors,sources[lang],k=len(anchors))['full_evidence_success'] is True,'Alternative anchor failed')
                oracle_checks+=1
    if self_check:
        for damage in ('quote','offset','language'):
            bad=copy.deepcopy(data); s=next(iter(bad['spans'].values()))
            if damage=='quote':s['quote']+=' TAMPER'
            elif damage=='offset':s['start_char']+=1
            else:s['language']='en' if s['language']=='vi' else 'vi'
            try:validate_labels(bad)
            except (ValueError,KeyError):pass
            else:raise ValueError('Tamper accepted: '+damage)
    print(json.dumps({'status':'passed','cases':48,'paired_intents':12,'required_components_per_direction':28,'parser_spans':len(data['spans']),'original_anchor_alternative_checks':oracle_checks,'component_isolation_checks':omission_checks,'tamper_checks':3 if self_check else 0,'manifest_sha256':sha(canonical(OUT/'manifest.json')),'inference_run':False},indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify-only',action='store_true'); parser.add_argument('--self-check',action='store_true')
    args=parser.parse_args()
    if not args.verify_only:build()
    verify(args.self_check)
