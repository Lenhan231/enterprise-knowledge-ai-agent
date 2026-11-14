"""The web page moves a request to the second backend only when the first never reached the app."""
import subprocess
import unittest

SCRIPT = r'''
const fs = require('fs'), vm = require('vm'), assert = require('assert');
const source = fs.readFileSync('src/app/static/app.js', 'utf8');
const code = source.slice(source.indexOf('const API_BASES'), source.indexOf('async function api(path'));
const reply = (status, type) => ({status, ok: status < 400, headers: {get: () => type}});
async function run(plan, path, init) {
  const calls = [];
  const context = {fetch: async (url) => { calls.push(url); const next = plan.shift(); if (next instanceof Error) throw next; return next; },
    performance, AbortSignal, setInterval, setTimeout};
  vm.runInNewContext(code + '; this.backendFetch = backendFetch; this.chooseBackend = chooseBackend; this.base = () => apiBase;', context);
  let result, error;
  try { result = await context.backendFetch(path, init); } catch (e) { error = e; }
  return {calls, result, error, base: context.base(), context};
}
(async () => {
  // tunnel offline (non-JSON 502) -> same request on the fallback, which is then kept
  let r = await run([reply(502, 'text/html'), reply(200, 'application/json')], '/api/agents/chat/stream', {method: 'POST'});
  assert.deepStrictEqual(r.calls, ['/api/agents/chat/stream', '/api-fallback/agents/chat/stream']);
  assert.strictEqual(r.base, '/api-fallback');
  // the app's own errors are JSON: never retried, even 503
  r = await run([reply(503, 'application/json')], '/api/agents/feedback', {method: 'POST'});
  assert.deepStrictEqual(r.calls, ['/api/agents/feedback']);
  // a POST that may have reached the app (504) is not sent twice; a GET is
  r = await run([reply(504, 'text/plain')], '/api/agents/report', {method: 'POST'});
  assert.strictEqual(r.calls.length, 1);
  r = await run([reply(504, 'text/plain'), reply(200, 'application/json')], '/api/dashboard', {});
  assert.strictEqual(r.calls.length, 2);
  // network error: GET moves, POST does not, a timeout never does
  r = await run([new TypeError('Failed to fetch'), reply(200, 'application/json')], '/api/auth/me', {});
  assert.strictEqual(r.calls[1], '/api-fallback/auth/me');
  r = await run([new TypeError('Failed to fetch')], '/api/documents/upload', {method: 'POST'});
  assert.ok(r.error && r.calls.length === 1);
  r = await run([Object.assign(new Error('t'), {name: 'TimeoutError'})], '/api/auth/me', {});
  assert.ok(r.error && r.calls.length === 1);
  // backend choice: primary kept unless the fallback is clearly faster; nothing changes if both fail
  // backend choice over three: the main one is kept unless another is clearly faster; a down main one is left
  const timed = async (ok, delays = [20, 25, 30]) => {
    const ctx = (await run([], '/x', {})).context;
    const index = (url) => url.startsWith('/api-fallback-2') ? 2 : url.startsWith('/api-fallback') ? 1 : 0;
    ctx.fetch = (url) => new Promise((done) => setTimeout(() => done(reply(ok[index(url)] ? 200 : 503, 'application/json')), delays[index(url)]));
    await ctx.chooseBackend(); return ctx.base();
  };
  assert.strictEqual(await timed([false, true, true]), '/api-fallback');
  assert.strictEqual(await timed([false, false, true]), '/api-fallback-2');
  assert.strictEqual(await timed([true, true, true]), '/api');
  assert.strictEqual(await timed([true, true, true], [100, 20, 90]), '/api-fallback');  // >40% faster than the main one
  assert.strictEqual(await timed([false, false, false]), '/api');
  // with the first two unreachable, a request reaches the third and it is kept for the next ones
  r = await run([reply(502, 'text/html'), reply(404, 'text/html'), reply(200, 'application/json')], '/api/agents/chat/stream', {method: 'POST'});
  assert.deepStrictEqual(r.calls, ['/api/agents/chat/stream', '/api-fallback/agents/chat/stream', '/api-fallback-2/agents/chat/stream']);
  assert.strictEqual(r.base, '/api-fallback-2');
  // all three unreachable: the last answer is returned, not an exception
  r = await run([reply(502, 'text/html'), reply(502, 'text/html'), reply(502, 'text/html')], '/api/dashboard', {});
  assert.strictEqual(r.result.status, 502);
  // source files load through backendFetch (fallback + ngrok header) and keep the PDF page anchor
  const loader = source.slice(source.indexOf('async function loadApiFile'), source.indexOf('document.addEventListener("click", async'));
  const seen = [];
  const lctx = {backendFetch: async (url, init) => { seen.push([url, init.headers['ngrok-skip-browser-warning']]); return {status: 200, ok: true, blob: async () => 'pdf'}; },
    URL: {createObjectURL: () => 'blob:x'}, clearExpiredSession() {}};
  vm.runInNewContext(loader + '; this.loadApiFile = loadApiFile;', lctx);
  assert.strictEqual(await lctx.loadApiFile('/api/documents/D1/source#page=12'), 'blob:x#page=12');
  assert.deepStrictEqual(seen, [['/api/documents/D1/source', '1']]);
  console.log('ok');
})().catch((error) => { console.error(error); process.exit(1); });
'''


class BackendFailoverTest(unittest.TestCase):
    def test_failover_rules(self):
        result = subprocess.run(["node", "-e", SCRIPT], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)


if __name__ == "__main__":
    unittest.main()
