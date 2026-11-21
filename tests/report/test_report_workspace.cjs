const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('src/app/static/report-workspace.js','utf8');
const contract = JSON.parse(fs.readFileSync('data/semantic/sales_performance_strict.json','utf8'));
const documentFixture = () => ({id:'12345678-1234-1234-1234-123456789abc',revision:1,title:'Sales report',status:'partial',updated_at:'2026-11-18T00:00:00Z',report:contract.runtime_output_template,presentation:{section_order:[...contract.sections],hidden_sections:[],chart_types:{line_breakdown:'kpi_row'},text_edits:{}}});
const response = (payload,status=200) => ({status,ok:status<400,json:async()=>payload,blob:async()=>({pdf:true})});
const flush = async () => { for(let i=0;i<12;i++) await Promise.resolve(); };
function environment() {
  const nodes={},calls=[],renders=[];
  let responder=async()=>response({reports:[]}), cleared=0, downloads=0;
  class Element {
    constructor(tag='div') { this.tag=tag;this.children=[];this.dataset={};this.attributes={};this.events={};this.disabled=false; }
    set id(value) { this._id=value;nodes[value]=this; } get id(){return this._id;}
    append(...items){this.children.push(...items);} replaceChildren(...items){this.children=items;}
    setAttribute(key,value){this.attributes[key]=value;} removeAttribute(key){delete this.attributes[key];}
    addEventListener(event,fn){this.events[event]=fn;} focus(){} click(){if(this.tag==='a')downloads++;else return this.events.click?.({preventDefault(){}});}
    querySelectorAll(selector){return Object.values(nodes).filter(n=>selector === '[data-report-vi]' ? n.dataset.reportVi : ['button','input','textarea','select'].includes(n.tag));}
  }
  const get=id=>nodes[id]||(()=>{const n=new Element(id==='rw-title'?'input':id==='report-agent-question'?'textarea':id.startsWith('rw-')&& !['rw-library','rw-edit-panel','rw-editor','rw-meta'].includes(id)||id==='report-agent-submit'?'button':'div');n.id=id;return n;})();
  const context={document:{getElementById:get,createElement:tag=>new Element(tag)}, currentUser:{role:'finance_analyst'},sessionGeneration:1,reportConversationId:'report',
    backendFetch:async(path,options)=>{calls.push({path,options});return responder(path,options);},
    clearExpiredSession(){cleared++;context.sessionGeneration++;context.window.reportWorkspace.clear();},
    SalesPerformanceReport:{render:(root,report,options)=>renders.push(JSON.parse(JSON.stringify({report,options}))),sectionTitles:contract.section_contract.map(s=>s.title),sectionTitlesVi:['Tóm tắt điều hành'],vietnamese:(text='')=>/báo cáo|doanh thu/i.test(text),narrative:()=>[{text:'Generated summary.'}],defaultPresentation:()=>({chart_types:{line_breakdown:'kpi_row'}})},
    window:{confirm:()=>true,setTimeout:()=>{}},URL:{createObjectURL:()=> 'blob:report',revokeObjectURL(){}},crypto:require('node:crypto').webcrypto,console};
  ['report-agent-submit','report-agent-question','rw-title','reports-workspace'].forEach(get);
  get('report-agent-submit').textContent = 'Generate report';
  get('report-agent-submit').dataset.reportVi = 'Tạo báo cáo';
  vm.runInNewContext(source,context);
  return {context,nodes,calls,renders,get,setResponder:value=>{responder=value;},get cleared(){return cleared;},get downloads(){return downloads;}};
}
async function run(){
  const env=environment();let doc=documentFixture();
  env.setResponder(async(path,options)=>path==='/api/reports'&&options.method==='POST'?response({document:doc},201):response({reports:[]}));
  await env.context.window.reportWorkspace.generate('Monthly revenue report 2026');
  assert.equal(env.calls[0].options.headers['ngrok-skip-browser-warning'],'1');
  assert.equal(env.get('rw-editor').hidden,false);
  const fields=env.get('rw-edit-panel').children;
  fields[0].children[1].children[1].click();
  assert.equal(env.renders.at(-1).options.presentation.section_order[1],'executive_summary');
  env.get('rw-type-sales_trend').value='bar';env.get('rw-type-sales_trend').events.change();
  assert.equal(env.renders.at(-1).options.presentation.chart_types.sales_trend,'bar');
  assert.deepEqual(env.renders.at(-1).report,doc.report);
  let resolveSave;
  env.setResponder(async(path,options)=>options.method==='PUT'?new Promise(resolve=>{resolveSave=resolve;}):response({reports:[]}));
  const saving=env.get('rw-save').click();await flush();
  assert(env.get('rw-title').disabled);
  assert(env.get('report-agent-submit').disabled);
  const before=env.calls.length;await env.context.window.reportWorkspace.generate('another report');assert.equal(env.calls.length,before);
  resolveSave(response({document:{...doc,revision:2}}));await saving;
  assert.equal(env.get('rw-title').disabled,false);
  env.setResponder(async(path,options)=>{
    if(options.method==='PUT'){const edit=JSON.parse(options.body);doc={...doc,...edit,revision:3};return response({document:doc});}
    if(path.includes('/pdf'))return response({});
    return response({reports:[]});
  });
  await env.get('rw-download').click();
  assert.equal(env.downloads,1);
  assert(env.calls.some(call=>call.path.endsWith('/pdf?revision=3')));
  const stale=environment();let resolveOld;
  stale.setResponder(()=>new Promise(resolve=>{resolveOld=resolve;}));
  stale.context.window.reportWorkspace.show();await flush();
  stale.context.sessionGeneration++;stale.context.window.reportWorkspace.clear();
  resolveOld(response({},401));await flush();
  assert.equal(stale.cleared,0,'A stale 401 must not clear a newer session');
  assert.equal(stale.get('rw-library').children.length,0);
  assert.equal(stale.get('rw-title').value,'');
  assert.equal(stale.get('rw-edit-panel').children.length,0);
  const expired=environment();expired.setResponder(async()=>response({},401));
  await expired.context.window.reportWorkspace.generate('Monthly report');assert.equal(expired.cleared,1);
  const switched=environment();let resolveGeneration;
  switched.setResponder(()=>new Promise(resolve=>{resolveGeneration=resolve;}));
  const generation=switched.context.window.reportWorkspace.generate('Monthly report');await flush();
  switched.context.sessionGeneration++;switched.context.window.reportWorkspace.clear();
  resolveGeneration(response({document:documentFixture()},201));await generation;
  assert.equal(switched.renders.length,0,'A response from an old session must not render');
  const localized=environment(), vietnameseDoc=JSON.parse(JSON.stringify(documentFixture()));
  vietnameseDoc.report.metrics[0].label='Doanh thu công ty';
  localized.setResponder(async(path,options)=>options.method==='POST'?response({document:vietnameseDoc},201):response({reports:[]}));
  await localized.context.window.reportWorkspace.generate('Tạo báo cáo tài chính');
  assert.equal(localized.get('reports-workspace').attributes.lang, 'vi');
  assert.equal(localized.get('report-agent-submit').textContent, 'Tạo báo cáo');
  assert.match(localized.get('report-workspace-status').textContent, /^Đã lưu báo cáo/);
  assert.match(localized.get('rw-meta').textContent, /^Phiên bản đã lưu/);
  localized.context.window.reportWorkspace.clear();
  assert.equal(localized.get('report-agent-submit').textContent, 'Generate report');
}
run().catch(error=>{console.error(error);process.exitCode=1;});
