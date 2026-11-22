/* Reports have their own library; presentation edits never change SQL facts. */
(() => {
  const el = id => document.getElementById(id);
  let selected = null, epoch = 0, loaded = false, busy = false, vi = false;
  const copyVi = {
    'Generating report from authorized sources...': 'Đang tạo báo cáo từ các nguồn được cấp quyền…',
    'Report saved with data notes. Review the notes below the report.': 'Đã lưu báo cáo. Xem ghi chú dữ liệu ở cuối báo cáo.',
    'Report generated and saved.': 'Đã tạo và lưu báo cáo.',
    'Your saved reports will appear here.': 'Báo cáo đã lưu sẽ xuất hiện tại đây.',
    'Opening report...': 'Đang mở báo cáo…', 'Report opened.': 'Đã mở báo cáo.',
    'Loading reports...': 'Đang tải danh sách báo cáo…', 'Ready.': 'Sẵn sàng.',
    'Move up': 'Di chuyển lên', 'Move down': 'Di chuyển xuống',
    'Remove section': 'Ẩn mục', 'Restore section': 'Hiện lại mục',
    'Keep at least one section.': 'Hãy giữ ít nhất một mục.',
    'Removed from preview and PDF. Restore it to include it again.': 'Mục này đang ẩn trong bản xem trước và PDF.',
    'Narrative text': 'Nội dung diễn giải', 'Restore generated text': 'Khôi phục nội dung ban đầu',
    'Line chart': 'Biểu đồ đường', 'Bar chart': 'Biểu đồ cột', Table: 'Bảng',
    'Unsaved layout changes.': 'Bố cục có thay đổi chưa lưu.',
    'Unsaved section changes.': 'Thay đổi các mục chưa được lưu.',
    'Unsaved text changes.': 'Nội dung có thay đổi chưa lưu.',
    'Unsaved chart changes.': 'Biểu đồ có thay đổi chưa lưu.',
    'Unsaved title changes.': 'Tiêu đề có thay đổi chưa lưu.',
    'Saving report...': 'Đang lưu báo cáo…', 'Report saved.': 'Đã lưu báo cáo.',
    'Preparing PDF...': 'Đang chuẩn bị PDF…', 'PDF downloaded.': 'Đã tải PDF.',
    'Delete this saved report?': 'Xóa báo cáo đã lưu này?',
    'Deleting report...': 'Đang xóa báo cáo…', 'Report deleted.': 'Đã xóa báo cáo.',
    'Describe a new report.': 'Nhập yêu cầu cho báo cáo mới.',
    'Sign in to continue': 'Hãy đăng nhập để tiếp tục',
    'The report could not be saved. Reopen it and try again.': 'Chưa lưu được báo cáo. Hãy mở lại báo cáo rồi thử lại.',
    'Enter a report title before saving.': 'Hãy nhập tiêu đề trước khi lưu.',
    'This saved report changed. Reopen it before downloading.': 'Báo cáo đã thay đổi. Hãy mở lại trước khi tải.',
    'PDF download failed. Please retry.': 'Chưa tải được PDF. Vui lòng thử lại.',
    'Inventory sections, metrics, widgets and decision rules use the fixed contract. You can edit the saved report title.':
      'Báo cáo tồn kho dùng bố cục, chỉ số, biểu đồ và quy tắc cố định. Bạn có thể sửa tiêu đề.',
  };
  const copy = text => vi && Object.hasOwn(copyVi, text) ? copyVi[text] : text;
  const translated = [...el('reports-workspace').querySelectorAll('[data-report-vi]')]
    .map(node => [node, node.textContent]);
  function setLanguage(vietnamese) {
    vi = vietnamese;
    el('reports-workspace').setAttribute('lang', vi ? 'vi' : 'en');
    translated.forEach(([node, english]) => { node.textContent = vi ? node.dataset.reportVi : english; });
    el('report-agent-question').placeholder = vi ? 'Báo cáo doanh thu tháng 5/2026' : 'Monthly revenue report for May 2026';
  }
  const status = (text, error = false) => { el('report-workspace-status').textContent = copy(text); el('report-workspace-status').dataset.error = String(error); };
  const element = (tag, text) => { const node = document.createElement(tag); if (text !== undefined) node.textContent = text; return node; };
  const allowed = () => ['admin','finance_analyst','sustainability_analyst','operations','executive'].includes(currentUser?.role);
  function setBusy(value) {
    el('reports-workspace').querySelectorAll('button,input,textarea,select').forEach(control => {
      if (value) {
        if (!Object.hasOwn(control.dataset,'busyWasDisabled')) control.dataset.busyWasDisabled = control.disabled ? '1' : '0';
        control.disabled = true;
      } else if (Object.hasOwn(control.dataset,'busyWasDisabled')) {
        control.disabled = control.dataset.busyWasDisabled === '1'; delete control.dataset.busyWasDisabled;
      }
    });
  }
  async function request(path, options = {}) {
    const generation = sessionGeneration, token = epoch;
    const response = await backendFetch(path, {credentials:'same-origin', ...options, headers:{'Content-Type':'application/json', 'ngrok-skip-browser-warning':'1', ...(options.headers || {})}});
    if (response.status === 401) { if (generation === sessionGeneration && token === epoch) clearExpiredSession(); throw new Error('Sign in to continue'); }
    if (response.status === 204) return null;
    const payload = await response.json();
    if (!response.ok) throw new Error(typeof payload.detail === 'string' ? payload.detail : 'The report could not be saved. Reopen it and try again.');
    return payload;
  }
  async function action(message, work) {
    if (busy) return;
    const generation = sessionGeneration, token = epoch;
    const valid = () => token === epoch && generation === sessionGeneration && allowed();
    busy = true; status(message); setBusy(true);
    const skeleton = /Opening|Generating|Đang (mở|tạo)/.test(message) ? document.getElementById('rw-skeleton') : null;
    if (skeleton) skeleton.hidden = false;
    try { await work(valid); }
    catch (error) { if (valid()) status(error.message, true); }
    finally { if (skeleton) skeleton.hidden = true; if (valid()) { busy = false; setBusy(false); } }
  }
  async function library(valid = () => true) {
    const payload = await request('/api/reports');
    if (!valid()) return;
    loaded = true; el('rw-library').replaceChildren();
    if (!payload.reports.length) el('rw-library').append(element('p', copy('Your saved reports will appear here.')));
    payload.reports.forEach(doc => {
      const button = element('button'); button.type = 'button'; button.dataset.id = doc.id;
      button.setAttribute('aria-current', String(doc.id === selected?.id));
      button.append(element('strong', doc.title), element('small', new Date(doc.updated_at).toLocaleString(vi ? 'vi-VN' : undefined)));
      button.addEventListener('click', () => action('Opening report...', async valid => {
        const payload = await request(`/api/reports/${doc.id}`);
        if (valid()) { display(payload.document, false); status('Report opened.'); }
      }));
      el('rw-library').append(button);
    });
    setBusy(busy);
  }
  function preview() {
    if (selected) SalesPerformanceReport.render(el('sales-report-output'), selected.report, {title:selected.title, presentation:selected.presentation, monthly_decisions:selected.monthly_decisions, insights:selected.insights, inventory_context:selected.inventory_context});
  }
  function showTab(edit) {
    el('rw-edit-panel').hidden = !edit; el('sales-report-output').hidden = edit || !selected;
    el('rw-preview-tab').setAttribute('aria-pressed', String(!edit)); el('rw-edit-tab').setAttribute('aria-pressed', String(edit));
  }
  function editor() {
    const root = el('rw-edit-panel'); root.replaceChildren();
    if (selected.report.report_type === 'inventory_operations') {
      root.append(element('p',copy('Inventory sections, metrics, widgets and decision rules use the fixed contract. You can edit the saved report title.')));
      return;
    }
    const defaults = SalesPerformanceReport.defaultPresentation(selected.report).chart_types;
    selected.presentation.section_order.forEach((key, index, order) => {
      const titles = vi ? SalesPerformanceReport.sectionTitlesVi : SalesPerformanceReport.sectionTitles;
      const item = element('fieldset'); const title = titles[Object.keys(selected.report.sections).indexOf(key)];
      item.append(element('legend', title));
      const controls = element('div'); controls.className = 'rw-toolbar';
      for (const [label, delta] of [['Move up', -1], ['Move down', 1]]) {
        const button = element('button', copy(label)); button.type = 'button'; button.disabled = index + delta < 0 || index + delta >= order.length;
        button.addEventListener('click', () => { const next = index + delta; [order[index],order[next]] = [order[next],order[index]]; editor(); preview(); status('Unsaved layout changes.'); }); controls.append(button);
      }
      const hidden = selected.presentation.hidden_sections.includes(key);
      const toggle = element('button', copy(hidden ? 'Restore section' : 'Remove section')); toggle.type = 'button';
      toggle.addEventListener('click', () => {
        if (!hidden && selected.presentation.hidden_sections.length === 4) { status('Keep at least one section.', true); return; }
        selected.presentation.hidden_sections = hidden ? selected.presentation.hidden_sections.filter(id => id !== key) : [...selected.presentation.hidden_sections,key];
        editor(); preview(); status('Unsaved section changes.');
      }); controls.append(toggle); item.append(controls);
      if (hidden) item.append(element('p', copy('Removed from preview and PDF. Restore it to include it again.')));
      if (['executive_summary','key_findings_and_explanations'].includes(key)) {
        const id = `rw-text-${key}`; const label = element('label', copy('Narrative text')); label.htmlFor = id;
        const input = element('textarea'); input.id = id; input.maxLength = 6000;
        input.value = selected.presentation.text_edits[key] ?? SalesPerformanceReport.narrative(selected.report,key,selected.monthly_decisions).map(item => item.text).join('\n\n');
        input.addEventListener('input', () => { selected.presentation.text_edits[key] = input.value; preview(); status('Unsaved text changes.'); });
        const reset = element('button',copy('Restore generated text')); reset.type = 'button'; reset.addEventListener('click', () => { delete selected.presentation.text_edits[key]; editor(); preview(); });
        item.append(label,input,reset);
      }
      if (key === 'performance_analysis') selected.report.dashboard.widgets.filter(w => !['sales_kpis','order_kpis'].includes(w.id)).forEach(widget => {
        const label = element('label',widget.title); label.htmlFor = `rw-type-${widget.id}`;
        const select = element('select'); select.id = label.htmlFor;
        for (const [value,text] of [['line','Line chart'],['bar','Bar chart'],['kpi_row','KPI'],['table','Table']]) {
          const option = element('option',copy(text)); option.value = value; select.append(option);
        }
        select.value = selected.presentation.chart_types[widget.id] || defaults[widget.id] || widget.type;
        select.addEventListener('change', () => { selected.presentation.chart_types[widget.id] = select.value; preview(); status('Unsaved chart changes.'); });
        item.append(label,select);
      });
      root.append(item);
    });
  }
  function display(doc, reload = true) {
    el('report-fold').open = true;
    selected = JSON.parse(JSON.stringify(doc)); el('rw-title').value = selected.title; el('rw-editor').hidden = false;
    setLanguage(SalesPerformanceReport.vietnamese(selected.report.metrics[0]?.label));
    el('rw-meta').textContent = `${vi ? 'Phiên bản đã lưu' : 'Saved revision'} ${selected.revision} · ${new Date(selected.updated_at).toLocaleString(vi ? 'vi-VN' : undefined)}`;
    preview(); editor(); showTab(false);
    setBusy(busy);
    if (reload) {
      const token = epoch, generation = sessionGeneration;
      library(() => token === epoch && generation === sessionGeneration).catch(error => status(error.message,true));
    }
  }
  async function save(valid) {
    if (!selected.title.trim()) throw new Error('Enter a report title before saving.');
    const id = selected.id;
    const payload = await request(`/api/reports/${id}`, {method:'PUT', body:JSON.stringify({revision:selected.revision,title:selected.title,presentation:selected.presentation})});
    if (!valid() || selected?.id !== id) return false;
    display(payload.document, false); await library(valid); return valid();
  }
  el('rw-title').addEventListener('input', () => { if (selected && !busy) { selected.title = el('rw-title').value; preview(); status('Unsaved title changes.'); } });
  el('rw-preview-tab').addEventListener('click', () => showTab(false));
  el('rw-edit-tab').addEventListener('click', () => showTab(true));
  el('rw-save').addEventListener('click', () => selected && action('Saving report...', async valid => { if (await save(valid)) status('Report saved.'); }));
  el('rw-download').addEventListener('click', () => selected && action('Preparing PDF...', async valid => {
    if (!await save(valid)) return;
    const response = await backendFetch(`/api/reports/${selected.id}/pdf?revision=${selected.revision}`, {credentials:'same-origin',headers:{'ngrok-skip-browser-warning':'1'}});
    if (!valid()) return;
    if (response.status === 401) { clearExpiredSession(); throw new Error('Sign in to continue'); }
    if (response.status === 409) throw new Error('This saved report changed. Reopen it before downloading.');
    if (!response.ok) throw new Error('PDF download failed. Please retry.');
    const blob = await response.blob(); if (!valid()) return;
    const url = URL.createObjectURL(blob), link = element('a'); link.href = url; link.download = `${selected.report.report_type.replaceAll('_','-')}-report.pdf`; link.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000); status('PDF downloaded.');
  }));
  el('rw-delete').addEventListener('click', () => {
    if (!selected || !window.confirm(copy('Delete this saved report?'))) return;
    action('Deleting report...', async valid => { await request(`/api/reports/${selected.id}?revision=${selected.revision}`,{method:'DELETE'}); if (!valid()) return; reset(); await library(valid); status('Report deleted.'); });
  });
  function reset() { selected = null; el('rw-editor').hidden = true; el('rw-title').value = ''; el('rw-meta').textContent = ''; el('rw-edit-panel').hidden = true; el('rw-edit-panel').replaceChildren(); el('sales-report-output').hidden = true; el('sales-report-output').replaceChildren(); el('sales-report-output').removeAttribute('aria-busy'); el('report-agent-question').value = ''; el('report-agent-submit').disabled = false; }
  el('rw-new').addEventListener('click', () => { if (!busy) { reportConversationId = crypto.randomUUID(); reset(); status('Describe a new report.'); el('report-agent-question').focus(); } });
  window.reportWorkspace = {
    display,
    generate(question) {
      if (busy) return;
      setLanguage(SalesPerformanceReport.vietnamese(question));
      return action('Generating report from authorized sources...', async valid => {
      const payload = await request('/api/reports',{method:'POST',body:JSON.stringify({question})});
      if (!valid()) return;
      display(payload.document,false); await library(valid);
      if (valid()) { status(payload.document.status === 'partial' ? 'Report saved with data notes. Review the notes below the report.' : 'Report generated and saved.'); el('sales-report-output').focus(); }
    }); },
    show() { if (allowed() && !loaded) action('Loading reports...', async valid => { await library(valid); if (valid()) status('Ready.'); }); },
    clear() { epoch++; loaded = false; busy = false; reset(); setLanguage(false); el('rw-library').replaceChildren(); status(''); setBusy(false); },
  };
  if (typeof activeTab !== 'undefined' && activeTab === 'knowledge') window.reportWorkspace.show();
})();
