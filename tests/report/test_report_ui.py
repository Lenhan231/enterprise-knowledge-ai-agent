"""The fixed report renderer preserves widgets and treats source strings as text."""
from pathlib import Path
import json
import subprocess
import unittest


class ReportUITest(unittest.TestCase):
    def test_saved_vietnamese_report_localizes_preview_and_pdf(self):
        from core.agents.report.document import ReportDocument
        from core.agents.report.export import export_pdf
        from core.agents.report.labels import localize_labels
        from core.agents.report.sales_performance import evaluate_decisions, populate_sections
        from tests.report.test_saved_reports import sample_report
        import fitz

        report = sample_report()
        localize_labels(report)
        change = next(metric for metric in report['metrics'] if metric['id'] == 'company_revenue_change_pct')
        change.update(value=-2.5, status='available', evidence=report['metrics'][0]['evidence'])
        evaluate_decisions(report, {'comparable': True})
        populate_sections(report)
        report['data_quality']['limitations'] = [
            'Order and traffic source completeness is unverified; totals describe matching records, not certified complete periods. No causal explanations are established.',
            'Period-over-period comparison uses calendar-month totals. Daily records verify source coverage only. '
            '2026-01-01 to 2027-01-01 (end excluded): 360 of 365 days; 2025-01-01 to 2026-01-01 (end excluded): 365 of 365 days. '
            'Whole-period revenue change and aggregate comparison-dependent decisions are unavailable; monthly decisions use separate calendar-month baselines. Current-period revenue and profitability remain usable.',
        ]
        saved = ReportDocument(report=report)
        script = r"""
const fs = require('node:fs'), vm = require('node:vm'), assert = require('node:assert/strict');
class Element {
  constructor(tag) { this.tag = tag; this.children = []; this.dataset = {}; }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; }
  setAttribute() {}
}
const element = tag => new Element(tag);
const document = {createElement: element, createElementNS: (_,tag) => element(tag)};
const render = vm.runInNewContext(fs.readFileSync('src/app/static/sales-report.js','utf8')+';SalesPerformanceReport.render', {document,Intl});
const saved = JSON.parse(fs.readFileSync(0, 'utf8')), root = element('div');
render(root, saved.report, {insights:saved.insights});
const text = el => [el.textContent || '', ...el.children.flatMap(text)];
const copy = text(root).join(' ');
assert.match(copy, /Tóm tắt điều hành/);
assert.match(copy, /Nguồn SQL đã xác minh/);
assert.match(copy, /360\/365 ngày/);
assert.match(copy, /So sánh doanh thu theo tháng và đối chiếu/);
assert.match(copy, /-2,5%/);
assert.doesNotMatch(copy, /No usable documentary|Validated SQL evidence|Order and traffic|Period-over-period comparison|A no-trigger conclusion|No chart data|Cannot evaluate|Compare revenue by month/);
"""
        result = subprocess.run(['node', '-e', script], input=json.dumps(saved.model_dump(mode='json')),
                                capture_output=True, text=True, encoding='utf-8',
                                cwd=Path(__file__).resolve().parents[2])
        self.assertEqual(result.returncode, 0, result.stderr)
        with fitz.open(stream=export_pdf(saved), filetype='pdf') as pdf:
            copy = ' '.join(' '.join(page.get_text() for page in pdf).split())
        self.assertIn('360/365 ngày', copy)
        self.assertIn('So sánh doanh thu theo tháng và đối chiếu', copy)
        self.assertNotRegex(copy, r'No usable documentary|Period-over-period comparison|No chart observations|Cannot evaluate|Compare revenue by month')

    def test_inventory_release_revalidates_page_and_replaces_sales_only_assets(self):
        import os
        import sys
        from unittest.mock import patch
        root = Path(__file__).resolve().parents[2]
        sys.path.insert(0, str(root / 'src'))
        from app.main import home
        with patch.dict(os.environ, {'BACKEND_ONLY': '0'}):
            self.assertEqual(home().headers.get('cache-control'), 'no-cache')
        html = (root / 'src/app/static/index.html').read_text(encoding='utf-8')
        self.assertIn('/static/sales-report.css?v=20261120-guidance', html)
        self.assertIn('/static/sales-report.js?v=20261121-report-vi', html)
        self.assertIn('/static/report-workspace.js?v=20261121-report-vi',html)
        self.assertIn('/static/app.js?v=20261125-neutral', html)

    def test_fixed_sections_widgets_and_untrusted_text(self):
        script = r"""
const fs = require('node:fs'), vm = require('node:vm'), assert = require('node:assert/strict');
class Element {
  constructor(tag) { this.tag = tag; this.children = []; this.dataset = {}; this.attributes = {}; }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; }
  setAttribute(key,value) { this.attributes[key]=value; }
}
const document = {createElement: tag => new Element(tag), createElementNS: (_,tag) => new Element(tag)};
const render = vm.runInNewContext(fs.readFileSync('src/app/static/sales-report.js','utf8')+';SalesPerformanceReport.render', {document,Intl});
const report = JSON.parse(fs.readFileSync('data/semantic/sales_performance_strict.json')).runtime_output_template;
report.request.period = {start:'2026-05-01',end_exclusive:'2026-07-01'};
report.data_quality.limitations = ['<img src=x onerror=alert(1)>'];
report.metrics[0].value=20;report.metrics[0].status='available';report.metrics[0].evidence=[{query_id:'08eb2ef823288614',source_table:'commerce.sales',filters:report.request}];
report.dashboard.widgets[1].data = [{period:'2026-05-01',company_revenue:20,company_gross_profit:5}];
const root = new Element('div');
function descendants(el) { return [el,...el.children.flatMap(descendants)]; }
render(root,report);
let nodes = descendants(root);
assert.deepEqual(nodes.filter(n=>n.tag==='h3').map(n=>n.textContent), ['Executive Summary','Sales KPIs','Performance Analysis','Key Findings & Explanations','Decision Support','Sources','Data notes']);
assert.deepEqual(nodes.filter(n=>n.dataset.widgetId).map(n=>[n.dataset.widgetId,n.dataset.chartType]), report.dashboard.widgets.filter(w=>!['sales_kpis','order_kpis'].includes(w.id)).map(w=>[w.id,w.id==='line_breakdown'?'kpi_row':w.type]));
const copy=nodes.map(n=>n.textContent||'').join(' ');
assert(copy.includes('The company revenue is 20 VND.'));
assert(!copy.includes('08eb2ef823288614'));
assert(!copy.includes('unknown_currency_amount'));
assert(nodes.filter(n=>n.tag==='a'&&n.href?.includes('-source-')).every(a=>nodes.some(n=>n.id===a.href.slice(1))));
assert(!nodes.some(n=>n.tag==='img'));
assert(nodes.some(n=>n.textContent==='<img src=x onerror=alert(1)>'));
assert(nodes.some(n=>n.tag==='svg'));
report.dashboard.widgets[1].data = [{period:'2026-01-01',company_revenue:20,company_gross_profit:5},{period:'2026-03-01',company_revenue:30,company_gross_profit:6}];
report.request.period={start:'2026-01-01',end_exclusive:'2026-04-01'};
render(root,report);
assert.equal(descendants(root).filter(n=>n.tag==='polyline').length,4, 'Each series must break across a missing calendar bucket');
render(root,report,{presentation:{chart_types:{sales_trend:'bar',line_breakdown:'kpi_row'}}});
const bars=descendants(root).filter(n=>n.tag==='rect');
assert.notEqual(bars[0].attributes.x,bars[2].attributes.x,'Two bar series must have distinct horizontal positions');
report.request.period = {start:'2026-07-01',end_exclusive:'2026-08-01'};
report.dashboard.widgets[1].data = [];
render(root,report);
assert.equal(descendants(root).filter(n=>n.dataset.widgetId).length,4);
report.request.period={start:'2025-01-01',end_exclusive:'2026-01-01'};
report.dashboard.widgets[1].data=[{period:'2025-11-01',company_revenue:1132584,company_gross_profit:214065.64},{period:'2025-12-01',company_revenue:2237062.71,company_gross_profit:326091.25}];
const stored=JSON.stringify(report);
render(root,report);
nodes=descendants(root);
assert.deepEqual(nodes.filter(n=>n.tag==='text'&&/^2025-\d\d$/.test(n.textContent)).map(n=>n.textContent),Array.from({length:12},(_,i)=>`2025-${String(i+1).padStart(2,'0')}`));
const trend=nodes.find(n=>n.dataset.widgetId==='sales_trend');
const monthRows=descendants(trend).find(n=>n.tag==='tbody').children;
assert.equal(monthRows.length,12);
assert(monthRows.slice(0,10).every(row=>row.children[1].textContent==='Unavailable'));
assert.equal(monthRows[10].children[1].textContent,'1,132,584 VND');
assert.equal(JSON.stringify(report),stored,'Rendering a saved report must not rewrite source data or edits');
report.request.period={start:'2026-05-01',end_exclusive:'2026-06-01'};
report.dashboard.widgets[1].data=[{period:'2026-05-01',company_revenue:20,company_gross_profit:5}];
render(root,report,{presentation:{chart_types:{line_breakdown:'kpi_row'}}});
assert(descendants(root).filter(n=>n.dataset.widgetId).every(n=>n.dataset.chartType==='kpi_row'),'Saved single-month reports default to KPIs');
assert(!descendants(root).some(n=>n.tag==='svg'));
render(root,report,{presentation:{chart_types:{sales_trend:'line'}}});
assert.equal(descendants(root).find(n=>n.dataset.widgetId==='sales_trend').dataset.chartType,'line','An explicit user chart choice must survive');
const monthly = JSON.parse(JSON.stringify(report));
monthly.period = {...report.request.period};
monthly.comparison={comparable:true};monthly.coverage={};
monthly.metrics[0].value=77;
monthly.metrics[0].evidence=[{query_id:'monthly-evidence',source_table:'commerce.sales',filters:{period:monthly.period}}];
monthly.decisions.forEach(rule=>{rule.triggered=false;rule.status='available'});
render(root,report,{monthly_decisions:[monthly]});
nodes=descendants(root);
const decisions=nodes.find(n=>n.dataset.sectionId==='decision_support');
assert(descendants(decisions).some(n=>n.textContent==='2026-05'));
assert(descendants(decisions).some(n=>n.textContent?.includes('revenue is 77 VND')));
assert(nodes.filter(n=>n.tag==='a'&&n.href?.includes('-source-')).every(a=>nodes.some(n=>n.id===a.href.slice(1))));
assert(!nodes.some(n=>n.textContent?.includes('monthly-evidence')));
report.request.granularity='month';
monthly.coverage={current_days:31,expected_current_days:31};
const change=monthly.metrics.find(m=>m.id==='company_revenue_change_pct');
change.value=12.5;change.status='available';change.evidence=monthly.metrics[0].evidence;
render(root,report,{monthly_decisions:[monthly]});
nodes=descendants(root);
assert(nodes.some(n=>n.tag==='dt'&&n.textContent==='Company revenue month-over-month change (2026-05 vs 2026-04)'));
assert(nodes.some(n=>n.tag==='dd'&&n.textContent==='12.5%'));
assert(nodes.some(n=>n.textContent?.includes('month-over-month change (2026-05 vs 2026-04) is 12.5%')));
assert.equal(report.metrics.find(m=>m.id==='company_revenue_change_pct').value,null,'Display defaults must preserve canonical facts');
const incompleteJune = JSON.parse(JSON.stringify(monthly));
incompleteJune.period = {start:'2026-06-01',end_exclusive:'2026-07-01'};
incompleteJune.comparison.comparable = false;
Object.assign(incompleteJune.metrics.find(m => m.id === change.id), {value:null,status:'not_available'});
report.request.period.end_exclusive = '2026-07-01';
render(root,report,{monthly_decisions:[monthly,incompleteJune]});
nodes=descendants(root);
const latestChange=nodes.find(n=>n.tag==='dt'&&n.textContent==='Company revenue month-over-month change (2026-06 vs 2026-05)');
assert(latestChange);
assert(nodes.some(n=>n.children.includes(latestChange)&&n.children.some(child=>child.tag==='dd'&&child.textContent==='Unavailable')));
report.request.period.end_exclusive = '2026-06-01';
const insights={decision_summary:'1 of 1 reporting months fully evaluated', actions:[{title:'Revenue decline',action:'Review company revenue',periods:['2026-05'],citations:['monthly-evidence']}],
  findings:[{text:'Supported monthly finding',citations:['monthly-evidence']}],
  document_context:[{text:'Pricing changes require approval.',citations:['document-evidence']}],
  documents:[{citation_id:'document-evidence',source:'Pricing review',source_type:'document',content:'<img src=x onerror=alert(1)>',metadata:{}}],
  data_needs:['Missing commerce.sales records: 2026-05-04']};
render(root,report,{monthly_decisions:[monthly],insights});
nodes=descendants(root);
assert(nodes.some(n=>n.textContent==='1 of 1 reporting months fully evaluated'));
assert(nodes.some(n=>n.tag==='summary'&&n.textContent==='View all rule evaluations'));
assert(nodes.some(n=>n.tag==='blockquote'&&n.textContent==='Pricing changes require approval.'));
assert(nodes.some(n=>n.textContent==='Missing commerce.sales records: 2026-05-04'));
assert(!nodes.some(n=>n.tag==='img'));
assert(nodes.filter(n=>n.tag==='a'&&n.href?.includes('-source-')).every(a=>nodes.some(n=>n.id===a.href.slice(1))));
"""
        result = subprocess.run(['node', '-e', script], capture_output=True, text=True, cwd=Path(__file__).resolve().parents[2])
        self.assertEqual(result.returncode, 0, result.stderr)
