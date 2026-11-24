/* Fixed sales report rendering. All source text stays in text nodes. */
const SalesPerformanceReport = (() => {
  const node = (tag, text, className) => {
    const element = document.createElement(tag);
    if (text !== undefined) element.textContent = text;
    if (className) element.className = className;
    return element;
  };
  const format = (value, vi = false) => value == null ? (vi ? 'Không có dữ liệu' : 'Unavailable')
    : new Intl.NumberFormat(vi ? 'vi-VN' : undefined, { maximumFractionDigits: 2 }).format(value);
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

  function dataTable(widget, metrics, vi = false) {
    const wrap = node('div', undefined, 'sales-report-table');
    const table = node('table');
    table.append(node('caption', widget.title));
    const head = node('thead');
    const headings = node('tr');
    const dimensions = vi ? {period:'Kỳ',category:'Danh mục',product:'Sản phẩm',snapshot_date:'Ngày chốt',dimension:'Nhóm'}
      : {period:'Period',category:'Category',product:'Product',snapshot_date:'Snapshot date',dimension:'Breakdown'};
    const dimensionLabel = dimensions[widget.x_dimension] || widget.x_dimension.replaceAll('_',' ');
    for (const label of [dimensionLabel, ...widget.metric_ids.map(id => metrics[id].label)]) {
      const th = node('th', label); th.scope = 'col'; headings.append(th);
    }
    head.append(headings); table.append(head);
    const body = node('tbody');
    for (const row of widget.data) {
      const tr = node('tr');
      tr.append(node('td', row[widget.x_dimension] ?? (vi ? 'Chưa rõ' : 'Unknown')));
      widget.metric_ids.forEach(id => tr.append(node('td', formatMetric(metrics[id], row[id]))));
      body.append(tr);
    }
    table.append(body); wrap.append(table); return wrap;
  }

  function chart(widget, granularity, metrics = {}, vi = false) {
    const values = widget.data.flatMap(row => widget.metric_ids.map(id => row[id])).filter(value => typeof value === 'number' && Number.isFinite(value));
    if (!values.length) return node('p', vi ? 'Không có dữ liệu cho biểu đồ.' : 'No chart data available.');
    const min = Math.min(0, ...values), max = Math.max(0, ...values);
    const range = max - min || 1;
    const x = index => 48 + (index + 0.5) * 520 / widget.data.length;
    const y = value => 180 - (value - min) / range * 150;
    const svg = svgNode('svg', { viewBox: '0 0 600 225', role: 'img', 'aria-label': `${widget.title}. ${vi ? 'Số liệu nằm trong bảng bên dưới.' : 'Values in the data table below.'}` });
    const unknown = vi ? 'Chưa rõ' : 'Unknown';
    svg.append(svgNode('line', { x1: 48, x2: 568, y1: y(0), y2: y(0), stroke: 'currentColor' }));
    for (const [index, value] of [[0, max], [1, min]]) {
      const label = svgNode('text', { x: 4, y: index ? 184 : 28, 'font-size': 11, fill: 'currentColor' });
      label.textContent = format(value, vi); svg.append(label);
    }
    widget.metric_ids.forEach((id, series) => {
      const color = ['#0a66d8','#64748b','#7aa8e8'][series % 3];
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
        title.textContent = `${row[widget.x_dimension] ?? unknown}: ${metrics[id]?.label || id} ${format(value, vi)}`;
        mark.append(title);
        svg.append(mark);
        segment.push(`${x(index)},${y(value)}`);
      });
      if (widget.type === 'line') flush();
    });
    widget.data.forEach((row, index) => {
      if (widget.data.length > 12 && index && index !== widget.data.length - 1 && index % Math.ceil(widget.data.length / 4)) return;
      const label = svgNode('text', { x: x(index), y: 210, 'text-anchor': 'middle', 'font-size': 10, fill: 'currentColor' });
      label.textContent = widget.x_dimension === 'period' ? row.period.slice(0,7) : row[widget.x_dimension] ?? unknown; svg.append(label);
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
  const vietnamese = (value = '') => /[ăâđêôơưáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ]|\b(?:bao cao|doanh thu|ton kho)\b|\b(?:thang|quy)\s+\d|\b(?:tao|lap|xuat|lam|viet)\s+(?:(?:a|an|the|new|monthly|quarterly|annual)\s+)*(?:inventory|sales|financial|report|dashboard)\b/iu
    .test(value.normalize('NFC').replace(/["“][^"”]*["”]|'[^']*'/gu, ''));
  const sectionTitlesVi = ['Tóm tắt điều hành', 'Chỉ số bán hàng', 'Phân tích kết quả', 'Phát hiện chính và diễn giải', 'Hỗ trợ ra quyết định'];
  const formatMetric = (metric, value = metric.value) => format(value, vietnamese(metric.label)) + (value == null ? '' : metric.unit === 'percent' ? '%' : metric.unit.startsWith('unknown_currency') ? ' VND' : '');
  const slotMetrics = {
    executive_summary: [['company_revenue','company_revenue_change_pct'],['company_gross_profit','company_gross_margin_pct'],['order_count']],
    key_findings_and_explanations: [['company_revenue_change_pct'],['company_gross_profit','company_gross_margin_pct'],['order_count','delivered_average_order_value']],
  };
  function comparisonMetrics(report, monthly = []) {
    if (!monthly.length || report.request.granularity !== 'month') return report.metrics;
    const observed = monthly.filter(group => group.metrics.some(m => m.id === 'company_revenue' && m.value !== null));
    const selected = (observed.length ? observed : monthly).at(-1);
    const prior = new Date(selected.period.start + 'T00:00:00Z'); prior.setUTCMonth(prior.getUTCMonth()-1);
    const period = selected.period.start.slice(0,7), baseline = prior.toISOString().slice(0,7);
    const label = vietnamese(report.metrics[0].label)
      ? `Thay đổi doanh thu công ty theo tháng (${period.slice(5)}/${period.slice(0,4)} so với ${baseline.slice(5)}/${baseline.slice(0,4)})`
      : `Company revenue month-over-month change (${period} vs ${baseline})`;
    const change = {...selected.metrics.find(m => m.id === 'company_revenue_change_pct'), label};
    return report.metrics.map(m => m.id === change.id ? change : m);
  }
  function narrative(report, key, monthly = []) {
    const vi = vietnamese(report.metrics[0]?.label);
    const metrics = Object.fromEntries(comparisonMetrics(report, monthly).map(m => [m.id,m]));
    return (slotMetrics[key] || []).map(ids => {
      const available = ids.map(id => metrics[id]).filter(m => m.status === 'available');
      const text = available.map(m => vi ? `${m.label}: ${formatMetric(m)}.` : `The ${m.label.toLowerCase()} is ${formatMetric(m)}.`).join(' ');
      const missingChange = key === 'key_findings_and_explanations' && ids[0] === 'company_revenue_change_pct';
      const unavailable = vi ? 'Chưa đủ dữ liệu để so sánh doanh thu giữa các kỳ. Xem ghi chú dữ liệu bên dưới.'
        : 'Period-over-period revenue change is unavailable for this scope. See the data notes below.';
      return {ids: available.map(m => m.id), text: text || (missingChange ? unavailable : '')};
    }).filter(item => item.text);
  }
  function numberedCitations(sources, prefix, vi = false) {
    return (element, ids) => {
      const identifiers = new Set(ids.filter(id => sources.has(id)));
      if (!identifiers.size) return;
      const sup = node('sup', undefined, 'sales-citation');
      identifiers.forEach(id => {
        const source = sources.get(id);
        const link = node('a', `[${source.number}]`);
        link.href = `#${prefix}-source-${source.number}`;
        link.title = vi ? `Xem nguồn ${source.number}` : `View source ${source.number}`;
        link.setAttribute('aria-label', vi ? `Xem trích dẫn ${source.number}` : `View citation ${source.number}`);
        sup.append(link);
      });
      element.append(sup);
    };
  }
  function render(root, report, options = {}) {
    if (report.report_type === 'inventory_and_sales') {
      const vi = vietnamese(report.reports.sales_performance.metrics[0]?.label);
      const title = options.title || (vi ? 'Báo cáo tồn kho và kết quả bán hàng' : 'Inventory and Sales Performance Report');
      root.setAttribute('lang', vi ? 'vi' : 'en');
      root.replaceChildren(node('h2', title));
      for (const kind of ['inventory_operations', 'sales_performance']) {
        const section = node('section');
        section.dataset.reportType = kind;
        render(section, report.reports[kind], {...options, title: undefined, insights: options.insights?.[kind]});
        root.append(section);
      }
      return;
    }
    if (report.report_type === 'inventory_operations') return renderInventory(root, report, options);
    root.replaceChildren();
    const vi = vietnamese(report.metrics[0]?.label);
    root.setAttribute('lang', vi ? 'vi' : 'en');
    const label = (english, translated) => vi ? translated : english;
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
    const citeIds = numberedCitations(sources, prefix, vi);
    const cite = (element, ids, values = metrics) => citeIds(element, ids.flatMap(id => values[id]?.evidence.map(e => e.query_id) || []));
    root.append(node('h2', options.title || label('Sales Performance Report', 'Báo cáo kết quả bán hàng')));
    const end = new Date(report.request.period.end_exclusive + 'T00:00:00Z');
    end.setUTCDate(end.getUTCDate() - 1);
    root.append(node('p', `${report.request.period.start} ${label('to', 'đến')} ${end.toISOString().slice(0,10)}`, 'sales-report-period'));
    for (const key of layout.section_order) {
      if (layout.hidden_sections.includes(key)) continue;
      const index = Object.keys(report.sections).indexOf(key);
      const section = node('section', undefined, 'sales-report-section');
      section.dataset.sectionId = key;
      section.append(node('h3', (vi ? sectionTitlesVi : sectionTitles)[index]));
      if (Object.hasOwn(layout.text_edits, key)) {
        section.append(node('small', label('Edited by you', 'Do bạn chỉnh sửa'), 'sales-edited-label'));
        layout.text_edits[key].split('\n').filter(Boolean).forEach(line => section.append(node('p', line)));
      } else if (key === 'sales_kpis') {
        const grid = node('dl', undefined, 'sales-report-kpis');
        shownMetrics.forEach(metric => {
          const item = node('div');
          const label = node('dt', metric.label);
          cite(label, [metric.id]);
          item.append(label, node('dd', formatMetric(metric)));
          if (metric.value === null) {
            const reason = node('a', vi ? 'Vì sao thiếu dữ liệu?' : 'Why unavailable?', 'sales-data-note-link');
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
            card.append(title);
            if (action.why) card.append(node('p', `${label('Why review this', 'Lý do cần xem xét')}: ${action.why}`));
            card.append(node('p', `${label('Recommended next step', 'Đề xuất xử lý')}: ${action.action}`), node('p', `${label('Periods', 'Các kỳ')}: ${action.periods.join(', ')}`)); section.append(card);
          });
          if (!insights.actions.length) section.append(node('p', label('No rule action is available from the observed inputs. See Data needed below for the specific gaps.', 'Dữ liệu hiện có chưa đưa ra hành động theo quy tắc. Xem mục Dữ liệu cần bổ sung.')));
          detailRoot = node('details'); detailRoot.append(node('summary',label('View all rule evaluations','Xem kết quả đánh giá các quy tắc'))); section.append(detailRoot);
        }
        if (monthly.length) section.append(node('p', label('Existing rules are evaluated for each month against its preceding calendar month.', 'Các quy tắc so sánh từng tháng với tháng liền trước.')));
        (monthly.length ? monthly : [report]).forEach(group => {
        const values = Object.fromEntries(group.metrics.map(m => [m.id, m]));
        if (group.period) detailRoot.append(node('h4', group.period.start.slice(0,7)));
        group.decisions.forEach(rule => {
          const item = node('article', undefined, 'sales-decision');
          const title = node('h4', rule.title); cite(title, rule.required_metric_ids, values);
          item.append(title);
          let text = rule.triggered === true ? (insights?.rule_actions?.[rule.id] || rule.action)
            : rule.triggered === false ? label('Evaluated: this predefined risk condition was not met.', 'Kết quả đánh giá chưa thỏa điều kiện cảnh báo này.')
            : rule.id === 'S04' ? label('A no-trigger conclusion is withheld because at least one comparison rule cannot be evaluated.', 'Chưa thể kết luận vì ít nhất một quy tắc so sánh chưa đánh giá được.')
            : ['S01','S03'].includes(rule.id) ? label('Cannot evaluate this comparison with the selected scope and available baseline. See the data notes below.', 'Chưa đủ dữ liệu kỳ đối chiếu để đánh giá. Xem ghi chú dữ liệu bên dưới.')
            : label('Cannot evaluate: current-period revenue or gross profit is unavailable.', 'Chưa có doanh thu hoặc lợi nhuận gộp của kỳ hiện tại để đánh giá.');
          if (rule.id === 'S02' && rule.triggered !== null) {
            const profit = formatMetric(values.company_gross_profit), revenue = formatMetric(values.company_revenue);
            text += label(` Gross profit is ${profit} and revenue is ${revenue}.`, ` Lợi nhuận gộp: ${profit}. Doanh thu: ${revenue}.`);
          }
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
            section.append(node('h4', label('Retrieved document context', 'Bối cảnh từ tài liệu nguồn')), node('p', label('Quoted source context; relevance to the reported movement and causality are not established.', 'Các trích đoạn cung cấp bối cảnh. Mối liên hệ với biến động và nguyên nhân của biến động chưa được xác minh.')));
            insights.document_context.forEach(item => { const quote = node('blockquote',item.text); citeIds(quote,item.citations); section.append(quote); });
          } else section.append(node('p', label('No usable documentary explanation was retrieved. SQL findings and rule evaluations remain available independently. See Data needed below.', 'Chưa tìm thấy tài liệu giải thích biến động. Xem mục Dữ liệu cần bổ sung bên dưới.')));
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
          } else if (widget.type === 'table') item.append(dataTable(widget, metrics, vi));
          else {
            item.append(chart(widget, report.request.granularity, metrics, vi));
            item.append(node('p', widget.metric_ids.map(id => metrics[id].label).join(' · '), 'sales-chart-legend'));
            const table = node('details'); table.append(node('summary', label('View chart data', 'Xem dữ liệu biểu đồ')), dataTable(widget, metrics, vi)); item.append(table);
          }
          grid.append(item);
        });
        section.append(grid);
      }
      root.append(section);
    }
    const footnotes = node('footer', undefined, 'sales-report-footnotes');
    footnotes.append(node('h3', label('Sources', 'Nguồn dữ liệu')));
    sources.forEach(source => {
      const item = node('article', undefined, 'sales-source'); item.id = `${prefix}-source-${source.number}`; item.tabIndex = -1;
      item.append(node('h4', `[${source.number}] ${source.source_table}`));
      if (source.source_type === 'document') {
        item.append(node('p', source.metadata?.section_title || label('Role-authorized retrieved document passage.', 'Trích đoạn từ tài liệu được phép truy cập.')), node('p',source.content));
      } else {
        const period = source.filters?.period || report.request.period;
        item.append(node('p', label(`Validated SQL evidence for ${period.start} to ${period.end_exclusive} (end excluded).`, `Nguồn SQL đã xác minh từ ${period.start} đến trước ${period.end_exclusive}.`)));
      }
      footnotes.append(item);
    });
    if (!sources.size) footnotes.append(node('p', label('No source observations were returned for this period.', 'Nguồn không trả về dữ liệu cho kỳ này.')));
    const notes = node('section'); notes.id = `${prefix}-notes`; notes.tabIndex = -1; notes.append(node('h3', label('Data notes', 'Ghi chú dữ liệu')));
    notes.append(node('p', label('Amounts are displayed in VND as requested. The source has no currency tag; no currency conversion has been applied.',
      'Số tiền hiển thị theo đơn vị VND. Nguồn không ghi đơn vị tiền tệ và chưa áp dụng quy đổi.')));
    if (insights) {
      notes.append(node('h4', label('Data needed', 'Dữ liệu cần bổ sung')));
      insights.data_needs.forEach(text => { const paragraph = node('p',text); if (text.startsWith('Missing or incomplete commerce.sales') || text.startsWith('Thiếu dữ liệu commerce.sales')) citeIds(paragraph,(insights.coverage_evidence || []).map(e=>e.query_id)); notes.append(paragraph); });
    }
    if (monthly.length && report.request.granularity === 'month') notes.append(node('p', vietnamese(report.metrics[0].label)
      ? 'Chỉ số so sánh tháng mới nhất có dữ liệu doanh thu với tháng liền trước. Nếu thiếu dữ liệu để so sánh, chỉ số sẽ hiển thị là không có dữ liệu.'
      : 'The month-over-month KPI compares the latest observed month with its preceding calendar month. Totals cover the full requested period. Incomplete comparisons remain unavailable.'));
    monthly.forEach(group => {
      if (group.comparison.comparable === true && group.metrics.find(m => m.id === 'company_revenue_change_pct').value !== null) return;
      const c = group.coverage;
      const unknown = label('unknown', 'chưa rõ');
      const current = `${c.current_days ?? unknown}/${c.expected_current_days ?? unknown}`;
      const prior = `${c.prior_days ?? unknown}/${c.expected_prior_days ?? unknown}`;
      notes.append(node('p', label(`${group.period.start.slice(0,7)} decision baseline: current month ${current} daily records; preceding month ${prior}. Missing coverage or zero prior revenue prevents growth comparisons.`,
        `Kỳ đối chiếu ${group.period.start.slice(0,7)}: tháng hiện tại có ${current} ngày dữ liệu, tháng trước có ${prior} ngày. Cần đủ ngày và doanh thu tháng trước khác 0 để tính tỷ lệ thay đổi.`)));
    });
    if (insights?.data_notes) {
      insights.data_notes.forEach(note => notes.append(node('p', note)));
    } else if (report.dashboard.widgets.some(w => w.x_dimension === 'period' && w.type !== 'kpi_row' && calendarRows(w,report.request).length > w.data.length)) {
      notes.append(node('p','Unobserved calendar periods are shown as gaps, not zero values.'));
    }
    const hasDetailed = report.data_quality.limitations.some(note => note.startsWith('Period-over-period comparison'));
    if (!insights?.data_notes) report.data_quality.limitations.forEach(note => {
      if (note.startsWith('Missing count describes') || hasDetailed && note.startsWith('Company daily coverage')) return;
      notes.append(node('p', note.startsWith('Synthetic commerce') ? 'Synthetic commerce demonstration data. Company sales and delivered-order sales are independent sources.' : note));
    });
    footnotes.append(notes); root.append(footnotes);
  }
  const inventoryTitles = {operations_summary:'Operations Summary', snapshot_scorecard:'Inventory Snapshot Scorecard', product_risks:'Product Risks', fulfillment_and_returns:'Fulfillment & Returns', policy_evidence:'Policy Evidence', fixed_decisions:'Fixed Decision Support', data_quality:'Data Quality'};
  const inventorySourceName = (source, copy) => source.split(/,\s*/).map(name => copy({
    'commerce.inventory':'Inventory records', 'commerce.products':'Product catalog', 'commerce.returns':'Return records',
    'commerce.orders':'Order records', 'commerce.shipments':'Shipment records', 'commerce.reviews':'Customer reviews',
  }[name]) || name.replace(/^.*[\\/]/,'').replace(/\.(pdf|docx?|xlsx?|csv|md|txt)$/i,'').replace(/^\d{2}[_ -]+/,'').replaceAll('_',' ')).join(', ');
  const inventoryValue = (metric, vi) => formatMetric(metric) + (metric.value === null ? '' :
    ({units:vi ? ' đơn vị' : ' units',calendar_days:vi ? ' ngày' : ' days',rating_1_to_5:' / 5'}[metric.unit] || ''));
  const inventoryUnavailableReason = metric => ({no_data:'No matching observations for these dates.',access_denied:'Source access is restricted.',unresolved:'The metric definition or reporting scope is unresolved.'}[metric.status] || 'Unavailable for this scope or source.');
  function inventoryNotes(report) {
    const labels = {snapshot:'Inventory snapshot',coverage:'Snapshot coverage',inventory_flag_distribution:'Flag distribution',stockout_product_table:'Stockout product list',inventory_snapshots:'Snapshot history',returns:'Returned orders',shipments:'Shipment duration',reviews:'Review ratings'};
    const notes = report.data_quality.limitations.flatMap(note => {
      if (/^(Dashboard source \[|Policy source \[|Policy Evidence:)/.test(note)) return [];
      if (note.startsWith('Synthetic commerce')) return ['Synthetic commerce demonstration data. Transaction records and historical catalog membership are not certified complete. No forecasts, service commitments, reorder quantities or causal conclusions are inferred.'];
      if (note.startsWith('Snapshot policy:')) return ['Inventory balances use one observed snapshot before the reporting period ends. Older snapshots are labelled stale; the history chart shows each snapshot independently.'];
      if (note.startsWith('days_of_supply') || note.startsWith('fill_rate')) return ['Days of supply, fill rate and sell-through metrics are excluded because their source definitions are not validated.'];
      if (note.startsWith('stockout/reorder/overstock')) return ['Stockout, reorder and overstock flags can overlap; do not add these product counts together.'];
      if (note.startsWith('Snapshot completeness')) return ['Coverage is checked against the current product catalog; historical membership is not certified. ' + (report.data_quality.partial_period === false ? 'Catalog coverage is verified for the selected snapshot.' : 'Complete snapshot coverage is unverified or incomplete; the no-exception conclusion is withheld.')];
      if (note === 'Inventory snapshot selection query unavailable.') return ['A snapshot date could not be verified from the available inventory records.'];
      const metric = report.metrics.find(m => note.startsWith(m.id + ': not_available'));
      if (metric) return [`${metric.label}: unavailable for this breakdown. No approximation has been applied.`];
      const key = note.split(':')[0], label = labels[key];
      if (label && note.includes('access denied')) return [`${label}: source access is restricted.`];
      if (label && note.includes('validated source query unavailable')) return [`${label}: the source could not be retrieved or verified.`];
      if (label && note.includes('200-row')) return [`${label}: the first 200 results are shown; additional records may be omitted.`];
      return [note];
    });
    report.metrics.filter(m=>m.value===null).forEach(metric=>{
      if (!notes.some(note=>note.startsWith(metric.label+':'))) notes.push(`${metric.label}: ${inventoryUnavailableReason(metric)}`);
    });
    return [...new Set(notes)];
  }
  function renderInventory(root, report, options) {
    root.replaceChildren();
    const vi = vietnamese(report.metrics[0]?.label);
    root.setAttribute('lang', vi ? 'vi' : 'en');
    const copy = text => options.insights?.copy?.[text] ?? text;
    const metrics = Object.fromEntries(report.metrics.map(m => [m.id,m]));
    const prefix = `inventory-report-${++renderId}`;
    const sources = new Map();
    const addSource = (id, source) => { if (!sources.has(id)) sources.set(id,{...source,number:sources.size+1}); };
    report.metrics.forEach(m => m.evidence.forEach(e => addSource(e.query_id,e)));
    const widgetSources = new Map();
    report.data_quality.limitations.forEach(note => {
      const match = note.match(/^Dashboard source \[([a-f0-9]+)\] (\w+): (.*)$/);
      if (match) {
        const [,id,widget,description] = match;
        widgetSources.set(widget,[id]);
        addSource(id,{source_table:description.split(';')[0],title:report.dashboard.widgets.find(w=>w.id===widget)?.title,
                      filters:widget==='inventory_snapshots' ? {} : {snapshot_date:report.data_quality.coverage_end}});
      }
    });
    const documents = options.inventory_context ? (options.inventory_context.documents || []) : report.data_quality.limitations.flatMap(note => {
      const match=note.match(/^Policy source \[([^\]]+)\] document [^:]+: ([\s\S]*)$/);
      return match ? [{citation_id:match[1],source:copy('Retrieved inventory policy'),content:match[2],metadata:{}}] : [];
    });
    documents.forEach(e=>addSource(e.citation_id,{...e,source_table:e.source,source_type:'document'}));
    const citeIds = numberedCitations(sources,prefix,vi);
    const cite = (target,evidence) => citeIds(target,evidence.map(e=>e.query_id));
    const cards = ids => {
      const grid=node('dl',undefined,'sales-report-kpis');
      ids.forEach(id=>{
        const metric=metrics[id],item=node('div'),label=node('dt',metric.label); cite(label,metric.evidence);
        item.append(label,node('dd',inventoryValue(metric,vi)));
        if (metric.value===null) {
          item.append(node('small',copy(inventoryUnavailableReason(metric))));
          const reason=node('a',copy('Why unavailable?'),'sales-data-note-link');reason.href=`#${prefix}-notes`;
          item.append(reason);
        }
        grid.append(item);
      });
      return grid;
    };
    root.append(node('h2', options.title || copy('Inventory & Operations Report')));
    const end=new Date(report.request.period.end_exclusive+'T00:00:00Z');end.setUTCDate(end.getUTCDate()-1);
    root.append(node('p',`${report.request.period.start} ${vi ? 'đến' : 'to'} ${end.toISOString().slice(0,10)}`, 'sales-report-period'));
    const ownership = {inventory_kpis:'snapshot_scorecard', inventory_flag_distribution:'product_risks', stockout_product_table:'product_risks', operations_kpis:'fulfillment_and_returns', inventory_snapshots:'fulfillment_and_returns'};
    const notes=options.insights?.data_notes || inventoryNotes(report);
    const selectedSnapshot = note => note.startsWith(copy('Selected snapshot:'));
    Object.entries(inventoryTitles).forEach(([id,title]) => {
      const section = node('section',undefined,'sales-report-section'); section.dataset.sectionId = id;
      if (id==='data_quality') {
        section.id=`${prefix}-notes`;section.tabIndex=-1;
        const detail=node('details');detail.append(node('summary',copy('Validation and source details')));
        (options.insights?.validation_summary || []).forEach(text=>detail.append(node('p',text)));
        notes.filter(n=>!selectedSnapshot(n)).forEach(text=>detail.append(node('p',text)));
        section.append(detail);root.append(section);return;
      }
      section.append(node('h3',copy(title)));
      if (id === 'operations_summary') {
        notes.filter(selectedSnapshot).forEach(n=>section.append(node('p',n)));
        section.append(node('p',report.request.granularity==='year'
          ? copy('This annual report uses one inventory snapshot. It does not add stock balances across months.')
          : copy('Inventory figures describe one snapshot.')));
        section.append(node('p',copy('Available fulfillment, return and review records are filtered to the requested reporting dates; complete transaction coverage is unverified.')));
        const stock = inventoryValue(metrics.stock_on_hand,vi), products = format(metrics.observed_products.value,vi);
        const summary=node('p',metrics.stock_on_hand.value!==null && metrics.observed_products.value!==null
          ? vi ? `Tại ngày chốt có ${stock} tồn kho trên ${products} sản phẩm được ghi nhận.` : `The selected snapshot records ${stock} across ${products} observed products.`
          : copy('Snapshot totals are unavailable for this reporting period. Open Validation and source details for the missing inputs.'));
        cite(summary,[...metrics.stock_on_hand.evidence,...metrics.observed_products.evidence]);section.append(summary);
      }
      const grid = node('div',undefined,'sales-report-widgets');
      report.dashboard.widgets.filter(w => ownership[w.id] === id).forEach(widget => {
        const article = node('article',undefined,'sales-report-widget'); article.dataset.widgetId=widget.id; article.dataset.chartType=widget.type;
        if (widget.type==='kpi_row') article.className+=' inventory-kpi-widget';
        const evidenceIds=widgetSources.get(widget.id) || (widget.type==='kpi_row' ? widget.metric_ids.flatMap(key=>metrics[key].evidence.map(e=>e.query_id)) : []);
        const heading=node('h4',widget.title);citeIds(heading,evidenceIds);article.append(heading);
        if (widget.type === 'kpi_row') article.append(cards(widget.metric_ids));
        else if (widget.type === 'table') {
          article.append(widget.data.length ? dataTable(widget,metrics,vi) : node('p',metrics.stockout_products.value===0
            ? copy('No stockout flags were observed at the selected snapshot.') : copy('The stockout product list is unavailable for this scope.')));
        } else {
          article.append(chart(widget,report.request.granularity,metrics,vi));
          const legend=node('div',undefined,'inventory-chart-legend');
          widget.metric_ids.forEach((key,index)=>legend.append(node('span',metrics[key].label,`inventory-series-${index}`)));article.append(legend);
          const data=node('details');data.append(node('summary',copy('View chart data')),dataTable(widget,metrics,vi));article.append(data);
        }
        if (widget.id==='inventory_flag_distribution') article.append(node('p',copy('A product may carry more than one flag.'),'sales-chart-legend'));
        if (widget.id==='inventory_snapshots') article.append(node('p',copy('Each point is an independent snapshot; stock balances are never added across dates.'),'sales-chart-legend'));
        grid.append(article);
      });
      if (grid.children.length) section.append(grid);
      if (id==='snapshot_scorecard') section.append(cards(['stockout_flag_pct','overstock_products']));
      if (id === 'policy_evidence') {
        if (documents.length) {
          section.append(node('p',copy('Quoted policy context. These passages do not by themselves verify approval, effective dates or compliance.')));
          documents.forEach(e=>{const quote=node('blockquote',e.content);citeIds(quote,[e.citation_id]);section.append(quote);});
        } else {
          const status=options.inventory_context?.retrieval_status || report.data_quality.limitations.find(n=>n.startsWith('Policy Evidence:'))?.split(': ')[1].split('.')[0];
          section.append(node('p',status==='access_denied' ? copy('Policy evidence is unavailable because document access is restricted.')
            : status==='no_evidence' ? copy('No matching authorized inventory policy passage was retrieved.') : copy('Policy evidence could not be retrieved. No policy-compliance conclusion has been added.')));
        }
      }
      if (id === 'fixed_decisions') {
        const triggered=report.decisions.filter(rule=>rule.triggered===true);
        if (!triggered.length) section.append(node('p',copy('No recommendation can be confirmed from the available inputs. Check the selected snapshot and recorded flags in Validation and source details.')));
        triggered.forEach(rule=>{
          const action=options.insights?.actions?.find(item=>item.title===rule.title);
          const article=node('article',undefined,'sales-decision'),heading=node('h4',rule.title);cite(heading,rule.evidence);article.append(heading);
          if (action?.why) article.append(node('p',`${copy('Why review this:')} ${action.why}`));
          article.append(node('p',`${copy('Recommended next step:')} ${action?.action || rule.action}`));section.append(article);
        });
        const detail=node('details');detail.append(node('summary',copy('View all rule evaluations')));
        report.decisions.forEach(rule=>{
          const article=node('article',undefined,'sales-decision'),heading=node('h4',rule.title);cite(heading,rule.evidence);
          article.append(heading,node('p',rule.triggered===true ? copy('Triggered: the recorded inputs meet this predefined condition.')
            : rule.triggered===false ? copy('Evaluated: this predefined condition was not met.')
            : rule.id==='I04' ? copy('A no-exception conclusion is withheld because snapshot coverage or flag evidence is incomplete.')
            : copy('Cannot evaluate: the required recorded flag count is unavailable.')));detail.append(article);
        });section.append(detail);
      }
      root.append(section);
    });
    const footer=node('footer',undefined,'sales-report-footnotes');footer.append(node('h3',copy('Sources')));
    sources.forEach(source=>{
      const article=node('article',undefined,'sales-source');article.id=`${prefix}-source-${source.number}`;article.tabIndex=-1;
      article.append(node('h4',`[${source.number}] ${inventorySourceName(source.source_table,copy)}`));
      if (source.source_type==='document') article.append(node('p',source.metadata?.section_title || copy('Role-authorized policy passage.')));
      else article.append(node('p',source.title || (source.filters?.snapshot_date ? `${copy('Selected snapshot:')} ${source.filters.snapshot_date}.` : copy('Source queried for the requested reporting dates.'))));
      footer.append(article);
    });
    if (!sources.size) footer.append(node('p',copy('No source observations were returned for this period.')));
    root.append(footer);
  }
  return {render, defaultPresentation, narrative, formatMetric, sectionTitles, sectionTitlesVi, inventoryTitles, vietnamese};
})();
