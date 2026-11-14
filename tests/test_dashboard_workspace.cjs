const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const vm = require('node:vm');

test('tile deletion is a draft edit, preserves siblings, and saves through the existing API', async () => {
  const doc = {id: 'a'.repeat(32), title: 'Sales', description: 'Monthly revenue', scope: '2026', revision: 1,
    data_updated_at: '2026-11-14', status: 'complete', results: [], tile_status: {},
    tiles: ['trend', 'summary'].map((id, i) => ({id, title: id, kind: i ? 'summary' : 'line', query_id: 'sales', dimension: 'month', measures: ['revenue'], span: 1}))};
  const nodes = new Map();
  const node = id => {
    if (!nodes.has(id)) nodes.set(id, {value: '', listeners: {}, dataset: {},
      addEventListener(event, listener) { this.listeners[event] = listener; },
      setAttribute() {}, removeAttribute() {}, replaceChildren() {},
      querySelectorAll(selector) {
        if (id !== 'dw-tiles' || selector !== '.dw-tile') return [];
        return doc.tiles.map(tile => ({querySelector(query) {
          const field = query.match(/data-field="([^"]+)"/)[1];
          return {value: field === 'measures' ? tile.measures.join(', ') : String(tile[field] ?? '')};
        }}));
      }});
    return nodes.get(id);
  };
  const writes = [];
  const context = vm.createContext({document: {querySelector: () => node('root'), getElementById: node},
    window: {}, sessionGeneration: 1, currentUser: {role: 'admin'}, escapeHtml: String,
    api: async (path, options) => {
      if (options) writes.push(JSON.parse(options.body));
      if (path === '/api/dashboards') return {dashboards: []};
      return {dashboard: doc, html: '<main>Saved</main>', html_url: '/api/dashboards/test/html'};
    }});
  vm.runInContext(readFileSync('src/app/static/dashboard.js', 'utf8'), context);
  node('dw-library').listeners.click({target: {closest: () => ({dataset: {id: doc.id}})}});
  await new Promise(setImmediate);
  const remove = index => node('dw-tiles').listeners.click({target: {closest: () => ({
    hasAttribute: name => name === 'data-remove', closest: () => ({dataset: {index: String(index)}}), dataset: {},
  })}});
  remove(0);
  assert.deepEqual(Array.from(doc.tiles, tile => tile.id), ['summary']);
  assert.equal(writes.length, 0);
  assert.match(node('dw-status').textContent, /Save edits/);
  remove(0);
  assert.equal(doc.tiles.length, 1);
  assert.match(node('dw-status').textContent, /at least one/);
  node('dw-save').listeners.click();
  await new Promise(setImmediate);
  assert.deepEqual(writes[0].tiles.map(tile => tile.id), ['summary']);
});
