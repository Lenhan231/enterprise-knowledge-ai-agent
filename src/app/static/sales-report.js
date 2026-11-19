/* Fixed sales report rendering. All source text stays in text nodes. */
const SalesPerformanceReport = (() => {
  const node = (tag, text, className) => {
    const element = document.createElement(tag);
    if (text !== undefined) element.textContent = text;
    if (className) element.className = className;
    return element;
  };
  const format = value => value == null ? 'Unavailable' : new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(value);
  const sectionTitles = ['Executive Summary', 'Sales KPIs', 'Performance Analysis', 'Key Findings & Explanations', 'Decision Support'];
  const svgNode = (tag, attributes) => {
    const element = document.createElementNS('http://www.w3.org/2000/svg', tag);
    for (const [key, value] of Object.entries(attributes)) element.setAttribute(key, value);
    return element;
  };

  function calendarRows(widget, scope) {
    if (widget.x_dimension !== 'period') return widget.data;
    const step = {month:1, quarter:3, year:12}[scope.granularity];
    const start = new Date(scope.period.start + 'T00:00:00Z');
    const end = new Date(scope.period.end_exclusive + 'T00:00:00Z');
    start.setUTCMonth(Math.floor(start.getUTCMonth() / step) * step, 1);
    const observed = new Map(widget.data.map(row => [row.period,row]));
    const rows = [];
    for (let current = start; current < end; current.setUTCMonth(current.getUTCMonth() + step)) {
      const period = current.toISOString().slice(0,10);
      rows.push({...observed.get(period) || {period,...Object.fromEntries(widget.metric_ids.map(id => [id,null]))}});
    }
    return rows;
  }

  function dataTable(widget, metrics) {
    const wrap = node('div', undefined, 'sales-report-table');
    const table = node('table');
    table.append(node('caption', widget.title));
    const head = node('thead');
    const headings = node('tr');
    for (const label of [widget.x_dimension, ...widget.metric_ids.map(id => metrics[id].label)]) {
      const th = node('th', label); th.scope = 'col'; headings.append(th);
    }
    head.append(headings); table.append(head);
    const body = node('tbody');
    for (const row of widget.data) {
      const tr = node('tr');
      tr.append(node('td', row[widget.x_dimension] ?? 'Unknown'));
      widget.metric_ids.forEach(id => tr.append(node('td', formatMetric(metrics[id], row[id]))));
      body.append(tr);
    }
    table.append(body); wrap.append(table); return wrap;
  }

  function chart(widget, granularity) {
    const values = widget.data.flatMap(row => widget.metric_ids.map(id => row[id])).filter(value => typeof value === 'number' && Number.isFinite(value));
    if (!values.length) return node('p', 'No chart data available.');
    const min = Math.min(0, ...values), max = Math.max(0, ...values);
    const range = max - min || 1;
    const x = index => 48 + (index + 0.5) * 520 / widget.data.length;
    const y = value => 180 - (value - min) / range * 150;
    const svg = svgNode('svg', { viewBox: '0 0 600 225', role: 'img', 'aria-label': `${widget.title}. Values in the data table below.` });
    svg.append(svgNode('line', { x1: 48, x2: 568, y1: y(0), y2: y(0), stroke: 'currentColor' }));
    for (const [index, value] of [[0, max], [1, min]]) {
      const label = svgNode('text', { x: 4, y: index ? 184 : 28, 'font-size': 11, fill: 'currentColor' });
      label.textContent = format(value); svg.append(label);
    }
    widget.metric_ids.forEach((id, series) => {
      const color = ['#287b78','#a15c20','#6951a8'][series % 3];
      let segment = [];
      const flush = () => {
        if (segment.length) svg.append(svgNode('polyline', { points: segment.join(' '), fill: 'none', stroke: color, 'stroke-width': 2 }));
        segment = [];
      };
      widget.data.forEach((row, index) => {
        if (widget.type === 'line' && index && widget.x_dimension === 'period') {
          const monthIndex = period => Number(period.slice(0, 4)) * 12 + Number(period.slice(5, 7));
          const step = {month: 1, quarter: 3, year: 12}[granularity];
          if (monthIndex(row.period) - monthIndex(widget.data[index - 1].period) !== step) flush();
        }
        const value = row[id];
        if (value == null) { flush(); return; }
        const mark = widget.type === 'bar'
          ? svgNode('rect', { x: x(index) - Math.min(20, 200 / widget.data.length) + series * Math.min(40, 400 / widget.data.length) / widget.metric_ids.length, y: Math.min(y(value), y(0)), width: Math.min(40, 400 / widget.data.length) / widget.metric_ids.length, height: Math.abs(y(value) - y(0)), fill: color })
          : svgNode('circle', { cx: x(index), cy: y(value), r: 3, fill: color });
        const title = svgNode('title', {});
        title.textContent = `${row[widget.x_dimension] ?? 'Unknown'}: ${id} ${format(value)}`;
        mark.append(title);
        svg.append(mark);
        segment.push(`${x(index)},${y(value)}`);
      });
      if (widget.type === 'line') flush();
    });
    widget.data.forEach((row, index) => {
      if (widget.data.length > 12 && index && index !== widget.data.length - 1 && index % Math.ceil(widget.data.length / 4)) return;
      const label = svgNode('text', { x: x(index), y: 210, 'text-anchor': 'middle', 'font-size': 10, fill: 'currentColor' });
      label.textContent = widget.x_dimension === 'period' ? row.period.slice(0,7) : row[widget.x_dimension] ?? 'Unknown'; svg.append(label);
    });
    return svg;
  }


  let renderId = 0;
  const defaultPresentation = report => {
    if (report?.report_type === 'inventory_operations') return {section_order:Object.keys(inventoryTitles), hidden_sections:[], chart_types:{}, text_edits:{}};
    const chart_types = {line_breakdown:'kpi_row'};
    if (report) {
      const next = new Date(report.request.period.start + 'T00:00:00Z');
      next.setUTCMonth(next.getUTCMonth() + 1);
      if (next.toISOString().slice(0,10) === report.request.period.end_exclusive) {
        report.dashboard.widgets.filter(w => w.x_dimension === 'period' && w.type !== 'kpi_row').forEach(w => { chart_types[w.id] = 'kpi_row'; });
      }
    }
    return {section_order: ['executive_summary','sales_kpis','performance_analysis','key_findings_and_explanations','decision_support'], hidden_sections: [], chart_types, text_edits: {}};
  };
  const formatMetric = (metric, value = metric.value) => value == null ? 'Unavailable' : format(value) + (metric.unit === 'percent' ? '%' : metric.unit.startsWith('unknown_currency') ? ' VND' : '');
  const slotMetrics = {
    executive_summary: [['company_revenue','company_revenue_change_pct'],['company_gross_profit','company_gross_margin_pct'],['order_count']],
    key_findings_and_explanations: [['company_revenue_change_pct'],['company_gross_profit','company_gross_margin_pct'],['order_count','delivered_average_order_value']],
  };
  function comparisonMetrics(report, monthly = []) {
    if (!monthly.length || report.request.granularity !== 'month') return report.metrics;
    const observed = monthly.filter(group => group.metrics.some(m => m.id === 'company_revenue' && m.value !== null));
    const selected = (observed.length ? observed : monthly).at(-1);
    const prior = new Date(selected.period.start + 'T00:00:00Z'); prior.setUTCMonth(prior.getUTCMonth()-1);
    const change = {...selected.metrics.find(m => m.id === 'company_revenue_change_pct'), label:`Company revenue month-over-month change (${selected.period.start.slice(0,7)} vs ${prior.toISOString().slice(0,7)})`};
    return report.metrics.map(m => m.id === change.id ? change : m);
  }
  function narrative(report, key, monthly = []) {
    const metrics = Object.fromEntries(comparisonMetrics(report, monthly).map(m => [m.id,m]));
    return (slotMetrics[key] || []).map(ids => {
      const available = ids.map(id => metrics[id]).filter(m => m.status === 'available');
      return {ids: available.map(m => m.id), text: available.map(m => `The ${m.label.toLowerCase()} is ${formatMetric(m)}.`).join(' ') || (key === 'key_findings_and_explanations' && ids[0] === 'company_revenue_change_pct' ? 'Period-over-period revenue change is unavailable for this scope. See the data notes below.' : '')};
    }).filter(item => item.text);
  }
  function render(root, report, options = {}) {
    if (report.report_type === 'inventory_operations') return renderInventory(root, report, options);
    root.replaceChildren();
    const defaults = defaultPresentation(report);
    const layout = {...defaults, ...(options.presentation || {}), chart_types:{...defaults.chart_types, ...options.presentation?.chart_types}};
    const monthly = options.monthly_decisions || [];
    const insights = options.insights;
    const shownMetrics = comparisonMetrics(report, monthly);
    const metrics = Object.fromEntries(shownMetrics.map(metric => [metric.id, metric]));
    const prefix = `sales-report-${++renderId}`;
    const sources = new Map();
    [report, ...monthly].forEach(group => group.metrics.forEach(m => m.evidence.forEach(e => { if (!sources.has(e.query_id)) sources.set(e.query_id, {...e, number:sources.size + 1}); })));
    (insights?.coverage_evidence || []).forEach(e => { if (!sources.has(e.query_id)) sources.set(e.query_id, {...e, number:sources.size+1}); });
    (insights?.documents || []).forEach(e => { if (!sources.has(e.citation_id)) sources.set(e.citation_id, {...e, source_table:e.source, number:sources.size + 1}); });
    const citeIds = (element, ids) => {
      const identifiers = new Set(ids.filter(id => sources.has(id)));
      if (!identifiers.size) return;
      const sup = node('sup', undefined, 'sales-citation');
      identifiers.forEach(id => {
        const source = sources.get(id);
        const link = node('a', `[${source.number}]`);
        link.href = `#${prefix}-source-${source.number}`;
        link.title = `View source ${source.number}`;
        link.setAttribute('aria-label', `View citation ${source.number}`);
        sup.append(link);
      });
      element.append(sup);
    };
    const cite = (element, ids, values = metrics) => citeIds(element, ids.flatMap(id => values[id]?.evidence.map(e => e.query_id) || []));
    root.append(node('h2', options.title || 'Sales Performance Report'));
    const end = new Date(report.request.period.end_exclusive + 'T00:00:00Z');
    end.setUTCDate(end.getUTCDate() - 1);
    root.append(node('p', `${report.request.period.start} to ${end.toISOString().slice(0,10)}`, 'sales-report-period'));
    for (const key of layout.section_order) {
      if (layout.hidden_sections.includes(key)) continue;
      const index = Object.keys(report.sections).indexOf(key);
      const section = node('section', undefined, 'sales-report-section');
      section.dataset.sectionId = key;
      section.append(node('h3', sectionTitles[index]));
      if (Object.hasOwn(layout.text_edits, key)) {
        section.append(node('small', 'Edited by you', 'sales-edited-label'));
        layout.text_edits[key].split('\n').filter(Boolean).forEach(line => section.append(node('p', line)));
      } else if (key === 'sales_kpis') {
        const grid = node('dl', undefined, 'sales-report-kpis');
        shownMetrics.forEach(metric => {
          const item = node('div');
          const label = node('dt', metric.label);
          cite(label, [metric.id]);
          item.append(label, node('dd', formatMetric(metric)));
          if (metric.value === null) {
            const reason = node('a', 'Why unavailable?', 'sales-data-note-link');
            reason.href = `#${prefix}-notes`; item.append(reason);
          }
          grid.append(item);
        });
        section.append(grid);
      } else if (key === 'decision_support') {
        let detailRoot = section;
        if (insights) {
          section.append(node('p', insights.decision_summary));
          insights.actions.forEach(action => {
            const card = node('article', undefined, 'sales-decision');
            const title = node('h4', action.title); citeIds(title, action.citations);
            card.append(title, node('p', action.action), node('p', `Periods: ${action.periods.join(', ')}`)); section.append(card);
          });
          if (!insights.actions.length) section.append(node('p', 'No rule action is available from the observed inputs. See Data needed below for the specific gaps.'));
          detailRoot = node('details'); detailRoot.append(node('summary','View all rule evaluations')); section.append(detailRoot);
        }
        if (monthly.length) section.append(node('p', 'Existing rules are evaluated for each month against its preceding calendar month.'));
        (monthly.length ? monthly : [report]).forEach(group => {
        const values = Object.fromEntries(group.metrics.map(m => [m.id, m]));
        if (group.period) detailRoot.append(node('h4', group.period.start.slice(0,7)));
        group.decisions.forEach(rule => {
          const item = node('article', undefined, 'sales-decision');
          const title = node('h4', rule.title); cite(title, rule.required_metric_ids, values);
          item.append(title);
          let text = rule.triggered === true ? rule.action : rule.triggered === false ? 'Evaluated: this predefined risk condition was not met.' : rule.id === 'S04' ? 'A no-trigger conclusion is withheld because at least one comparison rule cannot be evaluated.' : ['S01','S03'].includes(rule.id) ? 'Cannot evaluate this comparison with the selected scope and available baseline. See the data notes below.' : 'Cannot evaluate: current-period revenue or gross profit is unavailable.';
          if (rule.id === 'S02' && rule.triggered !== null) text += ` Gross profit is ${formatMetric(values.company_gross_profit)} and revenue is ${formatMetric(values.company_revenue)}.`;
          item.append(node('p', text)); detailRoot.append(item);
        });
        });
      } else if (key !== 'performance_analysis') {
        narrative(report, key, monthly).filter(item => key !== 'key_findings_and_explanations' || !insights?.findings.length || !item.text.startsWith('Period-over-period')).forEach(item => {
          const paragraph = node('p', item.text); cite(paragraph, item.ids); section.append(paragraph);
        });
        if (key === 'key_findings_and_explanations' && insights) {
          insights.findings.forEach(item => { const paragraph = node('p', item.text); citeIds(paragraph, item.citations); section.append(paragraph); });
          if (insights.document_context.length) {
            section.append(node('h4', 'Retrieved document context'), node('p', 'Quoted source context; relevance to the reported movement and causality are not established.'));
            insights.document_context.forEach(item => { const quote = node('blockquote',item.text); citeIds(quote,item.citations); section.append(quote); });
          } else section.append(node('p', 'No usable documentary explanation was retrieved. SQL findings and rule evaluations remain available independently. See Data needed below.'));
        }
      }
      if (key === 'performance_analysis') {
        const grid = node('div', undefined, 'sales-report-widgets');
        report.dashboard.widgets.filter(w => !['sales_kpis','order_kpis'].includes(w.id)).forEach(fixed => {
          const widget = {...fixed, type:layout.chart_types[fixed.id] || fixed.type, data:calendarRows(fixed, report.request)};
          const item = node('article', undefined, 'sales-report-widget');
          item.dataset.widgetId = widget.id; item.dataset.chartType = widget.type;
          const title = node('h4', widget.title); cite(title, widget.metric_ids); item.append(title);
          if (widget.type === 'kpi_row') {
            widget.metric_ids.forEach(id => {
              if (widget.metric_ids.length > 1) item.append(node('p',metrics[id].label,'sales-chart-legend'));
              item.append(node('p', formatMetric(metrics[id]), 'sales-widget-value'));
            });
          } else if (widget.type === 'table') item.append(dataTable(widget, metrics));
          else {
            item.append(chart(widget, report.request.granularity));
            item.append(node('p', widget.metric_ids.map(id => metrics[id].label).join(' ? '), 'sales-chart-legend'));
            const table = node('details'); table.append(node('summary', 'View chart data'), dataTable(widget, metrics)); item.append(table);
          }
          grid.append(item);
        });
        section.append(grid);
      }
      root.append(section);
    }
    const footnotes = node('footer', undefined, 'sales-report-footnotes');
    footnotes.append(node('h3', 'Sources'));
    sources.forEach(source => {
      const item = node('article', undefined, 'sales-source'); item.id = `${prefix}-source-${source.number}`; item.tabIndex = -1;
      item.append(node('h4', `[${source.number}] ${source.source_table}`));
      if (source.source_type === 'document') {
        item.append(node('p', source.metadata?.section_title || 'Role-authorized retrieved document passage.'), node('p',source.content));
      } else {
        const period = source.filters?.period || report.request.period;
        item.append(node('p', `Validated SQL evidence for ${period.start} to ${period.end_exclusive} (end excluded).`));
      }
      footnotes.append(item);
    });
    if (!sources.size) footnotes.append(node('p', 'No source observations were returned for this period.'));
    const notes = node('section'); notes.id = `${prefix}-notes`; notes.tabIndex = -1; notes.append(node('h3', 'Data notes'));
    notes.append(node('p', 'Amounts are displayed in VND as requested. The source has no currency tag; no currency conversion has been applied.'));
    if (insights) {
      notes.append(node('h4', 'Data needed'));
      insights.data_needs.forEach(text => { const paragraph = node('p',text); if (text.startsWith('Missing or incomplete commerce.sales')) citeIds(paragraph,(insights.coverage_evidence || []).map(e=>e.query_id)); notes.append(paragraph); });
    }
    if (monthly.length && report.request.granularity === 'month') notes.append(node('p', 'The month-over-month KPI compares the latest observed month with its preceding calendar month. Totals cover the full requested period. Incomplete comparisons remain unavailable.'));
    monthly.forEach(group => {
      if (group.comparison.comparable === true && group.metrics.find(m => m.id === 'company_revenue_change_pct').value !== null) return;
      const c = group.coverage;
      notes.append(node('p', `${group.period.start.slice(0,7)} decision baseline: current month ${c.current_days ?? 'unknown'}/${c.expected_current_days ?? 'unknown'} daily records; preceding month ${c.prior_days ?? 'unknown'}/${c.expected_prior_days ?? 'unknown'}. Missing coverage or zero prior revenue prevents growth comparisons.`));
    });
    if (report.dashboard.widgets.some(w => w.x_dimension === 'period' && w.type !== 'kpi_row' && calendarRows(w,report.request).length > w.data.length)) {
      notes.append(node('p','Unobserved calendar periods are shown as gaps, not zero values.'));
    }
    const hasDetailed = report.data_quality.limitations.some(note => note.startsWith('Period-over-period comparison'));
    report.data_quality.limitations.forEach(note => {
      if (note.startsWith('Missing count describes') || hasDetailed && note.startsWith('Company daily coverage')) return;
      notes.append(node('p', note.startsWith('Synthetic commerce') ? 'Synthetic commerce demonstration data. Company sales and delivered-order sales are independent sources.' : note));
    });
    footnotes.append(notes); root.append(footnotes);
  }
  const inventoryTitles = {operations_summary:'Operations Summary', snapshot_scorecard:'Inventory Snapshot Scorecard', product_risks:'Product Risks', fulfillment_and_returns:'Fulfillment & Returns', policy_evidence:'Policy Evidence', fixed_decisions:'Fixed Decision Support', data_quality:'Data Quality'};
  function renderInventory(root, report, options) {
    root.replaceChildren();
    const metrics = Object.fromEntries(report.metrics.map(m => [m.id,m]));
    const prefix = `inventory-report-${++renderId}`;
    const sources = new Map();
    report.metrics.forEach(m => m.evidence.forEach(e => sources.set(e.query_id,e)));
    const widgetSources = new Map();
    report.data_quality.limitations.forEach(note => {
      const match = note.match(/^Dashboard source \[([a-f0-9]+)\] (\w+): (.*)$/);
      if (match) {
        const [,id,widget,description] = match;
        const source = {query_id:id,source_table:description,filters:{},row_count:null};
        widgetSources.set(widget,[source]); sources.set(id,source);
      }
    });
    const cite = (target, evidence) => {
      [...new Set(evidence.map(e => e.query_id))].forEach(id => {
        const link = node('a',` [${id}]`); link.href = `#${prefix}-${id}`;
        link.setAttribute('aria-label',`View source ${id}`); target.append(link);
      });
    };
    root.append(node('h2', options.title || 'Inventory & Operations Report'));
    root.append(node('p',`${report.request.period.start} to ${report.request.period.end_exclusive} (end excluded)`, 'sales-report-period'));
    const ownership = {inventory_kpis:'snapshot_scorecard', inventory_flag_distribution:'product_risks', stockout_product_table:'product_risks', operations_kpis:'fulfillment_and_returns', inventory_snapshots:'fulfillment_and_returns'};
    Object.entries(inventoryTitles).forEach(([id,title]) => {
      const section = node('section',undefined,'sales-report-section'); section.dataset.sectionId = id;
      section.append(node('h3',title));
      if (id === 'operations_summary') {
        report.data_quality.limitations.filter(n => n.startsWith('Selected snapshot:') || n.startsWith('Snapshot completeness')).forEach(n => section.append(node('p',n)));
        const summary = node('p', report.metrics.slice(0,6).map(m => `${m.label}: ${formatMetric(m)}`).join('. '));
        cite(summary,report.metrics.slice(0,6).flatMap(m=>m.evidence)); section.append(summary);
      }
      if (id === 'snapshot_scorecard') {
        report.metrics.filter(m => ['stockout_flag_pct','overstock_products'].includes(m.id)).forEach(m => {const p = node('p',`${m.label}: ${formatMetric(m)} (${m.status})`); cite(p,m.evidence); section.append(p);});
      }
      const grid = node('div',undefined,'sales-report-widgets');
      report.dashboard.widgets.filter(w => ownership[w.id] === id).forEach(widget => {
        const article = node('article',undefined,'sales-report-widget'); article.dataset.widgetId=widget.id; article.dataset.chartType=widget.type;
        const heading=node('h4',widget.title); cite(heading,widgetSources.get(widget.id) || widget.metric_ids.flatMap(key=>metrics[key].evidence)); article.append(heading);
        if (widget.type === 'kpi_row') widget.metric_ids.forEach(key=>article.append(node('p',`${metrics[key].label}: ${formatMetric(metrics[key])} (${metrics[key].status})`)));
        else if (widget.type === 'table') article.append(dataTable(widget,metrics));
        else {article.append(chart(widget, report.request.granularity)); const data=node('details');data.append(node('summary','View chart data'),dataTable(widget,metrics));article.append(data);}
        if (widget.notes) article.append(node('p',widget.notes)); grid.append(article);
      });
      if (grid.children.length) section.append(grid);
      if (id === 'policy_evidence') {
        report.data_quality.limitations.filter(n=>n.startsWith('Policy Evidence:') || n.startsWith('Policy source [')).forEach(n=>section.append(node('p',n)));
      }
      if (id === 'fixed_decisions') report.decisions.forEach(rule=>{
        const article=node('article',undefined,'sales-decision');article.append(node('h4',`${rule.id}: ${rule.title}`),node('p',rule.condition));
        const text=node('p',rule.triggered === true ? rule.action : rule.triggered === false ? 'Evaluated: condition not met.' : 'Unavailable: insufficient validated snapshot evidence or coverage.');cite(text,rule.evidence);article.append(text);section.append(article);
      });
      if (id === 'data_quality') report.data_quality.limitations.filter(n=>!n.startsWith('Policy source [')).forEach(n=>section.append(node('p',n)));
      root.append(section);
    });
    const footer=node('footer',undefined,'sales-report-footnotes');footer.append(node('h3','Sources'));
    sources.forEach((source,id)=>{const article=node('article',undefined,'sales-source');article.id=`${prefix}-${id}`;article.tabIndex=-1;
      article.append(node('h4',`[${id}] ${source.source_table}`),node('p',`Validated SQL; ${source.row_count} result rows. Snapshot: ${source.filters.snapshot_date || 'period events'}.`));footer.append(article);});
    root.append(footer);
  }
  return {render, defaultPresentation, narrative, formatMetric, sectionTitles, inventoryTitles};
})();
