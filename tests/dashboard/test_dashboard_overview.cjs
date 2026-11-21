const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
function workspace() {
  const nodes=new Map(),calls=[];
  const node=id=>{
    if(!nodes.has(id))nodes.set(id,{value:'',dataset:{},hidden:false,listeners:{},addEventListener(k,f){this.listeners[k]=f;},setAttribute(){},removeAttribute(k){delete this[k];},replaceChildren(){},querySelectorAll(){return [];},focus(){}});
    return nodes.get(id);
  };
  let overview=async()=>({html:'<main>Live charts</main>',dashboard:{status:'complete',data_updated_at:'2026-11-17T16:07:41Z'}});
  let clock=1000;
  const context=vm.createContext({Date:class extends Date {static now(){return clock;}},document:{querySelector:()=>node('root'),getElementById:node},window:{},currentUser:{role:'operations'},sessionGeneration:1,escapeHtml:String,
    api:async(path)=>{calls.push(path);if(path==='/api/dashboards/overview')return overview();return {dashboards:[]};}});
  vm.runInContext(fs.readFileSync('src/app/static/dashboard-format.js','utf8'),context);
  vm.runInContext(fs.readFileSync('src/app/static/business-overview.js','utf8'),context);
  vm.runInContext(fs.readFileSync('src/app/static/dashboard.js','utf8'),context);
  return {node,calls,context,advance(ms){clock+=ms;},setOverview(fn){overview=fn;}};
}
test('home reuses its temporary overview independently of dashboard library and drafts',async()=>{
  const env=workspace();env.node('dw-prompt').value='Unsaved question';
  await env.context.window.businessOverview.show(true);
  assert.equal(env.node('home-overview-preview').srcdoc,'<main>Live charts</main>');
  assert.match(env.node('home-overview-status').textContent,/17\/11\/2026 23:07/);
  assert.equal(env.node('dw-prompt').value,'Unsaved question');
  await env.context.window.businessOverview.show(true);
  assert.equal(env.calls.filter(p=>p==='/api/dashboards/overview').length,1);
  assert.equal(env.calls.filter(p=>p==='/api/dashboards').length,0);
  await env.context.window.dashboardWorkspace.show();
  assert.equal(env.calls.filter(p=>p==='/api/dashboards/overview').length,1);
  assert.equal(env.calls.filter(p=>p==='/api/dashboards').length,1);
  assert(env.calls.every(path=>!path.includes('/refresh')));
});

test('cache expires after five minutes and Refresh always fetches current data',async()=>{
  const env=workspace();
  await env.context.window.businessOverview.show(true);
  env.advance(299999);
  await env.context.window.businessOverview.show(true);
  assert.equal(env.calls.length,1);
  env.advance(1);
  await env.context.window.businessOverview.show(true);
  assert.equal(env.calls.length,2);
  await env.node('home-overview-refresh').listeners.click();
  assert.equal(env.calls.length,3);
});

test('returning during a load shares its request and logout discards cached data',async()=>{
  const env=workspace();let resolve;
  env.setOverview(()=>new Promise(done=>{resolve=done;}));
  const first=env.context.window.businessOverview.show(true);
  const second=env.context.window.businessOverview.show(true);
  assert.equal(env.calls.length,1);
  resolve({html:'cached data',dashboard:{status:'complete',data_updated_at:'2026-11-17T16:07:41Z'}});
  await Promise.all([first,second]);
  env.context.window.businessOverview.clear();
  assert.equal(env.node('home-overview-preview').srcdoc,undefined);
  env.setOverview(async()=>({html:'new account',dashboard:{status:'complete'}}));
  await env.context.window.businessOverview.show(true);
  assert.equal(env.calls.length,2);
  env.context.sessionGeneration++;
  await env.context.window.businessOverview.show(true);
  assert.equal(env.calls.length,3);
  await env.context.window.businessOverview.show(false);
  assert.equal(env.node('home-overview-preview').srcdoc,undefined);
});

test('failed refreshes are not cached',async()=>{
  const env=workspace();
  await env.context.window.businessOverview.show(true);
  env.setOverview(async()=>{throw new Error('Source unavailable');});
  await env.node('home-overview-refresh').listeners.click();
  assert.equal(env.node('home-overview-preview').srcdoc,undefined);
  await env.context.window.businessOverview.show(true);
  assert.equal(env.calls.length,3);
  env.setOverview(async()=>({html:'Unavailable',dashboard:{status:'failed'}}));
  await env.context.window.businessOverview.show(true);
  await env.context.window.businessOverview.show(true);
  assert.equal(env.calls.length,5);
});
test('late overview responses cannot cross a logout or account switch',async()=>{
  const env=workspace();let resolve;
  env.setOverview(()=>new Promise(done=>{resolve=done;}));
  const pending=env.context.window.businessOverview.show(true);
  await new Promise(setImmediate);
  assert.notEqual(env.node('dw-prompt').disabled,true,'Live SQL must not block saved dashboard actions');
  env.context.window.businessOverview.clear();env.context.sessionGeneration++;
  resolve({html:'private old account data',dashboard:{status:'complete',data_updated_at:'2026-11-17T16:07:41Z'}});
  await pending;
  assert.equal(env.node('home-overview-preview').srcdoc,undefined);
  assert.equal(env.node('home-overview-status').textContent,'');
});
test('an overview source outage does not hide the saved dashboard library',async()=>{
  const env=workspace();env.setOverview(async()=>{throw new Error('Source unavailable');});
  await env.context.window.businessOverview.show(true);
  assert.equal(env.node('home-overview-status').dataset.error,'true');
  await env.context.window.dashboardWorkspace.show();
  assert(env.calls.includes('/api/dashboards'));
  assert.match(env.node('dw-library').innerHTML,/saved dashboards/);
});

test('home without analytics permission makes no overview request',async()=>{
  const env=workspace();
  await env.context.window.businessOverview.show(false);
  assert.equal(env.calls.length,0);
  assert.match(env.node('home-overview-status').textContent,/analytics access/i);
  assert.equal(env.node('home-overview-preview').hidden,true);
});
