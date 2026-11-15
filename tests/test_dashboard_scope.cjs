const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const vm = require('node:vm');

function workspace(responseScope, responses = []) {
  const nodes = new Map();
  const node = id => {
    if (!nodes.has(id)) nodes.set(id, {value: '', listeners: {}, dataset: {}, hidden: ['dw-editor', 'dw-transcript'].includes(id),
      addEventListener(event, listener) { this.listeners[event] = listener; },
      setAttribute() {}, removeAttribute() {}, replaceChildren() {},
      querySelectorAll() { return []; }, focus() {},
      requestSubmit() { this.listeners.submit({preventDefault() {}}); },
    });
    return nodes.get(id);
  };
  let doc = {id: 'a'.repeat(32), title: 'Monthly revenue', description: '', scope: '', revision: 1,
    data_updated_at: '2026-11-15', status: 'complete', tiles: [], results: [], tile_status: {}};
  const writes = [];
  const context = vm.createContext({document: {querySelector: () => node('root'), getElementById: node},
    window: {}, sessionGeneration: 1, currentUser: {role: 'admin'},
    escapeHtml: value => String(value).replace(/[&<>"']/g, char => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[char])),
    api: async (path, options) => {
      if (options) {
        const body = JSON.parse(options.body);
        writes.push(body);
        if (responses.length) {
          const next = responses.shift();
          return typeof next === 'function' ? next(body) : next;
        }
        doc = {...doc, description: body.description ?? doc.description, scope: responseScope ?? body.scope};
      }
      if (path === '/api/dashboards' && !options) return {dashboards: []};
      return {dashboard: doc, html: '<main>Source data: old clarification output</main>', html_url: '/api/dashboards/test/html'};
    }});
  vm.runInContext(readFileSync('src/app/static/dashboard.js', 'utf8'), context);
  const submit = async () => {
    node('dw-create').listeners.submit({preventDefault() {}});
    await new Promise(setImmediate);
  };
  return {node, writes, submit, context};
}

test('description, shared scope and preview output stay separate through build and refresh', async () => {
  const {node, writes, submit} = workspace();
  const description = 'Monthly revenue from commerce.sales';
  const scope = '2026-01-01 through 2026-05-31';
  node('dw-prompt').value = description;
  node('dw-create-scope').value = scope;
  await submit();
  assert.equal(writes[0].description, description);
  assert.equal(writes[0].scope, scope);
  assert.equal(node('dw-scope').value, scope);
  assert.equal(node('dw-description').value, description);
  assert.match(node('dw-preview').srcdoc, /old clarification/);
  assert.equal(node('dw-create-scope').value, '');
  node('dw-scope').value = '2026-06-01 through 2026-08-31';
  node('dw-refresh').listeners.click();
  await new Promise(setImmediate);
  assert.equal(writes[1].scope, '2026-06-01 through 2026-08-31');
  assert.equal(node('dw-scope').value, writes[1].scope);
});

test('New clears prior description and scope drafts instead of carrying stale values', async () => {
  const {node} = workspace();
  node('dw-prompt').value = 'Previous dashboard';
  node('dw-create-scope').value = 'Previous scope';
  node('dw-scope').value = 'Previous editor scope';
  node('dw-new').listeners.click();
  assert.equal(node('dw-prompt').value, '');
  assert.equal(node('dw-create-scope').value, '');
  assert.equal(node('dw-scope').value, '');
});

test('a response cannot silently replace submitted scope with generated report text', async () => {
  const {node, submit} = workspace('Source data: generated clarification report');
  node('dw-prompt').value = 'Monthly revenue';
  node('dw-create-scope').value = '2026-01-01 through 2026-05-31';
  await submit();
  assert.match(node('dw-status').textContent, /scope/i);
  assert.equal(node('dw-status').dataset.error, 'true');
  assert.equal(node('dw-scope').value, '');
  assert.equal(node('dw-create-scope').value, '2026-01-01 through 2026-05-31');
});

test('clarification stays in chat, escapes text, and a reply opens the workspace only after success', async () => {
  const scope = 'January through December 2026';
  const description = 'Traffic dashboard with total sessions and monthly trends';
  const identifier = 'c'.repeat(32);
  const question = 'Monthly trend or total? <img src=x onerror=alert(1)>';
  const {node, writes, submit} = workspace(undefined, [{status: 'clarification_required',
    conversation_id: identifier, description, scope, message: question, can_reply: true}]);
  node('dw-prompt').value = description;
  node('dw-create-scope').value = scope;
  await submit();
  assert.equal(node('dw-create').hidden, false);
  assert.equal(node('dw-editor').hidden, true);
  assert.match(node('dw-transcript').innerHTML, /Monthly trend or total/);
  assert.match(node('dw-transcript').innerHTML, /&lt;img/);
  assert.doesNotMatch(node('dw-transcript').innerHTML, /<img/);
  assert.equal(node('dw-create-scope').value, scope);
  assert.equal(node('dw-create-scope').disabled, true);
  assert.equal(node('dw-prompt').value, '');
  node('dw-prompt').value = 'Monthly trend only';
  await submit();
  assert.equal(writes[1].conversation_id, identifier);
  assert.equal(writes[1].description, 'Monthly trend only');
  assert.equal(writes[1].scope, scope);
  assert.equal(node('dw-create').hidden, true);
  assert.equal(node('dw-editor').hidden, false);
});

test('source failure stays in chat and New discards pending clarification identity', async () => {
  const {node, writes, submit} = workspace(undefined, [
    {status: 'clarification_required', conversation_id: 'd'.repeat(32), scope: '', description: 'Traffic',
      message: 'Which period?', can_reply: true},
    {status: 'failed', message: 'Data source unavailable', scope: '', description: 'Other request', conversation_id: null},
  ]);
  node('dw-prompt').value = 'Traffic';
  await submit();
  node('dw-new').listeners.click();
  node('dw-prompt').value = 'Other request';
  await submit();
  assert.equal(writes[1].conversation_id, undefined);
  assert.equal(node('dw-editor').hidden, true);
  assert.match(node('dw-transcript').innerHTML, /Data source unavailable/);
  assert.doesNotMatch(node('dw-transcript').innerHTML, /Which period/);
});

test('Enter sends a request while Shift+Enter keeps a newline', async () => {
  const {node, writes} = workspace();
  node('dw-prompt').value = 'Monthly traffic';
  let prevented = 0;
  node('dw-prompt').listeners.keydown({key: 'Enter', shiftKey: true, preventDefault() { prevented++; }});
  assert.equal(writes.length, 0);
  node('dw-prompt').listeners.keydown({key: 'Enter', shiftKey: false, preventDefault() { prevented++; }});
  await new Promise(setImmediate);
  assert.equal(writes.length, 1);
  assert.equal(prevented, 1);
});

test('account reset discards late clarification replies and their conversation identity', async () => {
  let finish;
  const response = new Promise(resolve => { finish = resolve; });
  const {node, context, writes} = workspace(undefined, [() => response]);
  node('dw-prompt').value = 'Private traffic request';
  node('dw-create').listeners.submit({preventDefault() {}});
  context.sessionGeneration++;
  context.window.dashboardWorkspace.clear();
  finish({status: 'clarification_required', conversation_id: 'e'.repeat(32), scope: '',
    description: 'Private traffic request', message: 'Private question', can_reply: true});
  await new Promise(setImmediate);
  assert.equal(node('dw-transcript').innerHTML, '');
  assert.equal(node('dw-editor').hidden, true);
  node('dw-prompt').value = 'New account request';
  node('dw-create').listeners.submit({preventDefault() {}});
  await new Promise(setImmediate);
  assert.equal(writes[1].conversation_id, undefined);
});

test('clarification round limit requires New rather than submitting another paid request', async () => {
  const {node, writes, submit} = workspace(undefined, [{status: 'clarification_required',
    conversation_id: null, scope: '', description: 'Traffic', message: 'Start a new request.', can_reply: false}]);
  node('dw-prompt').value = 'Traffic';
  await submit();
  assert.equal(node('dw-prompt').disabled, true);
  node('dw-prompt').value = 'Another reply';
  await submit();
  assert.equal(writes.length, 1);
  node('dw-new').listeners.click();
  assert.equal(node('dw-prompt').disabled, false);
});
