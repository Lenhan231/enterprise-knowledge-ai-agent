const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const vm = require('node:vm');
const source = readFileSync('src/app/static/app.js', 'utf8');
const chartSource = source.slice(source.indexOf('function renderDashboardVisualization('), source.indexOf('function renderAnswerBody('));
const context = vm.createContext({
  escapeHtml: value => String(value).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('"', '&quot;'),
  formatNumber: String,
  formatFinancialValue: String,
});
vm.runInContext(chartSource, context);
const render = chart => context.renderDashboardVisualization(chart);
const chart = type => ({type, title: '<Sessions>', categories: ['<source>', 'B'],
  series: [{name: 'Sessions', values: [10, 20]}], unit: 'sessions', x_label: 'Source', y_label: 'Sessions', scope: {sources: ['commerce.web_traffic']}});

test('bar renders marks, accessible labels and escaped source data', () => {
  const html = render(chart('bar'));
  assert.match(html, /<rect /);
  assert.match(html, /role="img"/);
  assert.match(html, /&lt;source>/);
  assert.doesNotMatch(html, /<Sessions>|<source>/);
  assert.match(html, /commerce.web_traffic/);
});
test('line handles negative values and null gaps without fiscal-year labels', () => {
  const data = chart('line');
  data.categories = ['2022-01-01', '2022-02-01', '2022-03-01'];
  data.series[0].values = [-3, null, 10];
  const html = render(data);
  assert.match(html, /-3/);
  assert.doesNotMatch(html, /NaN|Infinity|FY |fiscal year/);
  assert.equal((html.match(/<circle /g) || []).length, 2);
});
test('donut renders slices and rejects invalid composition values', () => {
  assert.match(render(chart('donut')), /stroke-dasharray/);
  const data = chart('donut');
  for (const values of [[0, 0], [-1, 2], [null, 2]]) {
    data.series[0].values = values;
    assert.equal(render(data), '');
  }
});
test('unsupported and malformed charts fail closed', () => {
  assert.equal(render(chart('html')), '');
  const data = chart('bar');
  data.series[0].values = [Infinity, 2];
  assert.equal(render(data), '');
});
test('temporal line positions reflect unequal date intervals', () => {
  const data = chart('line');
  data.temporal = true;
  data.categories = ['2022-01-01', '2022-02-01', '2022-04-01'];
  data.series[0].values = [10, 20, 30];
  const html = render(data);
  const points = [...html.matchAll(/<circle cx="([\d.]+)"/g)].map(match => Number(match[1]));
  assert.equal(points.length, 3);
  assert.ok(points[1] - points[0] < points[2] - points[1]);
});
