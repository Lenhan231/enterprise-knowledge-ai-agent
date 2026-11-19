import subprocess
import unittest


class WebConversationTest(unittest.TestCase):
    def test_stream_fallback_reuses_versioned_clarification_request(self):
        script = r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const source=fs.readFileSync('src/app/static/app.js','utf8');
const start=source.indexOf('async function sendChatMessage('),end=source.indexOf('function announceTurn',start);
const nodes={},calls=[];let shouldFail=false;
const button={id:'ask-button',innerHTML:'Ask',disabled:false};
const input={id:'question',value:''};
const context={sessionGeneration:7,sessionSubject:'user',agentConversationId:'conversation-1',
  sessionTurns:[],crypto:{randomUUID:()=> 'new-turn'},AbortController,DOMException,setTimeout,clearTimeout,setInterval,clearInterval,
  askAgentStream:async()=>{const error=new Error('stream unavailable');error.streamUnavailable=true;throw error;},
  api:async(path,options)=>{calls.push({path,body:JSON.parse(options.body)});
    if(shouldFail)throw new Error('offline');return {answer:'Resolved',metadata:{status:'complete'}};},
  updatePendingProgress:()=>{},updatePendingElapsed:()=>{},
  announceTurn:()=>{},renderSessionTranscript:()=>{},
  $:selector=>nodes[selector]||=(selector==='#question'?input:selector==='#ask-button'?button:
    {classList:{add(){}}})};
