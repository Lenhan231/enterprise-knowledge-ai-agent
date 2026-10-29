import subprocess
import unittest


class WebConversationTest(unittest.TestCase):
    def test_inflight_answer_cannot_cross_a_conversation_reset(self):
        script = r'''
const fs = require('fs'), vm = require('vm'), assert = require('assert');
const source = fs.readFileSync('src/app/static/app.js', 'utf8');
const start = source.indexOf('$("#ask-form").addEventListener("submit"');
const end = source.indexOf('$("#report-agent-form").addEventListener', start);
let handler, resolve, rendered = 0;
const nodes = {};
const context = {agentConversationId:'old', console,
  $: selector => nodes[selector] ||= {value:selector === '#question' ? 'Count products' : 'auto',
    classList:{add(){}}, addEventListener(event, callback){handler=callback;}},
  api: () => new Promise(done => resolve=done), renderSkeletonAnswer(){},
  renderAgentResult(){rendered++;}, escapeHtml: value=>String(value)};
vm.runInNewContext(source.slice(start,end),context);
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
assert(html.includes('task:s2'));assert(html.includes('&lt;Outdoor>'));
assert.equal((html.match(/<table>/g)||[]).length,2);
'''
        result = subprocess.run(['node', '-'], input=script, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
