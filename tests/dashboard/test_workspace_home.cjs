const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('src/app/static/app.js','utf8');
function workspace(role='operations') {
  const nodes=new Map(),shows=[];
  const node=id=>{
    if(!nodes.has(id))nodes.set(id,{id,hidden:false,dataset:{},attrs:{},classList:{add(){},remove(){},toggle(){}},
      setAttribute(k,v){this.attrs[k]=v;},getAttribute(k){return this.attrs[k];},querySelectorAll(){return [];},replaceChildren(){},addEventListener(){}});
    return nodes.get(id);
  };
  const tabs=['dashboard','knowledge','general-chat','upload','processing'];
  const buttons=tabs.map(name=>{const n=node('tab-button-'+name);n.dataset.tabTarget=name;n.attrs['aria-controls']='tab-'+name;return n;});
  const panels=tabs.map(name=>node('tab-'+name));
  const permissions={operations:['view_corpus','ask_documents','view_analytics'],employee:['view_corpus','ask_documents']}[role]||[];
  const context=vm.createContext({currentUser:{role,permissions},activeTab:'home',setTimeout:()=>1,clearTimeout(){},countUp(){},
    $:selector=>selector.startsWith('[data-tab-target=') ? buttons.find(b=>b.dataset.tabTarget===selector.split('"')[1]) : node(selector.replace(/^#/,'')),
    document:{querySelectorAll:s=>s==='.workspace-tab'?buttons:panels},
    window:{businessOverview:{show:allowed=>shows.push(['home',allowed])},dashboardWorkspace:{show:()=>shows.push(['dashboard'])},reportWorkspace:{show:()=>shows.push(['reports'])}}});
  vm.runInContext(source.slice(source.indexOf('function selectWorkspaceTab('),source.indexOf('$("#workspace-home-link").addEventListener')),context);
  return {context,node,buttons,panels,shows};
}
test('login lands on home without selecting a tab; separate tabs and logo navigation work',()=>{
  const env=workspace();env.context.syncWorkspaceTabs();
  assert.equal(env.node('workspace-home').hidden,false);
  assert(env.panels.every(p=>p.hidden));
  assert(env.buttons.every(b=>b.attrs['aria-selected']==='false'));
  assert.equal(env.buttons.find(b=>!b.hidden).tabIndex,0,'Tabs remain keyboard reachable from home');
  assert.deepEqual(env.shows,[['home',true]]);
  env.context.selectWorkspaceTab('dashboard');
  assert.equal(env.node('workspace-home').hidden,true);
  assert.equal(env.node('tab-dashboard').hidden,false);
  env.context.selectWorkspaceTab('knowledge');
  assert.equal(env.node('tab-knowledge').hidden,false);
  env.context.selectWorkspaceTab('general-chat');
  assert.equal(env.node('tab-general-chat').hidden,false);
  env.context.selectWorkspaceTab('home');
  assert.equal(env.node('workspace-home').hidden,false);
  assert.equal(env.shows.filter(s=>s[0]==='home').length,2);
});
test('slow login metadata does not reveal report headers or refresh home twice',async()=>{
  const env=workspace();let resolve;
  Object.assign(env.context,{sessionSubject:'previous',sessionGeneration:1,activeTab:'dashboard',
    chooseBackend(){},backendTimer:1,clearInvoiceReviewCaches(){},resetConversationState(){},
    loadCorpusStats:()=>new Promise(done=>{resolve=done;})});
  const start=source.indexOf('async function loadWorkspace('),end=source.indexOf('$("#workspace-tabs").addEventListener',start);
  vm.runInContext(source.slice(start,end),env.context);
  const pending=env.context.loadWorkspace({username:'new-user',role:'operations',permissions:['view_corpus','ask_documents','view_analytics']});
  assert.equal(env.node('.intro').hidden,true);
  assert.equal(env.node('.agent-overview').hidden,true);
  assert.equal(env.node('.stats').hidden,true);
  assert.equal(env.shows.length,1);
  resolve();await pending;
  assert.equal(env.shows.length,1);
});
test('a role without analytics lands on its first allowed tab, never a blank home or Reports',()=>{
  const env=workspace('employee');env.context.syncWorkspaceTabs();
  assert.equal(env.context.activeTab,'general-chat');
  assert.equal(env.node('tab-general-chat').hidden,false);
  assert.equal(env.node('workspace-home').hidden,true);
  assert.equal(env.buttons.find(b=>b.dataset.tabTarget==='knowledge').hidden,true,'Reports needs view_analytics like its API');
  assert.deepEqual(env.shows,[]);
  env.context.selectWorkspaceTab('dashboard');
  assert.equal(env.context.activeTab,'general-chat');
  env.context.selectWorkspaceTab('home');
  assert.deepEqual(env.shows,[['home',false]]);
  env.context.currentUser=null;
  env.context.selectWorkspaceTab('home');
  assert.equal(env.shows.length,1);
});
test('restored sessions and a different login start at home and home is outside dashboard markup',()=>{
  assert.match(source,/let activeTab = "home"/);
  const start=source.indexOf('async function loadWorkspace('),end=source.indexOf('  if (hasPermission(user, "upload_documents"))',start);
  const env=workspace();Object.assign(env.context,{sessionSubject:'previous',sessionGeneration:1,activeTab:'dashboard',
    chooseBackend(){},backendTimer:1,clearInvoiceReviewCaches(){},resetConversationState(){},setInterval(){}});
  vm.runInContext(source.slice(start,end)+'}',env.context);
  env.context.loadWorkspace({username:'new-user',role:'operations',permissions:['view_corpus','ask_documents','view_analytics']});
  assert.equal(env.context.activeTab,'home');
  const html=fs.readFileSync('src/app/static/index.html','utf8');
  assert(!html.includes('data-tab-target="home"'));
  assert(!html.includes('id="dw-overview"'));
  assert(html.indexOf('id="workspace-home"')<html.indexOf('id="tab-dashboard"'));
  assert(html.indexOf('/static/business-overview.js')<html.indexOf('/static/app.js'));
});
test('a 403 chat error says the user lacks access; other errors keep the service message',()=>{
  const start=source.indexOf('function renderChatTranscript('),end=source.indexOf('\n}\n',start)+2;
  const made=[],el=()=>{const e={dataset:{},append(){},innerHTML:''};made.push(e);return e;};
  const context=vm.createContext({document:{createElement:el},escapeHtml:s=>String(s),displayName:(_,v)=>v});
  vm.runInContext(source.slice(start,end),context);
  const root={replaceChildren(){},append(){}};
  context.renderChatTranscript(root,[{id:1,mode:'auto',question:'q',state:'error',error:'Forbidden',errorStatus:403}],false);
  assert.match(made.at(-1).innerHTML,/không có quyền/);
  assert.doesNotMatch(made.at(-1).innerHTML,/service configuration|error-message|role="alert"/);
  context.renderChatTranscript(root,[{id:2,mode:'auto',question:'q',state:'error',error:'Server error',errorStatus:500}],false);
  assert.match(made.at(-1).innerHTML,/class="error-message" role="alert">Server error\. Please check service configuration/);
  const announce=source.slice(source.indexOf('function announceTurn('),source.indexOf('\n}\n',source.indexOf('function announceTurn('))+2);
  const announcer={textContent:''};
  vm.runInContext(announce,Object.assign(context,{$:()=>announcer,document:{querySelector:()=>null}}));
  context.announceTurn({id:1,state:'error',errorStatus:403});
  assert.equal(announcer.textContent,'Bạn không có quyền xem dữ liệu này.');
  context.announceTurn({id:2,state:'error',errorStatus:500});
  assert.equal(announcer.textContent,'The answer could not be completed');
});
test('empty chat offers the Sales prompt and sales wording only to roles with analytics',async()=>{
  const start=source.indexOf('async function loadWorkspace('),end=source.indexOf('$("#workspace-tabs").addEventListener',start);
  const corpus=source.slice(source.indexOf('function renderCorpus('),source.indexOf('function renderParsedChunkInspector('));
  for (const [role,permissions,sees] of [['employee',['view_corpus','ask_documents'],false],['admin',['view_corpus','ask_documents','view_analytics'],true]]) {
    const env=workspace();
    Object.assign(env.context,{sessionSubject:'previous',sessionGeneration:1,chooseBackend(){},backendTimer:1,clearInvoiceReviewCaches(){},resetConversationState(){},loadCorpusStats:async()=>{},hasPermission:undefined,formatNumber:String});
    vm.runInContext(source.slice(start,end)+source.slice(source.indexOf('function hasPermission('),source.indexOf('function syncWorkspaceTabs('))+corpus,env.context);
    await env.context.loadWorkspace({username:role,role,permissions});
    assert.equal(env.node('chat-prompt-sales').hidden,!sees,role);
    env.context.document.querySelector=()=>env.node('status-dot');
    env.context.renderCorpus({documents:[],document_count:8,chunk_count:1});
    assert.equal(env.node('chat-library-head').innerHTML.includes('sales data'),sees,role);
  }
});