vm.runInNewContext(source.slice(start,end),context);
(async()=>{
  await context.sendChatMessage({question:'All regions',displayQuestion:'All regions',
    clarificationReply:{clarification_id:'pending-id-123456789',version:2,choice_id:'choice-id-123456789'},
    mode:'sql',button,input,state:{getId:()=> 'conversation-1',get turns(){return context.sessionTurns;},
      set turns(value){context.sessionTurns=value;}},render:()=>{}});
  assert.equal(calls.length,1);assert.equal(calls[0].path,'/api/agents/chat');
  assert.equal(calls[0].body.conversation_id,'conversation-1');assert.equal(calls[0].body.agent_mode,'sql');
  assert.deepEqual(calls[0].body.clarification_reply,
    {clarification_id:'pending-id-123456789',version:2,choice_id:'choice-id-123456789'});
  const pending={clarificationSubmitting:true,clarificationResponded:false};shouldFail=true;
  await context.sendChatMessage({question:'All regions',clarificationTurn:pending,
    clarificationReply:{clarification_id:'pending-id-123456789',version:2,choice_id:'choice-id-123456789'},
    mode:'sql',button,input,state:{getId:()=> 'conversation-1',get turns(){return context.sessionTurns;},
      set turns(value){context.sessionTurns=value;}},render:()=>{}});
  assert.equal(pending.clarificationSubmitting,false);assert.equal(pending.clarificationResponded,false,
    'Failed POST should leave the original choice available for retry');
})().catch(error=>{console.error(error);process.exitCode=1;});
'''
        result = subprocess.run(['node', '-'], input=script, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_clarification_click_custom_reply_and_mode_work_on_both_surfaces(self):
        script = r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const source=fs.readFileSync('src/app/static/app.js','utf8');
const start=source.indexOf('function clarificationSurface(entry)');
const end=source.indexOf('function resizeGeneralChatComposer()',start);
const handlers={},sent=[],nodes={};
const makeTurn=(id,mode,ui)=>({id,mode,state:'complete',result:{metadata:{clarification_ui:ui}}});
const ui={id:'clarification-id-123456789',version:4,question:'Choose',allow_custom:true,
  choices:[{id:'choice-id-123456789',label:'All regions'}]};
const generalTurn=makeTurn('general-turn','sql',ui);
const askTurn=makeTurn('ask-turn','auto',ui);
let focused=0,rendered=0;
const input={value:'Custom answer',focus(){focused++;}};
const generalEntry={dataset:{turnId:'general-turn'},closest:s=>s==='#general-chat-transcript'?generalEntry:null,
  querySelector:()=>input};
const askEntry={dataset:{turnId:'ask-turn'},closest:()=>null,querySelector:()=>input};
const options={dataset:{clarificationId:ui.id,clarificationVersion:String(ui.version)}};
const button=(kind,id)=>({disabled:false,dataset:{clarificationChoiceId:id},
  classList:{contains:name=>name===kind},
  closest:s=>s.includes('[data-turn-id]')?(kind==='ask-choice'?askEntry:generalEntry):
    s.includes('.clarification-options')?options:null});
const context={generalConversationId:'general-conv',agentConversationId:'ask-conv',
  generalTurns:[generalTurn],sessionTurns:[askTurn],document:{addEventListener:(name,fn)=>handlers[name]=fn},
  $:s=>nodes[s]||=(s==='#general-chat-question'||s==='#question'?input:{disabled:false,innerHTML:'Send'}),
  renderGeneralChatTranscript:()=>{rendered++;},renderSessionTranscript:()=>{rendered++;},
  sendChatMessage:args=>sent.push(args)};
vm.runInNewContext(source.slice(start,end),context);
handlers.click({target:{closest:()=>button('clarification-option',ui.choices[0].id)}});
assert.equal(sent.length,1);assert.equal(sent[0].question,'All regions');
assert.equal(sent[0].mode,'sql');assert.equal(sent[0].state.getId(),'general-conv');
assert.equal(sent[0].clarificationReply.choice_id,ui.choices[0].id);
handlers.click({target:{closest:()=>button('clarification-option',ui.choices[0].id)}});
assert.equal(sent.length,1,'Double click submitted twice');
generalTurn.clarificationSubmitting=false;
handlers.click({target:{closest:()=>button('clarification-custom-open','')}});
assert.equal(generalTurn.clarificationCustomOpen,true);assert.equal(focused,1);
generalTurn.clarificationSubmitting=false;generalTurn.clarificationResponded=false;
const form={closest:s=>s.includes('[data-turn-id]')?generalEntry:s.includes('.clarification-options')?options:form,
  querySelector:()=>input};
let prevented=false;
handlers.submit({target:{closest:()=>form},preventDefault:()=>{prevented=true;}});
assert(prevented);assert.equal(sent.length,2);assert.equal(sent[1].question,'Custom answer');
assert.equal(sent[1].clarificationReply.choice_id,undefined);
const askChoice=button('ask-choice',ui.choices[0].id);
handlers.click({target:{closest:()=>askChoice}});
assert.equal(sent.length,3);assert.equal(sent[2].mode,'auto');assert.equal(sent[2].state.getId(),'ask-conv');
context.generalTurns=[];
handlers.click({target:{closest:()=>button('clarification-option',ui.choices[0].id)}});
assert.equal(sent.length,3,'Old conversation choices must stop working after reset');
'''
        result = subprocess.run(['node', '-'], input=script, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_clarification_question_and_choice_labels_are_escaped(self):
        script = r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const source=fs.readFileSync('src/app/static/app.js','utf8');
const start=source.indexOf('function renderAnswer(');
const end=source.indexOf('function renderAgentRows(',start);
const escapeHtml=value=>String(value??'').replace(/[&<>"']/g,char=>
  ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const panel={hidden:true,innerHTML:'',querySelectorAll:()=>[],querySelector:()=>null};
const context={escapeHtml,answerOutcome:()=>({title:null,badge:'',next:'',gap:false}),
  renderRunDetails:()=>'',renderAnswerBody:()=>'',renderAgentRows:()=>'',
  renderDashboardVisualization:()=>'',requestAnimationFrame:()=>{},ICONS:{copy:''}};
vm.runInNewContext(source.slice(start,end),context);
context.renderAnswer({status:'clarification_required',answer:'Pick one',agent:'sql_analytics',
  clarification_ui:{id:'pending-"<script>',version:1,question:'<img src=x onerror=alert(1)>',
    allow_custom:true,choices:[{id:'choice-"<img>',label:'"><img src=x onerror=alert(1)>'}]}},panel,false);
assert(panel.innerHTML.includes('&lt;img src=x onerror=alert(1)&gt;'));
assert(panel.innerHTML.includes('&quot;&gt;&lt;img src=x onerror=alert(1)&gt;'));
assert(!panel.innerHTML.includes('<img src=x'));
assert(!panel.innerHTML.includes('<script>'));
'''
        result = subprocess.run(['node', '-'], input=script, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_inflight_answer_cannot_cross_a_conversation_reset(self):
        script = r'''
const fs = require('fs'), vm = require('vm'), assert = require('assert');
const source = fs.readFileSync('src/app/static/app.js', 'utf8');
const start = source.indexOf('async function sendChatMessage(');
const end = source.indexOf('function announceTurn', start);
let handler, resolve, rendered = 0;
const nodes = {};
const context = {agentConversationId:'old', sessionGeneration:1, sessionSubject:'user', console,
  crypto:{randomUUID:()=> 'turn-id'},
  AbortSignal:{timeout:()=>({})}, AbortController, DOMException, setTimeout, clearTimeout, setInterval, clearInterval,
  askAgentStream:() => new Promise(done => resolve=done),
  renderSessionTranscript:() => {if(context.sessionTurns.some(turn=>turn.result)) rendered++;},
  sessionTurns:[],
  $: selector => nodes[selector] ||= {value:selector === '#question' ? 'Count products' : '',
    innerHTML:'Ask agent', disabled:false, classList:{add(){}}, addEventListener(event, callback){handler=callback;},},
};
vm.runInNewContext(source.slice(start,end),context);
const listenerStart=source.indexOf('$("#ask-form").addEventListener("submit"');
const listenerEnd=source.indexOf('$("#general-chat-form")',listenerStart);
vm.runInNewContext(source.slice(listenerStart,listenerEnd),context);
(async()=>{
  const pending=handler({preventDefault(){}});
  context.agentConversationId='new';
  resolve({answer:'Old conversation answer',metadata:{status:'complete'}});
  await pending;
  assert.equal(rendered,0,'An old answer was rendered in a new conversation');
})().catch(error=>{console.error(error);process.exitCode=1;});
'''
        result = subprocess.run(['node', '-'], input=script, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_multiple_sql_task_groups_are_rendered(self):
        script = r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const source=fs.readFileSync('src/app/static/app.js','utf8');
const start=source.indexOf('function renderAgentRows('),end=source.indexOf('function renderAgentResult(',start);
const context={escapeHtml:value=>String(value).replaceAll('<','&lt;')};
vm.runInNewContext(source.slice(start,end),context);
const html=context.renderAgentRows({sql:{rows:[{count:3}]},'task:s2':{rows:[{category:'<Outdoor>'}]}});
assert(html.includes('Task s2'));assert(html.includes('&lt;Outdoor>'));
assert.equal((html.match(/<table>/g)||[]).length,2);
'''
        result = subprocess.run(['node', '-'], input=script, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
