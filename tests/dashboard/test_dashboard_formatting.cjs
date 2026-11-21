const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const format=vm.runInNewContext(fs.readFileSync('src/app/static/dashboard-format.js','utf8')+';DashboardFormatting');
test('Vietnamese display formatting is fixed independently of browser settings',()=>{
  assert.equal(format.number(1234567.5),'1.234.567,5');
  assert.equal(format.number(1234.56,{unit:'count'}),'1.235');
  assert.equal(format.number(12.56,{unit:'percent'}),'12,6%');
  assert.equal(format.number(.1256,{unit:'fraction'}),'12,6%');
  assert.equal(format.number(1234.5,{unit:'currency'}),'1.235');
  assert.equal(format.number(1234.5,{unit:'currency',currency:'VND'}),'1.235 ₫');
  for(const value of [null,undefined,true,'',Infinity,NaN])assert.equal(format.number(value),'—');
  assert.equal(format.datetime('2026-11-17T16:07:41.123456+00:00'),'17/11/2026 23:07');
  assert.equal(format.datetime('2026-11-17 16:07:41'),'17/11/2026 23:07');
  assert.equal(format.datetime('invalid'),'—');
});
