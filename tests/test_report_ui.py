"""Exercise the shipped confirmation function without a browser dependency."""
from pathlib import Path
import shutil
import subprocess
import unittest


class ReportDialogTest(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Node is required for browser JavaScript contract checks')
    def test_choices_cancellation_and_untrusted_text(self):
        source = (Path(__file__).resolve().parents[1] / 'src/app/static/app.js').read_text(encoding='utf-8')
        function = source[source.index('function confirmReportPlan('):source.index('$("#report-agent-form").addEventListener', source.index('function confirmReportPlan('))]
        harness = r'''
const assert = require('node:assert/strict');
class Element {
  constructor(tag) { this.tag = tag; this.children = []; this.events = {}; this.attributes = {}; }
  append(...children) { this.children.push(...children); }
  setAttribute(key, value) { this.attributes[key] = value; }
  addEventListener(key, callback) { this.events[key] = callback; }
  showModal() { this.open = true; }
  close() { this.open = false; }
  remove() { this.removed = true; }
}
const document = {createElement: tag => new Element(tag), body: new Element('body')};
async function check() {
  const bad = '<img src=x onerror=alert(1)>';
  const promise = confirmReportPlan({template_decision_required:true, scope_decision_required:true,
    mismatch_reasons:[bad], unsupported_requirements:['Missing supplier data'], suggested_structure:[{heading:'Stock'}]});
  let dialog = document.body.children.at(-1);
  assert(dialog.open);
  assert.equal(dialog.attributes['aria-labelledby'], 'report-plan-title');
  assert(dialog.children.some(child => child.textContent === bad));
  assert(!dialog.children.some(child => child.tag === 'img'));
  dialog.children.find(child => child.tag === 'button' && child.textContent.startsWith('Use suggested')).events.click();
  assert.deepEqual(await promise, {templateChoice:'suggested', acceptSupportedScope:true});
  assert(dialog.removed && !dialog.open);
  const uploaded = confirmReportPlan({template_decision_required:true});
  dialog = document.body.children.at(-1);
  dialog.children.find(child => child.tag === 'button' && child.textContent.startsWith('Continue with')).events.click();
  assert.deepEqual(await uploaded, {templateChoice:'uploaded', acceptSupportedScope:false});
  const scope = confirmReportPlan({scope_decision_required:true});
  dialog = document.body.children.at(-1);
  dialog.children.find(child => child.tag === 'button' && child.textContent === 'Generate supported report').events.click();
  assert.deepEqual(await scope, {templateChoice:null, acceptSupportedScope:true});
  const cancel = confirmReportPlan({});
  dialog = document.body.children.at(-1);
  let prevented = false;
  dialog.events.cancel({preventDefault(){prevented=true;}});
  assert.equal(await cancel, null);
  assert(prevented && dialog.removed);
}
check().catch(error => { console.error(error); process.exitCode=1; });
'''
        result = subprocess.run(['node', '-e', function+'\n'+harness], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
