const $ = (selector) => document.querySelector(selector);
let analyticsSnapshot = null;
let financialMetricDefinitions = new Map();
let businessMetricDefinitions = new Map();
let pendingMetricCandidates = [];
let activeTab = "knowledge";
let currentUser = null;
let decisionSuggestionsPending = false;
let commerceSnapshot = null;
const commerceLoadedDomains = new Set();
const commerceLoadingDomains = new Set();
let commerceCampaignsLoaded = false;
let commerceCampaignsLoading = false;
let knowledgeDocuments = [];
const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
}[char]));

function validSourceUrl(value) {
  try {
    const url = new URL(value);
    return url.protocol === "https:" ? url.href : "";
  } catch {
    return "";
  }
}

function sourcePageUrl(value, pageNumber) {
  const source = validSourceUrl(value);
  if (!source) return "";
  const url = new URL(source);
  const page = Number(pageNumber);
  if (url.pathname.toLowerCase().endsWith(".pdf") && Number.isInteger(page) && page > 0) {
    url.hash = `page=${page}`;
  }
  return url.href;
}

function uploadedSourcePageUrl(documentId, pageNumber) {
  if (!String(documentId || "").startsWith("UPLOAD-")) return "";
  const page = Number(pageNumber);
  return `/api/documents/${encodeURIComponent(documentId)}/source${Number.isInteger(page) && page > 0 ? `#page=${page}` : ""}`;
}

function metricSourceChunkInspectButton(documentId, chunkId, chunkIndex) {
  if (currentUser?.role !== "admin" || !documentId || !Number.isInteger(chunkId) || chunkId < 1
      || !Number.isInteger(chunkIndex) || chunkIndex < 0) return "";
  return `<button type="button" class="inline-tab-link" data-inspect-indexed-chunk data-document-id="${escapeHtml(documentId)}" data-source-chunk-id="${chunkId}" data-chunk-index="${chunkIndex}">Inspect linked indexed chunk ${chunkIndex}</button>`;
}

function selectWorkspaceTab(name) {
  const button = $(`[data-tab-target="${name}"]`);
  if (!button || button.hidden) return;
  activeTab = name;
  $(".intro").hidden = name === "analytics";
  document.querySelectorAll(".workspace-tab").forEach((tab) => {
    const selected = tab === button;
    tab.setAttribute("aria-selected", String(selected));
    tab.tabIndex = selected ? 0 : -1;
    tab.classList.toggle("active", selected);
  });
  document.querySelectorAll(".tab-panel").forEach((panel) => {
    panel.hidden = panel.id !== button.getAttribute("aria-controls");
  });
  if (name === "analytics") loadCommerceDashboardForActiveView();
}

function selectAnalyticsTab(name) {
  const button = $(`[data-analytics-tab="${name}"]`);
  if (!button) return;
  document.querySelectorAll("[data-analytics-tab]").forEach((tab) => {
    const selected = tab === button;
    tab.setAttribute("aria-selected", String(selected));
    tab.tabIndex = selected ? 0 : -1;
    tab.classList.toggle("active", selected);
  });
  document.querySelectorAll(".analytics-subpanel").forEach((panel) => {
    panel.hidden = panel.id !== button.getAttribute("aria-controls");
  });
}

document.querySelector(".analytics-subtabs").addEventListener("click", (event) => {
  const button = event.target.closest("[data-analytics-tab]");
  if (button) selectAnalyticsTab(button.dataset.analyticsTab);
});

document.querySelector(".analytics-subtabs").addEventListener("keydown", (event) => {
  const tabs = [...document.querySelectorAll("[data-analytics-tab]")];
  const current = tabs.indexOf(event.target);
  if (current < 0) return;
  const next = {ArrowRight: (current + 1) % tabs.length, ArrowLeft: (current - 1 + tabs.length) % tabs.length,
    Home: 0, End: tabs.length - 1}[event.key];
  if (next === undefined) return;
  event.preventDefault();
  tabs[next].focus();
  selectAnalyticsTab(tabs[next].dataset.analyticsTab);
});

function syncWorkspaceTabs(user = currentUser) {
  const isAdmin = user?.role === "admin";
  const isTester = user?.role === "tester";
  const canViewAnalytics = ["operations", "finance_analyst", "sustainability_analyst", "executive", "admin"].includes(user?.role);
  const canUpload = ["document_uploader", "admin"].includes(user?.role);
  const available = {
    knowledge: !isTester,
    analytics: canViewAnalytics,
    processing: canUpload,
    "ocr-lab": isTester || isAdmin,
    metrics: isAdmin,
    "knowledge-management": isAdmin,
    access: isAdmin,
    monitoring: isAdmin,
  };
  document.querySelectorAll(".workspace-tab").forEach((button) => {
    button.hidden = !available[button.dataset.tabTarget];
  });
  if (!available[activeTab]) activeTab = isTester ? "ocr-lab" : "knowledge";
  selectWorkspaceTab(activeTab);
}

document.querySelectorAll("[data-open-tab]").forEach((button) => {
  button.addEventListener("click", () => selectWorkspaceTab(button.dataset.openTab));
});

function renderCorpus(data) {
  const commerceLabels = {
    inventory_allocation: "Inventory allocation",
    promotion_planning: "Promotion planning",
    nationwide_logistics: "Nationwide logistics",
  };
  const referenceLabels = {
    company_practice_reference: "Company practice",
    company_policy_reference: "Company policy reference",
    platform_operating_rule: "Platform operating rule",
  };
  const companies = new Set(data.documents.map((doc) => doc.company).filter(Boolean));
  $("#company-name").textContent = companies.size || 0;
  $("#document-count").textContent = formatNumber(data.document_count);
  $("#chunk-count").textContent = formatNumber(data.chunk_count);
  const inFlight = data.documents.filter((doc) => doc.processing_status !== "ready").length;
  $("#processing-count").textContent = formatNumber(inFlight);
  $("#source-count").textContent = `${formatNumber(data.document_count)} registered source${data.document_count === 1 ? "" : "s"}`;
  $("#connection-status").textContent = "Knowledge base connected";
  document.querySelector(".status-dot").classList.add("connected");

  const groups = Object.groupBy
    ? Object.groupBy(data.documents, (doc) => doc.company)
    : data.documents.reduce((result, doc) => {
      (result[doc.company] ??= []).push(doc);
      return result;
    }, {});
  $("#company-grid").innerHTML = Object.entries(groups).map(([company, docs]) => `
    <article class="company-card">
      <div class="company-card-head"><div><span class="company-kicker">${escapeHtml([...new Set(docs.flatMap((doc) => doc.knowledge_domains || []))].map((domain) => commerceLabels[domain] || domain).join(" · ") || docs[0].domain.replaceAll("_", " "))}</span><h3>${escapeHtml(company)}</h3></div><span class="doc-total">${formatNumber(docs.length)} doc${docs.length === 1 ? "" : "s"}</span></div>
      <div class="document-list">${docs.map((doc) => {
        const href = validSourceUrl(doc.source_url);
        const link = href
          ? `<a class="document-link" href="${escapeHtml(href)}" target="_blank" rel="noopener noreferrer">Open official source</a>`
          : "";
        const status = doc.processing_status || (doc.chunks ? "ready" : "uploaded");
        const domains = (doc.knowledge_domains || []).map((domain) => commerceLabels[domain] || domain).join(", ");
        const reference = referenceLabels[doc.external_reference_type] || "";
        const attribution = [doc.source_publisher, reference, domains].filter(Boolean).join(" · ");
        return `<article class="document-row"><div class="file-mark">${escapeHtml(doc.format)}</div><div class="document-info"><strong>${escapeHtml(doc.title)}</strong><span>${escapeHtml(doc.fiscal_year ? `FY ${doc.fiscal_year}` : attribution || "General")} · ${formatNumber(doc.chunks)} passages · ${escapeHtml(status)} · access: ${escapeHtml((doc.allowed_roles || []).join(", "))}</span>${attribution ? `<small>${escapeHtml(attribution)}</small>` : ""}${link}</div></article>`;
      }).join("")}</div>
    </article>`).join("") || '<div class="loading-card">No company documents are indexed yet.</div>';
}

function renderParsedChunkInspector(data) {
  const documents = data.documents;
  const section = $("#parsed-chunk-inspector");
  section.hidden = documents.length === 0;
  $("#parsed-document").innerHTML = documents.map((doc) =>
    `<option value="${escapeHtml(doc.document_id)}">${escapeHtml(doc.title)} · ${escapeHtml(doc.processing_status || "unknown")}</option>`
  ).join("");
}

function renderKnowledgeDocuments() {
  const query = $("#knowledge-documents-search").value.trim().toLocaleLowerCase();
  const matches = knowledgeDocuments.filter((doc) => [doc.title, doc.document_id, doc.source_publisher,
    doc.domain, doc.evidence_class, doc.synthetic_company_policy ? "synthetic demo policy" : "",
    ...(doc.knowledge_domains || [])].join(" ").toLocaleLowerCase().includes(query));
  $("#knowledge-documents-status").textContent = `${formatNumber(knowledgeDocuments.filter((doc) => doc.knowledge_base_active).length)} active · ${formatNumber(knowledgeDocuments.length)} indexed sources`;
  $("#knowledge-documents-list").innerHTML = matches.map((doc) => {
    const domains = (doc.knowledge_domains || []).join(", ") || doc.domain || "General";
    const href = validSourceUrl(doc.source_url);
    const sourceKind = doc.synthetic_company_policy
      ? "Synthetic demo policy · fictional Commerce Demo only"
      : ({ management_cookbook_reference: "Management method · external reference",
          company_practice_reference: "Company practice · attributed example",
          platform_operating_rule: "Platform rule · scope-specific" }[doc.evidence_class] || "Knowledge source");
    const sourceLink = doc.synthetic_company_policy
      ? `<a href="/api/admin/knowledge-documents/${encodeURIComponent(doc.document_id)}/source" target="_blank" rel="noopener noreferrer">Open original PDF</a>`
      : href ? `<a href="${escapeHtml(href)}" target="_blank" rel="noopener noreferrer">Open source</a>` : "";
    return `<article class="knowledge-document-row ${doc.knowledge_base_active ? "" : "is-removed"}">
      <div class="knowledge-document-copy"><strong>${escapeHtml(doc.title)}</strong>
        <span class="knowledge-source-kind ${doc.synthetic_company_policy ? "is-synthetic" : ""}">${escapeHtml(sourceKind)}</span>
        <span>${escapeHtml(doc.source_publisher || doc.company || "Unknown publisher")} · ${escapeHtml(doc.format || "File")} · ${formatNumber(doc.chunk_count)} passages</span>
        <small>${escapeHtml(domains)} · ${escapeHtml(doc.processing_status || "unknown")} · ${doc.knowledge_base_active ? "Available to AI" : "Removed from AI retrieval"}</small>
        <code>${escapeHtml(doc.document_id)}</code>${sourceLink}
      </div>
      <button class="${doc.knowledge_base_active ? "danger-button" : "secondary-button"}" type="button" data-knowledge-toggle="${escapeHtml(doc.document_id)}" data-active="${doc.knowledge_base_active ? "true" : "false"}">${doc.knowledge_base_active ? "Remove from knowledge base" : "Restore to knowledge base"}</button>
    </article>`;
  }).join("") || '<p class="loading-card">No matching indexed sources.</p>';
}

async function refreshKnowledgeDocuments() {
  $("#knowledge-documents-status").textContent = "Loading indexed sources…";
  const result = await api("/api/admin/knowledge-documents");
  knowledgeDocuments = result.documents;
  renderKnowledgeDocuments();
}

function renderMetricCatalog(metrics) {
  financialMetricDefinitions = new Map(metrics.map((metric) => [metric.metric_name, metric]));
  const select = $("#manual-metric-name");
  select.innerHTML = metrics.map((metric) =>
    `<option value="${escapeHtml(metric.metric_name)}">${escapeHtml(metric.label)}</option>`
  ).join("");
  const showDefinition = () => {
    const metric = metrics.find((item) => item.metric_name === select.value);
    $("#metric-definition").innerHTML = metric
      ? `<article class="analysis-stat"><span>${escapeHtml(metric.metric_name)}</span><strong>${escapeHtml(metric.definition)}</strong><small>${escapeHtml(metric.unit_guidance)}</small></article>`
      : "";
    const unit = $("#manual-metric-unit");
    if (!unit.value && metric?.unit_guidance) unit.placeholder = metric.unit_guidance;
  };
  select.onchange = showDefinition;
  showDefinition();
}

function renderBusinessMetricCatalog(metrics) {
  businessMetricDefinitions = new Map(metrics.map((metric) => [metric.metric_name, metric]));
  const domains = [...new Set(metrics.map((metric) => metric.domain).filter(Boolean))].sort();
  const domainLabel = (domain) => metrics.find((metric) => metric.domain === domain)?.decision_profile_label
    || domain.replaceAll("_", " ");
  const populateDomains = (select, placeholder = "Choose a domain") => {
    select.innerHTML = `<option value="">${placeholder}</option>` + domains.map((domain) =>
      `<option value="${escapeHtml(domain)}">${escapeHtml(domainLabel(domain))}</option>`
    ).join("");
  };
  const entryDomain = $("#business-metric-entry-domain");
  const entryMetric = $("#business-metric-name");
  populateDomains(entryDomain);
  const updateEntryMetrics = () => {
    const matching = metrics.filter((metric) => metric.domain === entryDomain.value);
    entryMetric.innerHTML = matching.map((metric) =>
      `<option value="${escapeHtml(metric.metric_name)}">${escapeHtml(metric.label)}</option>`
    ).join("");
    update();
  };
  const update = () => {
    const metric = metrics.find((item) => item.metric_name === entryMetric.value);
    $("#business-metric-definition").innerHTML = metric
      ? `<article class="analysis-stat"><span>${escapeHtml(domainLabel(metric.domain))}</span><strong>${escapeHtml(metric.definition)}</strong><small>Typical unit: ${escapeHtml(metric.unit_guidance)}</small></article>`
      : "";
    const unit = $("#business-metric-unit");
    if (metric) unit.placeholder = metric.unit_guidance;
  };
  entryDomain.onchange = updateEntryMetrics;
  entryMetric.onchange = update;
  updateEntryMetrics();

  const replayDomain = $("#business-metric-replay-domain");
  const replayMetric = $("#business-metric-replay-metric");
  populateDomains(replayDomain);
  const updateReplayMetrics = () => {
    const matching = metrics.filter((metric) => metric.domain === replayDomain.value
      && metric.decision_priority === "primary");
    replayMetric.innerHTML = matching.map((metric) =>
      `<option value="${escapeHtml(metric.metric_name)}">${escapeHtml(metric.label)}</option>`
    ).join("");
    replayMetric.disabled = matching.length === 0;
  };
  replayDomain.onchange = updateReplayMetrics;
  updateReplayMetrics();
}

function renderParsedChunks(chunks, documentId) {
  $("#parsed-chunk-list").innerHTML = chunks.map((chunk) => {
    const pageNumber = chunk.metadata?.page_number;
    const isPdf = String(chunk.metadata?.format || "").toLowerCase() === "pdf"
      || /\.pdf(?:$|[?#])/i.test(String(chunk.metadata?.source_url || ""));
    const sourceUrl = uploadedSourcePageUrl(documentId, isPdf ? pageNumber : null)
      || sourcePageUrl(chunk.metadata?.source_url, isPdf ? pageNumber : null);
    const sourceLabel = isPdf && pageNumber ? `Open original PDF · page ${formatNumber(pageNumber)}` : "Open original document";
    return `
    <article class="candidate-row" id="document-chunk-${chunk.chunk_index}">
        <div class="candidate-heading"><strong>${pageNumber ? `Page ${formatNumber(pageNumber)} · ` : ""}Passage ${formatNumber(chunk.chunk_index + 1)}</strong><span>${escapeHtml(chunk.processing_status || "extracted")} · ${escapeHtml(chunk.metadata?.text_extraction_method || "parser output")}</span></div>
      ${sourceUrl ? `<a class="document-link" href="${escapeHtml(sourceUrl)}" target="_blank" rel="noopener noreferrer">${escapeHtml(sourceLabel)}</a>` : ""}
      ${chunk.processing_error ? `<p class="corpus-note">Processing error: ${escapeHtml(chunk.processing_error)}</p>` : ""}
      <blockquote>${escapeHtml(chunk.content)}</blockquote>
      <details class="candidate-source"><summary>Parser metadata</summary><pre>${escapeHtml(JSON.stringify(chunk.metadata, null, 2))}</pre></details>
    </article>`;
  }).join("") || '<p class="loading-card">No parsed passages at this offset.</p>';
}

function renderExtractedTables(tables, documentId) {
  $("#parsed-table-list").innerHTML = tables.map((table) => {
    const columns = Array.isArray(table.columns) ? table.columns : [];
    const rows = Array.isArray(table.rows) ? table.rows : [];
    const pageNumber = table.page_number;
    const isPdf = String(table.metadata?.format || "").toLowerCase() === "pdf"
      || /\.pdf(?:$|[?#])/i.test(String(table.metadata?.source_url || ""));
    const sourceUrl = uploadedSourcePageUrl(documentId, isPdf ? pageNumber : null)
      || sourcePageUrl(table.metadata?.source_url, isPdf ? pageNumber : null);
    const sourceLabel = isPdf && pageNumber ? `Open original PDF · page ${formatNumber(pageNumber)}` : "Open original document";
    return `<article class="candidate-row">
      <div class="candidate-heading"><strong>Page ${formatNumber(table.page_number)} · Table ${formatNumber(table.table_index + 1)}</strong><span>${formatNumber(table.row_count)} rows · showing ${formatNumber(rows.length)}</span></div>
      ${sourceUrl ? `<a class="document-link" href="${escapeHtml(sourceUrl)}" target="_blank" rel="noopener noreferrer">${escapeHtml(sourceLabel)}</a>` : ""}
      <div class="extracted-table-wrap"><table class="extracted-table"><thead><tr>${columns.map((column) => `<th>${escapeHtml(column)}</th>`).join("")}</tr></thead><tbody>${rows.map((row) => `<tr>${columns.map((column) => `<td>${escapeHtml(row?.[column] ?? "")}</td>`).join("")}</tr>`).join("")}</tbody></table></div>
      <details class="candidate-source"><summary>Table metadata</summary><pre>${escapeHtml(JSON.stringify(table.metadata, null, 2))}</pre></details>
    </article>`;
  }).join("") || '<p class="loading-card">No structured tables were extracted from this document.</p>';
}

function renderBusinessMetricExtractionRuns(runs) {
  const label = {
    candidate_found: "Candidate found",
    checked_no_candidate: "Checked · no candidate",
    not_selected: "Not selected for LLM",
    not_evaluated: "Not evaluated",
    llm_error: "LLM error",
  };
  $("#business-metric-extraction-runs").innerHTML = runs.map((run) => {
    const decisions = run.audit?.chunk_decisions || [];
    return `<details class="candidate-row">
      <summary class="candidate-heading"><strong>${escapeHtml(run.decision_domain)} · ${(run.audit?.selected_metric_names || []).map(escapeHtml).join(", ")} · ${escapeHtml(run.status)}</strong><span>${formatNumber(run.selected_chunk_count)} / ${formatNumber(run.input_chunk_count)} chunks selected · ${formatNumber(run.candidate_count)} candidates · ${escapeHtml(run.model_name)}</span></summary>
      <p class="corpus-note">Extractor ${escapeHtml(run.extractor_version)} · prompt ${escapeHtml(run.prompt_version)} · ${escapeHtml(new Date(run.created_at).toLocaleString())}</p>
      <div class="extracted-table-wrap"><table class="extracted-table"><thead><tr><th>Chunk</th><th>Page</th><th>Decision</th><th>Selection reason</th><th>Selector signals</th></tr></thead><tbody>${decisions.map((item) => `<tr><td>${formatNumber(item.chunk_index)}</td><td>${formatNumber(item.page_number)}</td><td>${escapeHtml(label[item.status] || item.status)}</td><td>${escapeHtml(item.selection_reason || "selected")}</td><td>${escapeHtml(JSON.stringify(item.selection_signals || {}))}</td></tr>`).join("")}</tbody></table></div>
      <details class="candidate-source"><summary>LLM page results and validation</summary><pre>${escapeHtml(JSON.stringify({pages: run.audit?.page_results || [], error: run.audit?.execution_error || null}, null, 2))}</pre></details>
    </details>`;
  }).join("") || '<p class="loading-card">No business metric extraction run is recorded for this document.</p>';
}

const replayDomainSelect = $("#business-metric-replay-domain");
const replayMetricSelect = $("#business-metric-replay-metric");

async function loadOcrTestRuns() {
  const result = await api("/api/ocr-tests");
  $("#ocr-test-runs").innerHTML = result.runs.map((run) => {
    const config = run.processor_config || {};
    const settings = config.tesseract_psm
      ? `PSM ${config.tesseract_psm} · page ${config.ocr_render_scale || "?"}×`
      : "OCR settings unavailable";
    return `<button type="button" class="ocr-run-button" data-ocr-run-id="${escapeHtml(run.run_id)}"><strong>${escapeHtml(run.source_filename)}</strong><span>${escapeHtml(new Date(run.created_at).toLocaleString())} · ${formatNumber(run.page_count)} pages · ${formatNumber(run.chunk_count)} chunks · ${formatNumber(run.table_count)} tables · ${escapeHtml(settings)}</span></button>`;
  }).join("") || '<p class="loading-card">No OCR tests yet. Upload a PDF above to create one.</p>';
}

function renderOcrTestDetails(run) {
  const allPages = [...new Set([
    ...run.pages,
    ...run.chunks.map((chunk) => Number(chunk.metadata?.page_number)).filter(Number.isFinite),
    ...run.tables.map((table) => Number(table.page_number)).filter(Number.isFinite),
  ])].sort((a, b) => a - b);
  const pageContent = allPages.map((pageNumber, pageIndex) => {
    const chunks = run.chunks.filter((chunk) => Number(chunk.metadata?.page_number) === pageNumber);
    const tables = run.tables.filter((table) => Number(table.page_number) === pageNumber);
    const tablesHtml = tables.map((table) => {
      const data = table.structured_data || {};
      const context = table.context || {};
      const columns = Array.isArray(data.columns) ? data.columns : [];
      const rows = Array.isArray(data.rows) ? data.rows : [];
      const headers = columns.length ? columns : [...new Set(rows.flatMap((row) => Object.keys(row || {})))];
      const metadata = table.metadata || {};
      const ocr = metadata.ocr || {};
      const bbox = Array.isArray(metadata.bbox)
        ? metadata.bbox.map((value) => Number(value).toFixed(1)).join(" · ")
        : "Not available";
      const parserDetails = [
        ["OCR", [ocr.engine, ocr.language && `language ${ocr.language}`, ocr.table_psm && `PSM ${ocr.table_psm}`, ocr.render_scale && `scale ${ocr.render_scale}×`].filter(Boolean).join(" · ") || "Not available"],
        ["Extraction", metadata.table_extraction_method || "Not available"],
        ["Detection", metadata.table_detection_strategy || "Not available"],
        ["Table region", `${bbox}${metadata.bbox_coordinate_system ? ` (${metadata.bbox_coordinate_system})` : ""}`],
        ["Structure", `${formatNumber(rows.length)} rows · ${formatNumber(headers.length)} columns`],
      ];
      return `<article class="ocr-test-table"><h5>Table ${formatNumber(table.table_index + 1)} <span>${formatNumber(rows.length)} rows</span></h5>
        ${headers.length ? `<div class="ocr-test-table-wrap"><table class="extracted-table"><thead><tr>${headers.map((column) => `<th>${escapeHtml(column)}</th>`).join("")}</tr></thead><tbody>${rows.map((row) => `<tr>${headers.map((column) => `<td>${escapeHtml(row?.[column] ?? "")}</td>`).join("")}</tr>`).join("")}</tbody></table></div>` : `<pre>${escapeHtml(JSON.stringify(data, null, 2))}</pre>`}
        <details class="candidate-source"><summary>Table context</summary><dl class="ocr-context-list">
          <dt>Source</dt><dd>${escapeHtml(context.source_filename || run.source_filename)}</dd>
          <dt>Section</dt><dd>${escapeHtml(context.section_title || "Not extracted")}</dd>
          <dt>Table title</dt><dd>${escapeHtml(context.table_title || "Not extracted")}</dd>
          <dt>Unit</dt><dd>${escapeHtml(context.unit || "Not extracted")}</dd>
          <dt>Reporting periods</dt><dd>${escapeHtml((context.reporting_periods || []).join(", ") || "Not extracted")}</dd>
        </dl></details>
        <dl class="ocr-context-list">${parserDetails.map(([label, value]) => `<dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value)}</dd>`).join("")}</dl>
        <details class="candidate-source"><summary>Detailed parser metadata</summary><pre>${escapeHtml(JSON.stringify(metadata, null, 2))}</pre></details></article>`;
    }).join("");
    return `<details class="ocr-test-page" ${pageIndex === 0 ? "open" : ""}>
      <summary>Page ${formatNumber(pageNumber)} · ${formatNumber(chunks.length)} chunks · ${formatNumber(tables.length)} tables</summary>
      <section class="ocr-test-raw"><h4>Raw page</h4><img loading="lazy" alt="Rendered source page ${formatNumber(pageNumber)}" src="/api/ocr-tests/${encodeURIComponent(run.run_id)}/pages/${pageNumber}/preview"></section>
      <section class="ocr-test-extracted"><h4>Extracted output</h4>
        <details class="ocr-test-chunks"><summary>View ${formatNumber(chunks.length)} text chunks for this page</summary>${chunks.map((chunk) => `<article class="ocr-test-chunk"><div class="candidate-heading"><strong>Chunk ${formatNumber(chunk.chunk_index + 1)}</strong><span>${formatNumber(chunk.metadata?.actual_char_count ?? chunk.content.length)} chars actual · ${formatNumber(chunk.metadata?.chunk_size_chars ?? 0)} char limit · ${escapeHtml(chunk.metadata?.text_extraction_method || "parser output")} · ${escapeHtml(chunk.metadata?.layout_type || "text")}</span></div><pre>${escapeHtml(chunk.content)}</pre><details class="candidate-source"><summary>Chunk metadata</summary><pre>${escapeHtml(JSON.stringify(chunk.metadata, null, 2))}</pre></details></article>`).join("") || '<p class="ocr-test-empty">No text chunks on this page.</p>'}</details>
        <h4 class="ocr-test-table-heading">Extracted tables</h4>
        ${tablesHtml || '<p class="ocr-test-empty">No structured table detected on this page.</p>'}
      </section>
    </details>`;
  }).join("");
  $("#ocr-test-results").innerHTML = `<article class="ocr-test-run">
    <div class="candidate-heading"><strong>${escapeHtml(run.source_filename)}</strong><span>${formatNumber(run.page_count)} pages · ${formatNumber(run.chunks.length)} chunks · ${formatNumber(run.tables.length)} tables</span></div>
    <p class="corpus-note">SHA-256: <code>${escapeHtml(run.source_sha256)}</code></p>
    <details class="candidate-source"><summary>Parser configuration and versions</summary><pre>${escapeHtml(JSON.stringify({processor_config:run.processor_config,runtime_info:run.runtime_info},null,2))}</pre></details>
    <div class="ocr-test-pages">${pageContent}</div>
  </article>`;
}

async function openOcrTestRun(runId) {
  $("#ocr-test-results").innerHTML = '<p class="loading-card">Loading test pages and parser output…</p>';
  try {
    renderOcrTestDetails(await api(`/api/ocr-tests/${encodeURIComponent(runId)}`));
  } catch (error) {
    $("#ocr-test-results").innerHTML = `<p class="loading-card">${escapeHtml(error.message)}</p>`;
  }
}

function formatNumber(value) {
  return new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 3 }).format(value);
}

function formatFinancialValue(value) {
  const parsed = typeof value === "number" ? value : Number(String(value ?? "").trim());
  return Number.isFinite(parsed)
    ? new Intl.NumberFormat("vi-VN", { useGrouping: true, maximumFractionDigits: 3 }).format(parsed)
    : "—";
}

function formatCommerceValue(value) {
  const parsed = typeof value === "number" ? value : Number(String(value ?? "").trim());
  return Number.isFinite(parsed)
    ? new Intl.NumberFormat("en-US", { useGrouping: true, maximumFractionDigits: 2 }).format(parsed)
    : "—";
}

function commerceTable(rows, columns) {
  if (!rows.length) return '<p class="analysis-empty">No observations for this year.</p>';
  const headings = columns.map(([, label]) => `<th>${escapeHtml(label)}</th>`).join("");
  const body = rows.map((row) => `<tr>${columns.map(([key, , format]) => {
    const value = row[key];
    const rendered = format ? format(value, row)
      : value == null ? "—"
        : key === "year" ? String(value)
          : typeof value === "number" ? formatCommerceValue(value) : value;
    return `<td>${escapeHtml(rendered)}</td>`;
  }).join("")}</tr>`).join("");
  return `<table><thead><tr>${headings}</tr></thead><tbody>${body}</tbody></table>`;
}

function renderCommerceEvidence(rows, group) {
  if (!Array.isArray(rows) || !rows.length) return "";
  const columns = [...new Set(rows.flatMap((row) => Object.keys(row || {})))];
  if (!columns.length) return "";
  const header = columns.map((key) => `<th>${escapeHtml(key.replaceAll("_", " "))}</th>`).join("");
  const body = rows.map((row) => `<tr>${columns.map((key) => {
    const value = row?.[key];
    const text = typeof value === "number"
      ? new Intl.NumberFormat("en-US", {maximumFractionDigits: 8}).format(value)
      : value === true ? "Yes" : value === false ? "No" : value == null ? "—" : String(value);
    return `<td>${escapeHtml(text)}</td>`;
  }).join("")}</tr>`).join("");
  return `<details class="citation-observations"><summary>Inspect structured SQL observations · ${rows.length} rows</summary><div class="commerce-table-wrap"><table aria-label="${escapeHtml(group || "Commerce SQL observations")}"><thead><tr>${header}</tr></thead><tbody>${body}</tbody></table></div></details>`;
}

function renderCommerceCards(cards, note) {
  $("#commerce-domain-cards").innerHTML = cards.map(([label, value, detail]) =>
    `<article class="commerce-kpi-card"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong><small>${escapeHtml(detail || note)}</small></article>`
  ).join("");
}

function renderCommerceChart(selector, rows, series, unit, kind = "line", periodLabel = "All available years") {
  const root = $(selector);
  if (!rows.length) {
    root.innerHTML = '<p class="analysis-empty">No observations available to chart.</p>';
    return;
  }
  const years = [...new Set(rows.map((row) => Number(row.year)).filter(Number.isFinite))].sort((a, b) => a - b);
  const values = rows.flatMap((row) => series.map((item) => Number(item.value(row)))).filter(Number.isFinite);
  const max = Math.max(1, ...values) * 1.08;
  const width = 760, height = 250, left = 60, right = 746, top = 15, bottom = 199;
  const x = (index) => years.length < 2 ? (left + right) / 2 : left + index * (right - left) / (years.length - 1);
  const y = (value) => bottom - (value / max) * (bottom - top);
  const compact = new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 });
  const grid = Array.from({ length: 4 }, (_, index) => {
    const value = max * index / 3, yy = y(value);
    return `<g><line x1="${left}" y1="${yy}" x2="${right}" y2="${yy}" class="commerce-chart-gridline"/><text x="${left - 8}" y="${yy + 4}" text-anchor="end" class="commerce-chart-axis-label">${compact.format(value)}</text></g>`;
  }).join("");
  const labels = years.map((year, index) => `<text x="${x(index)}" y="${height - 12}" text-anchor="middle" class="commerce-chart-axis-label">${year}</text>`).join("");
  let marks = "";
  if (kind === "bar") {
    const groupWidth = Math.min(28, (right - left) / Math.max(years.length, 1) * 0.72);
    const barWidth = groupWidth / series.length;
    marks = years.map((year, yearIndex) => series.map((item, seriesIndex) => {
      const row = rows.find((candidate) => Number(candidate.year) === year && item.matches(candidate));
      const value = row ? Number(item.value(row)) : NaN;
      if (!Number.isFinite(value)) return "";
      const barX = x(yearIndex) - groupWidth / 2 + seriesIndex * barWidth;
      return `<g><title>${escapeHtml(item.label)} · ${year}: ${formatCommerceValue(value)} ${escapeHtml(unit)}</title><rect x="${barX}" y="${y(value)}" width="${Math.max(2, barWidth - 1)}" height="${bottom - y(value)}" rx="2" fill="${item.color}"/></g>`;
    }).join("")).join("");
  } else {
    marks = series.map((item) => {
      const points = years.map((year, index) => {
        const row = rows.find((candidate) => Number(candidate.year) === year && item.matches(candidate));
        const value = row ? Number(item.value(row)) : NaN;
        return Number.isFinite(value) ? { year, index, value } : null;
      }).filter(Boolean);
      const path = points.map((point, index) => `${index ? "L" : "M"}${x(point.index)},${y(point.value)}`).join(" ");
      return `<path d="${path}" fill="none" stroke="${item.color}" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>${points.map((point) => `<g><title>${escapeHtml(item.label)} · ${point.year}: ${formatCommerceValue(point.value)} ${escapeHtml(unit)}</title><circle cx="${x(point.index)}" cy="${y(point.value)}" r="3.5" fill="${item.color}"/></g>`).join("")}`;
    }).join("");
  }
  const legend = series.map((item) => `<span><i style="--commerce-series:${item.color}"></i>${escapeHtml(item.label)}</span>`).join("");
  root.innerHTML = `<figure><svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(series.map((item) => item.label).join(" and "))} by year"><title>${escapeHtml(series.map((item) => item.label).join(" and "))} by year</title>${grid}<line x1="${left}" y1="${bottom}" x2="${right}" y2="${bottom}" class="commerce-chart-axis"/>${marks}${labels}</svg><figcaption>${legend}<span class="commerce-chart-unit">${escapeHtml(unit)}</span></figcaption></figure><p class="commerce-chart-note">Showing ${escapeHtml(periodLabel)}.</p>`;
}

function renderCommerceDashboard(data = commerceSnapshot) {
  if (!data) return;
  commerceSnapshot = data;
  const yearSelect = $("#commerce-year-filter");
  const selectedYear = yearSelect.value;
  const years = [...new Set([
    ...(data.sales_by_year || []).map((row) => row.year),
    ...(data.inventory_by_year || []).map((row) => row.year),
    ...(data.promotions_by_year || []).map((row) => row.year),
    ...(data.promotions_by_campaign || []).map((row) => row.year),
    ...(data.logistics_by_year_region || []).map((row) => row.year),
  ].filter(Number.isFinite))].sort((a, b) => a - b);
  yearSelect.innerHTML = '<option value="">All available years</option>' + years.map((year) =>
    `<option value="${year}">${year}</option>`).join("");
  yearSelect.value = years.includes(Number(selectedYear)) ? selectedYear : "";
  const year = yearSelect.value ? Number(yearSelect.value) : null;
  const byYear = (rows) => rows.filter((row) => year == null || Number(row.year) === year);
  const activeView = document.querySelector('[data-commerce-view][aria-selected="true"]')?.dataset.commerceView || "inventory";
  const yearLabel = year == null ? "All available years" : `Year ${year}`;
  if (activeView === "inventory") {
    const rows = byYear(data.inventory_by_year || []);
    const latest = rows.at(-1) || {};
    const inventoryPeriod = year == null ? `Latest annual data: ${latest.year ?? "—"}` : yearLabel;
    const annualCategoryRows = data.inventory_year_end_by_category || [];
    const categoryYear = year ?? annualCategoryRows.at(-1)?.year ?? null;
    const categoryRows = categoryYear == null ? [] : annualCategoryRows.filter((row) => Number(row.year) === Number(categoryYear));
    const stockoutProducts = categoryRows.reduce((sum, row) => sum + Number(row.stockout_products || 0), 0);
    const overstockProducts = categoryRows.reduce((sum, row) => sum + Number(row.overstock_products || 0), 0);
    const bothFlaggedProducts = categoryRows.reduce((sum, row) => sum + Number(row.both_flagged_products || 0), 0);
    const stockoutDays = Number(latest.avg_stockout_days);
    renderCommerceCards([
      ["SKU snapshots", formatCommerceValue(latest.sku_snapshots), inventoryPeriod],
      ["Average units on hand", formatCommerceValue(latest.avg_stock_on_hand), inventoryPeriod],
      ["Stockout snapshots", formatCommerceValue(latest.stockout_snapshots), `${inventoryPeriod}; not unique products`],
      ["Overstock snapshots", formatCommerceValue(latest.overstock_snapshots), `${inventoryPeriod}; days-of-supply excluded`],
      ["Average stockout days", Number.isFinite(stockoutDays) ? stockoutDays.toFixed(2) : "—", inventoryPeriod],
      ["Selected snapshot · stockout / overstock / both flags", `${formatCommerceValue(stockoutProducts)} / ${formatCommerceValue(overstockProducts)} / ${formatCommerceValue(bothFlaggedProducts)}`, `Latest snapshot in ${categoryYear}; both flags can apply to one product`],
    ], "Synthetic dataset observation");
  } else if (activeView === "promotions") {
    const rows = byYear(data.promotions_by_year || []);
    const tagged = rows.filter((row) => row.used_promotion);
    const plain = rows.filter((row) => !row.used_promotion);
    const sum = (items, key) => items.reduce((total, row) => total + Number(row[key] || 0), 0);
    const taggedOrders = sum(tagged, "delivered_orders");
    const plainOrders = sum(plain, "delivered_orders");
    const paired = (key) => `${formatCommerceValue(sum(tagged, key))} / ${formatCommerceValue(sum(plain, key))}`;
    const marginProxy = (items) => {
      const sales = sum(items, "net_sales");
      return sales ? `${(sum(items, "merchandise_gross_profit_proxy") / sales * 100).toFixed(1)}%` : "—";
    };
    renderCommerceCards([
      ["Delivered order groups · tagged / untagged", `${formatCommerceValue(taggedOrders)} / ${formatCommerceValue(plainOrders)}`, yearLabel],
      ["Net sales · tagged / untagged items", paired("net_sales"), "Dataset units; currency not declared"],
      ["Units · tagged / untagged items", paired("units"), yearLabel],
      ["Recorded discounts · tagged / untagged", paired("discounts"), "Dataset units; currency not declared"],
      ["Gross-profit proxy · tagged / untagged", paired("merchandise_gross_profit_proxy"), "Net item sales less catalog COGS; estimate only"],
      ["Gross-margin proxy · tagged / untagged", `${marginProxy(tagged)} / ${marginProxy(plain)}`, "Catalog COGS assumption; not contribution margin or ROI"],
    ], "Mixed orders may count in both groups; comparison is not causal. Validate catalog COGS before using the gross-profit proxy.");
  } else {
    const rows = byYear(data.logistics_by_year_region || []);
    const deliveries = rows.reduce((sum, row) => sum + Number(row.deliveries || 0), 0);
    const weighted = (key) => deliveries ? rows.reduce((sum, row) => sum + Number(row[key] || 0) * Number(row.deliveries || 0), 0) / deliveries : NaN;
    const regionalMedians = rows.map((row) => Number(row.median_transit_days)).filter(Number.isFinite);
    const medianRange = regionalMedians.length ? `${Math.min(...regionalMedians).toFixed(1)}–${Math.max(...regionalMedians).toFixed(1)} days` : "—";
    renderCommerceCards([
      ["Delivered shipments", formatCommerceValue(deliveries), yearLabel],
      ["Weighted average transit", Number.isFinite(weighted("avg_transit_days")) ? `${weighted("avg_transit_days").toFixed(2)} days` : "—", "Weighted by delivered shipments"],
      ["Regional median range", medianRange, "Range across displayed dataset regions"],
      ["Weighted average shipping fee", formatCommerceValue(weighted("avg_shipping_fee")), "Dataset units; currency not declared"],
    ], "Descriptive regional summary; no carrier or route-level data");
  }
  const inventoryRows = byYear(data.inventory_by_year || []);
  renderCommerceChart("#commerce-inventory-chart", inventoryRows, [
    { label: "Stockout snapshots", color: "#c54845", matches: () => true, value: (row) => row.stockout_snapshots },
    { label: "Overstock snapshots", color: "#3972bd", matches: () => true, value: (row) => row.overstock_snapshots },
  ], "snapshot count", "line", yearLabel);
  const promotionRows = byYear(data.promotions_by_year || []);
  renderCommerceChart("#commerce-promotion-chart", promotionRows, [
    { label: "Items with promotion tag", color: "#3972bd", matches: (row) => row.used_promotion, value: (row) => row.net_sales },
    { label: "Items without promotion tag", color: "#48a17c", matches: (row) => !row.used_promotion, value: (row) => row.net_sales },
  ], "net sales · dataset units", "bar", yearLabel);
  const logisticsRows = byYear(data.logistics_by_year_region || []);
  const regionColors = ["#3972bd", "#48a17c", "#d58c35", "#8761bd"];
  const regions = [...new Set(logisticsRows.map((row) => row.region))].sort();
  renderCommerceChart("#commerce-logistics-chart", logisticsRows, regions.map((region, index) => ({
    label: region, color: regionColors[index % regionColors.length],
    matches: (row) => row.region === region, value: (row) => row.avg_transit_days,
  })), "average transit days", "line", yearLabel);
  $("#commerce-sales-table").innerHTML = commerceTable(byYear(data.sales_by_year || []), [
    ["year", "Year"], ["revenue", "Revenue", formatCommerceValue], ["cogs", "COGS", formatCommerceValue], ["gross_profit", "Gross profit", formatCommerceValue],
    ["gross_margin", "Gross margin", (value) => Number.isFinite(Number(value)) ? `${(Number(value) * 100).toFixed(1)}%` : "—"],
  ]);
  $("#commerce-inventory-table").innerHTML = commerceTable(byYear(data.inventory_by_year || []), [
    ["year", "Year"], ["products", "Products"], ["sku_snapshots", "SKU snapshots"], ["avg_stock_on_hand", "Avg units on hand", formatCommerceValue],
    ["stockout_snapshots", "Stockout snapshots"], ["overstock_snapshots", "Overstock snapshots"],
    ["avg_stockout_days", "Avg stockout days"],
  ]);
  const annualCategoryRows = data.inventory_year_end_by_category || [];
  const categoryYear = year ?? annualCategoryRows.at(-1)?.year ?? null;
  const categoryRows = categoryYear == null ? [] : annualCategoryRows.filter((row) => Number(row.year) === Number(categoryYear));
  $("#commerce-inventory-category").innerHTML = commerceTable(categoryRows, [
    ["category", "Category"], ["products", "Products"], ["stock_on_hand", "Units on hand", formatCommerceValue],
    ["stockout_products", "Stockout products"], ["overstock_products", "Overstock products"],
    ["both_flagged_products", "Both flags"],
  ]);
  $("#commerce-inventory-latest-date").textContent = categoryRows[0]?.snapshot_date
    ? `· Year ${categoryYear}: ${categoryRows[0].snapshot_date}` : "";
  $("#commerce-promotion-table").innerHTML = commerceTable(byYear(data.promotions_by_year || []), [
    ["year", "Year"], ["used_promotion", "Promotion tagged", (value) => value ? "Yes" : "No"],
    ["delivered_orders", "Delivered orders"], ["units", "Units"], ["net_sales", "Net sales", formatCommerceValue],
    ["discounts", "Recorded discounts", formatCommerceValue], ["catalog_cogs", "Catalog COGS", formatCommerceValue],
    ["merchandise_gross_profit_proxy", "Gross-profit proxy", formatCommerceValue],
    ["merchandise_gross_margin_proxy", "Gross-margin proxy", (value) => Number.isFinite(Number(value)) ? `${(Number(value) * 100).toFixed(1)}%` : "—"],
  ]);
  $("#commerce-campaign-table").innerHTML = commerceTable(byYear(data.promotions_by_campaign || []), [
    ["campaign", "Campaign"], ["channel", "Channel"], ["campaign_start", "Window starts"],
    ["campaign_end", "Window ends"], ["delivered_orders", "Delivered orders"], ["units", "Tagged units"],
    ["net_item_sales", "Tagged net item sales", formatCommerceValue], ["discounts", "Recorded discounts", formatCommerceValue],
    ["catalog_cogs", "Catalog COGS", formatCommerceValue],
    ["merchandise_gross_profit_proxy", "Gross-profit proxy", formatCommerceValue],
    ["merchandise_gross_margin_proxy", "Gross-margin proxy", (value) => Number.isFinite(Number(value)) ? `${(Number(value) * 100).toFixed(1)}%` : "—"],
  ]);
  $("#commerce-logistics-table").innerHTML = commerceTable(byYear(data.logistics_by_year_region || []), [
    ["year", "Year"], ["region", "Dataset region"], ["deliveries", "Deliveries"],
    ["avg_transit_days", "Avg transit days"], ["median_transit_days", "Median transit days"],
    ["avg_shipping_fee", "Avg shipping fee · dataset units"],
  ]);
  $("#commerce-data-notes-list").innerHTML = (data.data_notes || []).map((note) => `<li>${escapeHtml(note)}</li>`).join("");
}

document.querySelectorAll("[data-commerce-view]").forEach((button) => {
  button.addEventListener("click", () => {
    $("#commerce-dashboard-status").hidden = true;
    document.querySelectorAll("[data-commerce-view]").forEach((tab) => {
      const selected = tab === button;
      tab.setAttribute("aria-selected", String(selected));
      $("#commerce-view-" + tab.dataset.commerceView).hidden = !selected;
    });
    const domainByView = {
      inventory: "inventory_allocation",
      promotions: "promotion_planning",
      logistics: "nationwide_logistics",
    };
    $("#commerce-decision-domain").value = domainByView[button.dataset.commerceView];
    renderDecisionDomainQuestions($("#commerce-decision-domain").value);
    renderCommerceDashboard();
    loadCommerceDashboardForActiveView();
  });
});
$("#commerce-campaign-details").addEventListener("toggle", (event) => {
  if (event.currentTarget.open) loadCommerceCampaigns();
});
$(".commerce-dashboard-tabs").addEventListener("keydown", (event) => {
  const tabs = [...document.querySelectorAll("[data-commerce-view]")];
  const current = tabs.indexOf(event.target);
  const next = { ArrowRight: (current + 1) % tabs.length, ArrowLeft: (current - 1 + tabs.length) % tabs.length,
    Home: 0, End: tabs.length - 1 }[event.key];
  if (current < 0 || next === undefined) return;
  event.preventDefault();
  tabs[next].focus();
  tabs[next].click();
});
$("#commerce-year-filter").addEventListener("change", () => renderCommerceDashboard());
$("#commerce-decision-domain").addEventListener("change", () => {
  renderDecisionDomainQuestions($("#commerce-decision-domain").value);
  const viewByDomain = {
    inventory_allocation: "inventory",
    promotion_planning: "promotions",
    nationwide_logistics: "logistics",
  };
  document.querySelector(`[data-commerce-view="${viewByDomain[$("#commerce-decision-domain").value]}"]`)?.click();
});

function financialDisplayItem(item) {
  const sourceUnit = String(item.unit || "").trim().toLocaleLowerCase();
  const scaleToBillionVnd = {
    "vnd": 1e-9,
    "million vnd": 1e-3,
    "triệu vnd": 1e-3,
    "billion vnd": 1,
    "tỷ đồng": 1,
  }[sourceUnit];
  if (scaleToBillionVnd === undefined) return item;
  return {
    ...item,
    metric_value: Number((Number(item.metric_value) * scaleToBillionVnd).toFixed(3)),
    source_unit: item.unit,
    unit: "billion VND",
  };
}

function metricSeriesKey(item) {
  return [item.company, item.domain || "financial", item.metric_name, item.unit || "unknown unit",
    item.reporting_period || "FY"].join(":");
}

function formatBusinessMetricValue(item) {
  const prefix = {
    approximately: "≈",
    more_than: ">",
    at_least: "≥",
    less_than: "<",
    at_most: "≤",
  }[item.value_qualifier] || "";
  return `${prefix}${formatFinancialValue(item.metric_value)}`;
}

function formatBusinessMetricPeriod(item) {
  return `${item.reporting_period && item.reporting_period !== "FY" ? `${item.reporting_period} ` : "FY "}${item.fiscal_year}`;
}

function parseVietnameseFinancialInput(value) {
  const text = String(value ?? "").trim();
  const grouped = /^[+-]?\d{1,3}(?:\.\d{3})+(?:,\d+)?$/.test(text);
  const plain = /^[+-]?\d+(?:,\d+)?$/.test(text);
  const dotDecimal = /^[+-]?\d+\.\d+$/.test(text);
  if (!grouped && !plain && !dotDecimal) return NaN;
  const canonical = grouped ? text.replace(/\./g, "").replace(",", ".") : text.replace(",", ".");
  return Number(canonical);
}

function renderCandidateFigures(figures) {
  if (!figures.length) return "<span>No numeric token detected</span>";
  return figures.map((figure) => `<button type="button" data-candidate-value="${escapeHtml(figure)}" aria-pressed="false">${escapeHtml(figure)}</button>`).join("");
}

function normalizeCandidateFigure(value) {
  const text = String(value).trim();
  // Parser figures are source-grounded integer tokens; preserve their exact digits.
  return /^[+-]?\d{1,3}([.,])\d{3}(?:\1\d{3})*$/.test(text)
    ? text.replace(/[.,]/g, "")
    : text;
}

function decisionReadyBusinessDomains(items) {
  const byDomain = new Map();
  for (const item of items || []) {
    if (!item.domain || !item.metric_name || !item.unit || (item.reporting_period && item.reporting_period !== "FY")) continue;
    const definition = businessMetricDefinitions.get(item.metric_name);
    if (definition?.decision_priority !== "primary" || definition.domain !== item.domain) continue;
    const year = Number(item.fiscal_year);
    if (!Number.isInteger(year)) continue;
    const key = `${item.metric_name}:${item.unit}`;
    const series = byDomain.get(item.domain) || new Map();
    const years = series.get(key) || new Set();
    years.add(year);
    series.set(key, years);
    byDomain.set(item.domain, series);
  }
  return [...byDomain].filter(([, series]) => {
    const years = [...new Set([...series.values()].flatMap((values) => [...values]))].sort((a, b) => a - b);
    const recent = years.slice(-3);
    if (recent.length < 3 || recent.some((year, index) => index > 0 && year !== recent[index - 1] + 1)) return false;
    return [...series.values()].filter((values) => recent.every((year) => values.has(year))).length >= 2;
  }).map(([domain]) => domain).filter((domain) => ["milk_supply", "market_performance"].includes(domain)).sort();
}

const marketMetricLabels = {
  domestic_consolidated_net_revenue: "Domestic Revenue",
  overseas_market_net_revenue: "Overseas Revenue",
  domestic_consolidated_net_revenue_growth: "Domestic Revenue Growth",
  overseas_market_net_revenue_growth: "Overseas Revenue Growth",
  domestic_segment_gross_profit: "Domestic Segment Gross Profit",
  overseas_segment_gross_profit: "Overseas Segment Gross Profit",
  domestic_revenue_share: "Domestic Revenue Share",
  overseas_revenue_share: "Overseas Revenue Share",
  parent_domestic_net_revenue: "Parent-company Domestic Revenue",
  parent_domestic_net_revenue_growth: "Parent-company Domestic Growth",
  export_net_revenue: "Export Net Revenue",
  foreign_subsidiary_revenue: "Foreign Subsidiaries' Revenue",
  export_markets_count: "Export Markets Reached",
  new_export_markets_entered: "New Export Markets",
  export_volume_teu: "Export Volume",
  export_trade_promotion_programs: "Trade-promotion Programs",
  vinamilk_stores: "Vinamilk Stores",
  retail_points_of_sale: "Retail Points of Sale",
};

function marketMetricLabel(name, item = {}) {
  return marketMetricLabels[name] || businessMetricDefinitions.get(name)?.label || item.metric_label || name;
}

function marketYear(item) {
  return Number(item.fiscal_year);
}

function marketPeriod(item) {
  return item.reporting_period || "FY";
}

function marketScopeDimension(item) {
  const scope = String(item.scope || "").toLocaleLowerCase();
  const geography = /overseas|outside vietnam/.test(scope) ? "overseas"
    : /domestic|in vietnam|located in vietnam/.test(scope) ? "domestic" : "";
  const entity = /parent company|parent-company|standalone/.test(scope) ? "parent"
    : /geographic segment|customers located/.test(scope) ? "geographic-segment"
    : /consolidat/.test(scope) ? "consolidated"
    : /market/.test(scope) ? "market" : "";
  return geography && entity ? `${entity}:${geography}` : scope.replace(/\s+/g, " ").trim();
}

function marketComparableDimension(item) {
  return [item.company, item.unit, marketScopeDimension(item), marketPeriod(item), item.value_qualifier || "exact"];
}

function marketComparableSeries(items) {
  const ordered = [...items].sort((a, b) => marketYear(a) - marketYear(b));
  if (ordered.length < 2 || ordered.some((item) => !String(item.scope || "").trim()
      || (item.value_qualifier || "exact") !== "exact")) return [];
  const dimension = JSON.stringify(marketComparableDimension(ordered[0]));
  if (ordered.some((item) => JSON.stringify(marketComparableDimension(item)) !== dimension)) return [];
  if (new Set(ordered.map(marketYear)).size !== ordered.length) return [];
  return ordered;
}

function marketSourceLink(item) {
  if (item.sourceRows?.length) {
    return item.sourceRows.map((row) => `${escapeHtml(marketMetricLabel(row.metric_name, row))}: ${escapeHtml(formatBusinessMetricValue(row))} ${escapeHtml(row.unit)} · ${marketSourceLink(row)}`).join("<br>");
  }
  const href = uploadedSourcePageUrl(item.source_document_id, item.page_number)
    || sourcePageUrl(item.source_url, item.page_number);
  return href ? `<a href="${escapeHtml(href)}" target="_blank" rel="noopener noreferrer">Source · p. ${escapeHtml(item.page_number ?? "—")}</a>` : "Source link unavailable";
}

function marketMetricCard(item) {
  const definition = businessMetricDefinitions.get(item.metric_name);
  const definitionText = definition?.definition || "Definition is not recorded in the metric catalog.";
  const unitGuidance = definition?.unit_guidance || item.unit || "Use the source-reported unit.";
  const qualifier = {
    approximately: "Approximate",
    more_than: "Lower bound",
    at_least: "At least",
    less_than: "Upper bound",
    at_most: "At most",
  }[item.value_qualifier] || "Verified";
  return `<article class="market-kpi-card">
    <span class="market-kpi-label">${escapeHtml(marketMetricLabel(item.metric_name, item))}</span>
    <strong>${formatBusinessMetricValue(item)} <small>${escapeHtml(item.unit || unitGuidance)}</small></strong>
    <div class="market-kpi-meta"><span>FY ${escapeHtml(item.fiscal_year)}</span><span>${escapeHtml(qualifier)}</span></div>
    ${marketSourceLink(item)}
    <details><summary>Definition &amp; scope</summary><p>${escapeHtml(definitionText)}</p><small>${escapeHtml(item.scope || unitGuidance)}</small>${item.source_quote ? `<blockquote>${escapeHtml(item.source_quote)}</blockquote>` : ""}</details>
  </article>`;
}

function latestMarketCards(items, metricNames) {
  return metricNames.flatMap((metricName) => {
    const byCompany = new Map();
    for (const item of items.filter((row) => row.metric_name === metricName)) {
      const companyRows = byCompany.get(item.company) || [];
      companyRows.push(item);
      byCompany.set(item.company, companyRows);
    }
    return [...byCompany.values()].flatMap((companyRows) => {
      const latestYear = Math.max(...companyRows.map(marketYear));
      return companyRows.filter((item) => marketYear(item) === latestYear)
        .map((item) => marketMetricCard(item));
    });
  });
}

function pairedMarketMetric(revenueRows, profitRows) {
  const profits = new Map();
  for (const item of profitRows) {
    const key = `${item.company}:${marketYear(item)}:${marketPeriod(item)}`;
    const rows = profits.get(key) || [];
    rows.push(item);
    profits.set(key, rows);
  }
  return revenueRows.flatMap((revenue) => {
    const matching = profits.get(`${revenue.company}:${marketYear(revenue)}:${marketPeriod(revenue)}`) || [];
    if (matching.length !== 1) return [];
    const profit = matching[0];
    if (!profit || revenue.scope !== profit.scope || revenue.unit !== profit.unit
        || (revenue.value_qualifier || "exact") !== "exact" || (profit.value_qualifier || "exact") !== "exact") return [];
    const denominator = Number(revenue.metric_value);
    const numerator = Number(profit.metric_value);
    if (!Number.isFinite(denominator) || denominator <= 0 || !Number.isFinite(numerator)) return [];
    return [{
      metric_name: "segment_gross_margin", metric_label: `${revenue.metric_label} gross margin`,
      company: revenue.company, fiscal_year: revenue.fiscal_year, reporting_period: marketPeriod(revenue),
      unit: "%", scope: revenue.scope, value_qualifier: "exact", metric_value: numerator / denominator * 100,
      sourceRows: [revenue, profit],
    }];
  }).sort((a, b) => marketYear(a) - marketYear(b));
}

function alignMarketSeries(items, metricNames) {
  const series = metricNames.map((name) => marketComparableSeries(items.filter((item) => item.metric_name === name)));
  if (series.some((rows) => rows.length < 2)) return [];
  // Domestic and overseas are intentionally different scopes. Each series
  // must keep a stable semantic scope over time; phrasing/year labels can vary.
  const dimensionsMatch = series.every((rows) => {
    const [first] = rows;
    return rows.every((item) => item.company === first.company
      && item.unit === first.unit && marketPeriod(item) === marketPeriod(first));
  });
  if (!dimensionsMatch || series.some((rows) => rows[0].company !== series[0][0].company
      || rows[0].unit !== series[0][0].unit || marketPeriod(rows[0]) !== marketPeriod(series[0][0]))) return [];
  const years = new Set(series[0].map(marketYear));
  for (const rows of series.slice(1)) {
    const available = new Set(rows.map(marketYear));
    for (const year of years) if (!available.has(year)) years.delete(year);
  }
  if (years.size < 2) return [];
  return series.map((rows) => rows.filter((item) => years.has(marketYear(item))));
}

function marketValuesTable(series) {
  const rows = series.flatMap(({label, observations}) => observations.map((item) => `<tr>
    <th scope="row">${escapeHtml(label)}</th><td>FY ${escapeHtml(item.fiscal_year)}</td>
    <td>${escapeHtml(formatBusinessMetricValue(item))} ${escapeHtml(item.unit)}</td><td>${escapeHtml(item.scope || "Not stated")}</td>
    <td>${marketSourceLink(item)}</td></tr>`)).join("");
  return `<details class="market-source-values"><summary>Values, scope and sources</summary><div class="market-values-scroll"><table><thead><tr><th>Measure</th><th>Period</th><th>Value</th><th>Scope</th><th>Evidence</th></tr></thead><tbody>${rows}</tbody></table></div></details>`;
}

function renderMarketSvg(series, kind = "line") {
  const width = 760, height = 250, left = 58, right = 742, top = 16, bottom = 192;
  const observations = series.flatMap((item) => item.observations);
  const years = [...new Set(observations.map(marketYear))].sort((a, b) => a - b);
  const values = observations.map((item) => Number(item.metric_value));
  const rawMin = Math.min(0, ...values), rawMax = Math.max(1, ...values);
  const padding = (rawMax - rawMin) * 0.08;
  const min = rawMin < 0 ? rawMin - padding : 0;
  const max = rawMax + padding;
  const y = (value) => bottom - ((Number(value) - min) / (max - min)) * (bottom - top);
  const x = (yearIndex) => years.length < 2 ? (left + right) / 2 : left + yearIndex * (right - left) / (years.length - 1);
  const palette = ["#2868c7", "#2d9870", "#8761bd"];
  const grids = Array.from({length: 4}, (_, index) => {
    const value = min + (max - min) * index / 3;
    const yy = y(value);
    return `<g><line x1="${left}" y1="${yy}" x2="${right}" y2="${yy}" class="market-gridline"/><text x="${left - 9}" y="${yy + 4}" text-anchor="end" class="market-axis-label">${escapeHtml(formatFinancialValue(value))}</text></g>`;
  }).join("");
  const xLabels = years.map((year, index) => `<text x="${x(index)}" y="${bottom + 23}" text-anchor="middle" class="market-axis-label">FY ${year}</text>`).join("");
  let marks = "";
  if (kind === "grouped-bar") {
    const clusterWidth = Math.min(48, (right - left) / Math.max(years.length, 1) * 0.48);
    marks = series.map((entry, seriesIndex) => entry.observations.map((item) => {
      const yearIndex = years.indexOf(marketYear(item));
      const center = x(yearIndex);
      const offset = (seriesIndex - (series.length - 1) / 2) * (clusterWidth / series.length);
      const barWidth = clusterWidth / series.length - 3;
      const zero = y(0), valueY = y(item.metric_value);
      return `<rect x="${center + offset - barWidth / 2}" y="${Math.min(zero, valueY)}" width="${barWidth}" height="${Math.max(1, Math.abs(zero - valueY))}" rx="3" fill="${palette[seriesIndex % palette.length]}"><title>${escapeHtml(entry.label)} · FY ${escapeHtml(item.fiscal_year)}: ${escapeHtml(formatBusinessMetricValue(item))} ${escapeHtml(item.unit)}</title></rect>`;
    }).join("")).join("");
  } else {
    marks = series.map((entry, seriesIndex) => {
      const points = entry.observations.map((item) => `${x(years.indexOf(marketYear(item)))},${y(item.metric_value)}`).join(" ");
      const line = `<polyline points="${points}" fill="none" stroke="${palette[seriesIndex % palette.length]}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>`;
      const dots = entry.observations.map((item) => `<circle cx="${x(years.indexOf(marketYear(item)))}" cy="${y(item.metric_value)}" r="4.5" fill="${palette[seriesIndex % palette.length]}"><title>${escapeHtml(entry.label)} · FY ${escapeHtml(item.fiscal_year)}: ${escapeHtml(formatBusinessMetricValue(item))} ${escapeHtml(item.unit)}</title></circle>`).join("");
      return line + dots;
    }).join("");
  }
  const legends = series.map((entry, index) => `<span><i style="--legend-color:${palette[index % palette.length]}"></i>${escapeHtml(entry.label)}</span>`).join("");
  const units = [...new Set(observations.map((item) => item.unit).filter(Boolean))];
  return `<figure class="market-figure"><svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(series.map((entry) => entry.label).join(" and "))} by fiscal year">${grids}<line x1="${left}" y1="${bottom}" x2="${right}" y2="${bottom}" class="market-axis"/>${marks}${xLabels}</svg><figcaption class="market-legend">${legends}<span class="market-chart-unit">${escapeHtml(units.join(" / "))}</span></figcaption></figure>${marketValuesTable(series)}`;
}

function marketChartUnavailable(element, message) {
  element.innerHTML = `<div class="market-chart-empty"><strong>Not charted</strong><p>${escapeHtml(message)}</p></div>`;
}

function renderMarketPerformanceDashboard(items) {
  const itemByName = (name) => items.filter((item) => item.metric_name === name);
  const chartOrEmpty = (selector, metricNames, kind) => {
    const target = $(selector);
    const aligned = alignMarketSeries(items, metricNames);
    if (!aligned.length) {
      marketChartUnavailable(target, "The visible observations do not provide at least two exact, like-for-like periods with matching company, scope, reporting period and unit.");
      return;
    }
    const labeled = aligned.map((observations, index) => ({
      label: marketMetricLabel(metricNames[index], observations[0]), observations,
    }));
    target.innerHTML = renderMarketSvg(labeled, kind);
  };

  const coreNames = [
    "domestic_consolidated_net_revenue", "overseas_market_net_revenue", "overseas_revenue_share", "export_net_revenue",
  ];
  $("#market-core-cards").innerHTML = latestMarketCards(items, coreNames).join("")
    || '<p class="analysis-empty">No verified core market-performance observations in this selection.</p>';
  chartOrEmpty("#market-revenue-trend", ["domestic_consolidated_net_revenue", "overseas_market_net_revenue"], "line");
  chartOrEmpty("#market-revenue-growth", ["domestic_consolidated_net_revenue_growth", "overseas_market_net_revenue_growth"], "grouped-bar");

  const marginDefinitions = [
    {label: "Domestic", revenue: "domestic_consolidated_net_revenue", profit: "domestic_segment_gross_profit"},
    {label: "Overseas", revenue: "overseas_market_net_revenue", profit: "overseas_segment_gross_profit"},
  ];
  const marginSeries = marginDefinitions.map((segment) => ({
    label: `${segment.label} gross margin`,
    observations: marketComparableSeries(pairedMarketMetric(itemByName(segment.revenue), itemByName(segment.profit))),
  }));
  const commonMarginYears = marginSeries[0].observations.filter((row) =>
    marginSeries[1].observations.some((other) => marketYear(other) === marketYear(row)
      && other.company === row.company && other.unit === row.unit
      && other.reporting_period === row.reporting_period)
  );
  const commonOverseas = marginSeries[1].observations.filter((row) => commonMarginYears.some((other) => marketYear(other) === marketYear(row)));
  if (commonMarginYears.length < 2 || new Set([...commonMarginYears, ...commonOverseas].map((row) => row.unit)).size !== 1) {
    marketChartUnavailable($("#market-profitability"), "Verified domestic and overseas gross-profit/revenue pairs do not yet share two comparable years, scope, period and unit.");
  } else {
    $("#market-profitability").innerHTML = renderMarketSvg([
      {label: marginSeries[0].label, observations: commonMarginYears},
      {label: marginSeries[1].label, observations: commonOverseas},
    ]);
  }

  const channelCardNames = ["commercial_export_revenue", "foreign_subsidiary_revenue"];
  $("#market-channel-cards").innerHTML = latestMarketCards(items, channelCardNames).join("")
    || '<p class="analysis-empty">No verified international-channel observations in this selection.</p>';
  chartOrEmpty("#market-channel-trend", ["export_net_revenue", "foreign_subsidiary_revenue"], "grouped-bar");
  const highlightNames = ["guinea_export_revenue_growth", "hong_kong_export_revenue_growth", "japan_export_revenue_growth"];
  const highlightCards = latestMarketCards(items, highlightNames);
  $("#market-market-highlights").innerHTML = highlightCards.length
    ? `<div class="market-section-heading"><div><p class="eyebrow">SELECTED DISCLOSED MARKETS</p><h4>Export market highlights</h4></div><p>These reported markets are examples, not a ranking of all export destinations.</p></div><div class="market-kpi-grid market-highlight-grid">${highlightCards.join("")}</div>`
    : "";
  const footprintNames = ["export_markets_count", "new_export_markets_entered", "export_volume_teu", "export_trade_promotion_programs", "vinamilk_stores", "retail_points_of_sale"];
  const footprint = latestMarketCards(items, footprintNames);
  $("#market-footprint").innerHTML = footprint.join("")
    || '<p class="analysis-empty">No verified market-footprint observations in this selection.</p>';
  const glossaryNames = ["export_net_revenue", "commercial_export_revenue", "overseas_market_net_revenue", "foreign_subsidiary_revenue"];
  $("#market-glossary-content").innerHTML = `<p class="market-definition-note">Export net revenue and commercial export revenue are separate reported measures. They are not combined or compared until their source definitions and boundaries are confirmed.</p>` + glossaryNames.map((name) => {
    const definition = businessMetricDefinitions.get(name);
    return `<article><h5>${escapeHtml(marketMetricLabels[name] || definition?.label || name)}</h5><p>${escapeHtml(definition?.definition || "Definition not available in catalog.")}</p><small>${escapeHtml(definition?.unit_guidance || "Reported unit")}</small></article>`;
  }).join("");
}

const DECISION_DOMAIN_QUESTIONS = {
  inventory_allocation: [
    {
      title: "Where are stockouts and excess inventory concentrated?",
      question: "Which product categories show the strongest combination of stockout and overstock signals in the latest snapshot, and how do the last three annual inventory summaries compare? Recommend a bounded investigation, not a stock transfer, because warehouse locations, lead times, demand forecasts, and transfer costs are unavailable.",
    },
    {
      title: "What should be checked before reallocating stock?",
      question: "Should inventory be reallocated toward products with repeated stockout signals? Use only the Commerce inventory aggregates and company references. State the warehouse-level stock, forecast demand, replenishment lead time, transfer cost, and target service level needed before moving stock.",
    },
    {
      title: "Generate conditional inventory actions",
      question: "Suggest up to three conditional next actions for inventory allocation from the available SQL observations and company practice references. Do not invent numeric thresholds or assume the synthetic dataset represents one company's live warehouse network.",
    },
  ],
  promotion_planning: [
    {
      title: "How do promotion-tagged orders compare?",
      question: "Compare delivered orders, units, net sales, discounts, and the catalog-COGS merchandise gross-profit/margin proxy for promotion-tagged and untagged items in the latest three years. Treat the comparison as descriptive, not causal uplift; explain why the proxy is not contribution margin or ROI and what COGS validation, campaign spend, and holdout data are needed before changing promotion spend.",
    },
    {
      title: "Should we repeat a promotion?",
      question: "Should the business repeat or expand a promotion based on the available order data? Separate the catalog-COGS gross-profit proxy from contribution margin, explain why causal lift and ROI cannot be established without a holdout and campaign spend, and use a cited company measurement method for the next step.",
    },
    {
      title: "Generate conditional promotion actions",
      question: "Suggest up to three conditional next actions for promotion planning. Do not call tagged-versus-untagged differences uplift, treat the catalog-COGS proxy as contribution margin, set an unsourced discount threshold, or recommend scaling without causal and campaign-cost evidence.",
    },
  ],
  nationwide_logistics: [
    {
      title: "Which regions have longer transit times?",
      question: "Compare average and median ship-to-delivery time and shipping fees by dataset region for the latest three years. Recommend where to investigate, but do not infer a carrier, route, warehouse cause, or SLA breach from these aggregates.",
    },
    {
      title: "Would regional inventory placement help?",
      question: "Should the business consider regional inventory placement to improve delivery speed or cost? Compare available regional transit evidence with cited company practices, then identify the warehouse origin, route, capacity, carrier, demand, and cost data needed before a pilot.",
    },
    {
      title: "Generate conditional logistics actions",
      question: "Suggest up to three conditional next actions for nationwide logistics from the SQL observations and company references. Do not recommend network redesign from regional averages alone.",
    },
  ],
};

function renderDecisionDomainQuestions(domain) {
  const container = $("#decision-domain-questions");
  if (!container) return;
  container.innerHTML = (DECISION_DOMAIN_QUESTIONS[domain] || []).map(({ title, question }) =>
    `<button type="button" data-decision-question="${escapeHtml(question)}"><strong>${escapeHtml(title)}</strong><small>Select to load this question into the editor; review it before submitting.</small></button>`
  ).join("");
}

function renderAnalytics(data) {
  analyticsSnapshot = data;
  const companySelect = $("#analytics-company");
  const yearSelect = $("#analytics-year");
  const domainSelect = $("#commerce-decision-domain");
  const metricScopeSelect = $("#analytics-metric-scope");
  const selectedCompany = companySelect.value;
  const selectedYear = yearSelect.value;
  const selectedDomain = domainSelect.value;
  const companies = [...new Set(data.documents.map((item) => item.company).filter(Boolean))].sort();
  const years = [...new Set([
    ...data.documents.map((item) => item.fiscal_year),
    ...(data.financial || []).map((item) => item.fiscal_year),
    ...(data.business_metrics || []).map((item) => item.fiscal_year),
    ...(data.business_candidates || []).map((item) => item.fiscal_year),
  ].filter(Boolean).map(String))].sort();
  companySelect.innerHTML = '<option value="">All companies</option>' + companies.map((name) => `<option value="${escapeHtml(name)}">${escapeHtml(name)}</option>`).join("");
  yearSelect.innerHTML = '<option value="">All years</option>' + years.map((year) => `<option value="${escapeHtml(year)}">${escapeHtml(year)}</option>`).join("");
  const domains = decisionReadyBusinessDomains(data.business_metrics);
  const domainLabels = {
    milk_supply: "Raw Milk Supply Management",
    market_performance: "Domestic vs International Market Performance (Trial)",
  };
  domainSelect.innerHTML = domains.map((domain) =>
    `<option value="${escapeHtml(domain)}">${escapeHtml(domainLabels[domain] || domain.replaceAll("_", " "))}</option>`
  ).join("");
  companySelect.value = companies.includes(selectedCompany) ? selectedCompany : "";
  yearSelect.value = years.includes(selectedYear) ? selectedYear : "";
  domainSelect.value = domains.includes(selectedDomain) ? selectedDomain
    : domains.includes("milk_supply") ? "milk_supply" : domains[0] || "";
  const suggestionButton = document.querySelector("[data-decision-suggestions]");
  if (suggestionButton) suggestionButton.disabled = !domainSelect.value;
  metricScopeSelect.value = metricScopeSelect.value || "primary";
  companySelect.onchange = yearSelect.onchange = domainSelect.onchange = metricScopeSelect.onchange = applyAnalyticsFilters;
  applyAnalyticsFilters();
}

function applyAnalyticsFilters() {
  if (!analyticsSnapshot) return;
  const company = $("#analytics-company").value;
  const year = $("#analytics-year").value;
  const domain = $("#analytics-domain").value;
  const metricScope = $("#analytics-metric-scope").value;
  const isMarketPerformance = domain === "market_performance";
  $("#market-performance-dashboard").hidden = !isMarketPerformance;
  $("#business-metric-gallery").hidden = isMarketPerformance;
  $("#business-metric-scope-control").hidden = isMarketPerformance;
  $("#business-metric-title").textContent = isMarketPerformance
    ? "Market Performance"
    : domain === "milk_supply" ? "Raw Milk Supply Management" : "Business performance by decision domain";
  const matches = (item) => (!company || item.company === company) && (!year || String(item.fiscal_year ?? "") === year);
  const businessMatches = (item) => matches(item) && (!domain || item.domain === domain);
  const companyYearBusinessMetrics = (analyticsSnapshot.business_metrics || []).filter(matches);
  const scopedBusinessMetrics = companyYearBusinessMetrics.filter((item) => !domain || item.domain === domain);
  const data = {
    ...analyticsSnapshot,
    documents: analyticsSnapshot.documents.filter(matches),
    domains: analyticsSnapshot.domains.filter(matches),
    processing: analyticsSnapshot.processing.filter(matches),
    financial: analyticsSnapshot.financial.filter(matches),
    candidates: analyticsSnapshot.candidates.filter(matches),
    business_metrics: companyYearBusinessMetrics,
    business_candidates: (analyticsSnapshot.business_candidates || []).filter(businessMatches),
    quality: analyticsSnapshot.quality.filter(matches),
  };
  const roleVisibleMetricNames = new Set([
    ...data.financial.map((item) => item.metric_name),
    ...scopedBusinessMetrics.map((item) => item.metric_name),
  ]);
  document.querySelectorAll("[data-required-metrics]").forEach((button) => {
    const required = button.dataset.requiredMetrics.split(",").filter(Boolean);
    const requiredDomains = [...new Set(required.map((name) => businessMetricDefinitions.get(name)?.domain).filter(Boolean))];
    button.hidden = required.some((name) => !roleVisibleMetricNames.has(name))
      || (Boolean(domain) && requiredDomains.some((requiredDomain) => requiredDomain !== domain));
  });
  const metricGroups = data.financial.reduce((groups, sourceItem) => {
    const item = financialDisplayItem(sourceItem);
    const key = `${item.company}:${item.metric_name}:${item.unit || "unknown unit"}`;
    (groups[key] ??= []).push(item);
    return groups;
  }, {});
  const metrics = Object.values(metricGroups).map((series) =>
    series.sort((a, b) => Number(a.fiscal_year) - Number(b.fiscal_year))
  );
  const businessDisplayMetrics = metricScope === "all" || !businessMetricDefinitions.size ? scopedBusinessMetrics
    : scopedBusinessMetrics.filter((item) => businessMetricDefinitions.get(item.metric_name)?.decision_priority === "primary");
  const reports = data.documents.filter((item) => item.document_type === "annual_report");
  const reportYears = [...new Set(reports.map((item) => String(item.fiscal_year || "")).filter(Boolean))].sort();
  const verifiedMetrics = [...data.financial, ...businessDisplayMetrics];
  const verifiedSeries = new Set(verifiedMetrics.map((item) => metricSeriesKey(financialDisplayItem(item))));
  const verifiedYears = [...new Set(verifiedMetrics.map((item) => String(item.fiscal_year)))].sort();
  $("#analysis-summary").innerHTML = [
    ["Annual reports in scope", reports.length, reportYears.join(" · ") || "No fiscal year recorded"],
    ["Verified metric series shown", verifiedSeries.size, `${formatNumber(data.financial.length)} financial · ${formatNumber(businessDisplayMetrics.length)} business observations; supporting metrics remain available`],
    ["Verified reporting periods", verifiedYears.length, verifiedYears.join(" · ") || "Admin review required before comparison"],
  ].map(([label, value, note]) => `<article class="analysis-stat"><span>${escapeHtml(label)}</span><strong>${formatNumber(value)}</strong><small>${escapeHtml(note)}</small></article>`).join("");
  $("#analysis-coverage-note").textContent = `${formatNumber(data.documents.length)} source documents · ${formatNumber(data.documents.reduce((sum, item) => sum + item.chunks, 0))} indexed passages`;

  $("#financial-kpis").innerHTML = metrics.length ? metrics.map((series) => {
    const latest = series.at(-1);
    const previous = series.length > 1 ? series.at(-2) : null;
    const href = sourcePageUrl(latest.source_url, latest.page_number);
    const diff = previous ? Number(latest.metric_value) - Number(previous.metric_value) : 0;
    const isNegative = diff < 0;
    const comparison = previous && previous.unit === latest.unit
      ? `Change vs FY ${escapeHtml(previous.fiscal_year)}: ${diff >= 0 ? "+" : ""}${formatFinancialValue(diff)} ${escapeHtml(latest.unit)}${Number(previous.metric_value) ? ` (${formatFinancialValue(diff / Math.abs(Number(previous.metric_value)) * 100)}%)` : ""}`
      : "One verified reporting period";
    const provenance = latest.entry_method === "manual"
      ? `<span class="metric-provenance">Manual entry · admin verified${latest.verified_by ? ` by ${escapeHtml(latest.verified_by)}` : ""}</span>${latest.source_reference ? (validSourceUrl(latest.source_reference) ? `<a href="${escapeHtml(validSourceUrl(latest.source_reference))}" target="_blank" rel="noopener noreferrer">${escapeHtml(latest.source_reference)}</a>` : `<span>${escapeHtml(latest.source_reference)}</span>`) : ""}${latest.source_note ? `<details class="candidate-source"><summary>Verification context</summary><p>${escapeHtml(latest.source_note)}</p></details>` : ""}`
      : href ? `<a href="${escapeHtml(href)}" target="_blank" rel="noopener noreferrer">Source · page ${escapeHtml(latest.page_number)}</a>` : `<span>Source · page ${escapeHtml(latest.page_number ?? "not recorded")}</span>`;
    const definition = financialMetricDefinitions.get(latest.metric_name);
    const definitionDetails = definition?.definition
      ? `<details class="candidate-source"><summary>Metric definition</summary><p>${escapeHtml(definition.definition)}</p><small>${escapeHtml(definition.unit_guidance || "Use the reported source unit")}</small></details>`
      : "";
    return `<article class="financial-card"><span>${escapeHtml(latest.metric_label)}</span><strong>${formatFinancialValue(latest.metric_value)} <small>${escapeHtml(latest.unit)}</small></strong><em class="${isNegative ? "negative" : ""}">FY ${escapeHtml(latest.fiscal_year)} · ${comparison}</em>${definitionDetails}${provenance}${metricSourceChunkInspectButton(latest.document_id, latest.source_chunk_id, latest.source_chunk_index)}</article>`;
  }).join("") : '<p class="analysis-empty"><strong>No verified financial results for this selection</strong><span>Unreviewed extraction candidates are excluded. Admins can validate source evidence in Document processing.</span></p>';

  const comparisons = metrics.flatMap((series) => {
    if (series.length < 2) return [];
    const latest = series.at(-1);
    const previous = series.at(-2);
    if (previous.unit !== latest.unit) return [];
    const change = Number(latest.metric_value) - Number(previous.metric_value);
    const percent = Number(previous.metric_value) ? change / Math.abs(Number(previous.metric_value)) * 100 : null;
    const href = validSourceUrl(latest.source_url);
    const source = href ? `<a href="${escapeHtml(href)}" target="_blank" rel="noopener noreferrer">Source, page ${escapeHtml(latest.page_number)}</a>` : "Source link unavailable";
    return [`<article class="insight-row"><div class="insight-mark">${change >= 0 ? "+" : "-"}</div><div><strong>${escapeHtml(latest.metric_label)} ${change >= 0 ? "increased" : "decreased"} by ${formatFinancialValue(Math.abs(change))} ${escapeHtml(latest.unit)}${percent === null ? "" : ` (${formatFinancialValue(Math.abs(percent))}%)`}</strong><span>Reported change from FY ${escapeHtml(previous.fiscal_year)} to FY ${escapeHtml(latest.fiscal_year)} · ${source}</span></div></article>`];
  });
  if (comparisons.length) {
    $("#financial-insights").innerHTML = `<div class="insight-list">${comparisons.join("")}</div><p class="analysis-caveat">Reported VND, million VND and billion VND observations are normalized to billion VND for comparison; source quotes retain the originally reported units. Period-to-period changes describe the figures and do not establish why they changed.</p>`;
  } else {
    const pending = (data.candidates || []).length;
    const reportScope = reportYears.length ? `Annual reports in this selection: ${reportYears.join(", ")}. ` : "No annual report is available in this selection. ";
    const reviewScope = pending ? `${formatNumber(pending)} extracted evidence items await admin review; they are not treated as reported results.` : data.financial.length ? "A year-over-year comparison needs at least two verified periods for the same indicator." : "Ask an administrator to review extracted source evidence before interpreting financial results.";
    $("#financial-insights").innerHTML = `<div class="insight-empty"><span class="eyebrow">ANALYSIS STATUS</span><h4>No verified period comparison yet</h4><p>${escapeHtml(reportScope + reviewScope)}</p>${pending ? '<button type="button" class="inline-tab-link" data-open-tab="processing">Review source evidence</button>' : ""}</div>`;
  }
  $("#financial-trends").innerHTML = metrics.map((series) => {
    const max = Math.max(1, ...series.map((item) => Math.abs(Number(item.metric_value))));
    return `<article class="trend-card"><h4>${escapeHtml(series[0].metric_label)} · ${escapeHtml(series[0].unit)}</h4><div class="trend-bars">${series.map((item) => { const href = validSourceUrl(item.source_url); const source = href ? `<a href="${escapeHtml(href)}" target="_blank" rel="noopener noreferrer" aria-label="Open source page ${item.page_number}">Source</a>` : ""; const ratio = Math.abs(Number(item.metric_value)) / max; return `<div class="trend-point"><strong>${formatFinancialValue(item.metric_value)}</strong><i style="--bar-ratio:${ratio}" role="img" aria-label="FY ${escapeHtml(item.fiscal_year)} value ${formatFinancialValue(item.metric_value)} ${escapeHtml(item.unit)}"></i><span>FY ${escapeHtml(item.fiscal_year)}</span>${source}</div>`; }).join("")}</div></article>`;
  }).join("");
  const businessGroups = businessDisplayMetrics.reduce((groups, item) => {
    const key = metricSeriesKey(item);
    (groups[key] ??= []).push(item);
    return groups;
  }, {});
  const businessSeries = Object.values(businessGroups).map((series) =>
    series.sort((a, b) => Number(a.fiscal_year) - Number(b.fiscal_year)
      || (a.reporting_period === "H1" ? -1 : b.reporting_period === "H1" ? 1 : 0))
  );
  if (isMarketPerformance) renderMarketPerformanceDashboard(scopedBusinessMetrics);
  $("#business-metric-kpis").innerHTML = businessSeries.length
    ? businessSeries.map((series) => {
      const latest = series.at(-1);
      const previous = series.length > 1 ? series.at(-2) : null;
      const scope = escapeHtml(latest.scope);
      const source = uploadedSourcePageUrl(latest.source_document_id, latest.page_number)
        || sourcePageUrl(latest.source_url, latest.page_number);
      const comparable = previous && previous.unit === latest.unit
        && previous.scope === latest.scope
        && previous.value_qualifier === "exact" && latest.value_qualifier === "exact"
        && (previous.reporting_period || "FY") === (latest.reporting_period || "FY");
      const change = comparable
        ? latest.unit === "%"
          ? ` · ${formatFinancialValue(Number(latest.metric_value) - Number(previous.metric_value))} percentage points vs ${escapeHtml(formatBusinessMetricPeriod(previous))}`
          : ` · ${formatFinancialValue((Number(latest.metric_value) - Number(previous.metric_value)) / Math.abs(Number(previous.metric_value) || 1) * 100)}% vs ${escapeHtml(formatBusinessMetricPeriod(previous))}`
        : previous && previous.scope !== latest.scope
          ? " · reported scope differs; change not compared"
          : previous && (previous.value_qualifier !== "exact" || latest.value_qualifier !== "exact")
            ? " · value qualifier prevents a direct change comparison"
            : " · one verified reporting period";
      const parserProvenance = latest.extraction_method ? `${latest.extraction_method}${latest.extractor_version ? ` · ${latest.extractor_version}` : ""}${Number.isInteger(latest.source_chunk_index) ? ` · indexed chunk ${latest.source_chunk_index}` : ""}` : "Manual/source-research entry";
      const visualEvidence = latest.extraction_config?.visual_label
        ? `<p>Visual source label: ${escapeHtml(latest.extraction_config.visual_label)}${latest.extraction_config.source_scope ? ` · ${escapeHtml(latest.extraction_config.source_scope)}` : ""}</p>`
        : "";
      const definition = businessMetricDefinitions.get(latest.metric_name);
      const definitionDetails = definition?.definition
        ? `<details class="candidate-source"><summary>Metric definition</summary><p>${escapeHtml(definition.definition)}</p><small>Typical unit: ${escapeHtml(definition.unit_guidance || latest.unit)}</small></details>`
        : "";
      return `<article class="financial-card"><span>${escapeHtml(latest.domain.replaceAll("_", " "))} · ${escapeHtml(latest.metric_label)}</span><strong>${formatBusinessMetricValue(latest)} <small>${escapeHtml(latest.unit)}</small></strong><em>${escapeHtml(formatBusinessMetricPeriod(latest))}${change}</em><small>${scope}</small>${definitionDetails}${source ? `<a href="${escapeHtml(source)}" target="_blank" rel="noopener noreferrer">Source · page ${escapeHtml(latest.page_number)}</a>` : ""}<details class="candidate-source"><summary>Source excerpt</summary>${visualEvidence}<blockquote>${escapeHtml(latest.source_quote)}</blockquote><small>Verified by ${escapeHtml(latest.verified_by || "administrator")} · ${escapeHtml(parserProvenance)}</small></details>${metricSourceChunkInspectButton(latest.source_document_id, latest.source_chunk_id, latest.source_chunk_index)}</article>`;
    }).join("")
    : '<p class="analysis-empty"><strong>No verified business metrics for this selection yet</strong><span>Source-backed observations remain in the admin review queue and appear here only after verification.</span></p>';
  $("#business-metric-trends").innerHTML = businessSeries.filter((series) =>
    scopedBusinessMetrics.some((item) => item.metric_name === series[0].metric_name && item.company === series[0].company)
      && (metricScope === "all" || !businessMetricDefinitions.size
        || businessMetricDefinitions.get(series[0].metric_name)?.decision_priority === "primary")
  ).map((series) => {
    const max = Math.max(1, ...series.map((item) => Math.abs(Number(item.metric_value))));
    const scopeOrQualifierVaries = new Set(series.map((item) => item.scope)).size > 1
      || new Set(series.map((item) => item.value_qualifier)).size > 1;
    const periodLabel = series[0].reporting_period || "FY";
    const comparisonNote = scopeOrQualifierVaries
      ? '<p class="analysis-caveat">Reported scope or value qualifier varies across periods; inspect the source evidence before comparing.</p>' : "";
    return `<article class="trend-card"><h4>${escapeHtml(series[0].domain.replaceAll("_", " "))} · ${escapeHtml(series[0].metric_label)} · ${escapeHtml(series[0].unit)} · ${escapeHtml(periodLabel)}</h4>${comparisonNote}<div class="trend-bars">${series.map((item) => {
      const source = uploadedSourcePageUrl(item.source_document_id, item.page_number)
        || sourcePageUrl(item.source_url, item.page_number);
      const ratio = Math.abs(Number(item.metric_value)) / max;
      return `<div class="trend-point"><strong>${formatBusinessMetricValue(item)}</strong><i style="--bar-ratio:${ratio}" role="img" aria-label="${escapeHtml(formatBusinessMetricPeriod(item))} value ${formatBusinessMetricValue(item)} ${escapeHtml(item.unit)}"></i><span>${escapeHtml(formatBusinessMetricPeriod(item))}</span>${source ? `<a href="${escapeHtml(source)}" target="_blank" rel="noopener noreferrer">Source p. ${escapeHtml(item.page_number)}</a>` : ""}</div>`;
    }).join("")}</div></article>`;
  }).join("");
  const segmentDefinitions = {
    domestic: {label: "Domestic", revenue: "domestic_consolidated_net_revenue", profit: "domestic_segment_gross_profit"},
    overseas: {label: "Overseas", revenue: "overseas_market_net_revenue", profit: "overseas_segment_gross_profit"},
  };
  const segmentYearRows = new Map();
  for (const metric of data.business_metrics || []) {
    const segment = Object.entries(segmentDefinitions).find(([, definition]) =>
      metric.metric_name === definition.revenue || metric.metric_name === definition.profit
    );
    if (!segment) continue;
    const key = `${metric.company}:${metric.fiscal_year}:${segment[0]}`;
    const row = segmentYearRows.get(key) || {company: metric.company, fiscal_year: metric.fiscal_year, segment: segment[0]};
    row[metric.metric_name === segment[1].revenue ? "revenue" : "profit"] = metric;
    segmentYearRows.set(key, row);
  }
  const marginSeries = new Map();
  for (const row of segmentYearRows.values()) {
    if (!row.revenue || !row.profit) continue;
    const revenue = Number(row.revenue.metric_value);
    const grossProfit = Number(row.profit.metric_value);
    if (!Number.isFinite(revenue) || revenue <= 0 || !Number.isFinite(grossProfit)) continue;
    const key = `${row.company}:${row.segment}`;
    const series = marginSeries.get(key) || [];
    series.push({...row, margin: grossProfit / revenue * 100});
    marginSeries.set(key, series);
  }
  const marginFormat = (value) => new Intl.NumberFormat("vi-VN", {
    minimumFractionDigits: 2, maximumFractionDigits: 2,
  }).format(value);
  const marginCards = [...marginSeries.values()].flatMap((series) => {
    series.sort((a, b) => Number(a.fiscal_year) - Number(b.fiscal_year));
    return series.map((row, index) => {
      const previous = series[index - 1];
      const change = previous
        ? ` · ${marginFormat(row.margin - previous.margin)} percentage points vs FY ${escapeHtml(previous.fiscal_year)}`
        : "";
      const revenueSource = sourcePageUrl(row.revenue.source_url, row.revenue.page_number);
      const profitSource = sourcePageUrl(row.profit.source_url, row.profit.page_number);
      return `<article class="financial-card"><span>${escapeHtml(segmentDefinitions[row.segment].label)} segment · ${escapeHtml(row.company)}</span><strong>${marginFormat(row.margin)}<small>% gross margin</small></strong><em>FY ${escapeHtml(row.fiscal_year)}${change}</em><small>Derived from verified segment gross profit and net revenue; excludes selling and administration costs.</small>${revenueSource ? `<a href="${escapeHtml(revenueSource)}" target="_blank" rel="noopener noreferrer">Net revenue source · p. ${escapeHtml(row.revenue.page_number)}</a>` : ""}${profitSource ? `<a href="${escapeHtml(profitSource)}" target="_blank" rel="noopener noreferrer">Gross profit source · p. ${escapeHtml(row.profit.page_number)}</a>` : ""}<details class="candidate-source"><summary>Calculation inputs</summary><blockquote>Net revenue: ${escapeHtml(formatFinancialValue(row.revenue.metric_value))} ${escapeHtml(row.revenue.unit)} — ${escapeHtml(row.revenue.source_quote)}<br>Segment gross profit: ${escapeHtml(formatFinancialValue(row.profit.metric_value))} ${escapeHtml(row.profit.unit)} — ${escapeHtml(row.profit.source_quote)}</blockquote></details></article>`;
    });
  });
  $("#segment-gross-margin-kpis").innerHTML = marginCards.length
    ? marginCards.join("")
    : '<p class="analysis-empty"><strong>No verified segment revenue and gross-profit pair for this selection</strong><span>Both observations must be verified for the same segment, company and year before gross margin is calculated.</span></p>';
  const maxDocs = Math.max(1, ...(data.domains || []).map((item) => item.documents));
  $("#domain-chart").innerHTML = (data.domains || []).map((item) => `
    <div class="bar-row"><div><span>${escapeHtml(item.company)} · ${escapeHtml(item.domain.replaceAll("_", " "))} · FY ${escapeHtml(item.fiscal_year || "No year")}</span><strong>${formatNumber(item.documents)} docs · ${formatNumber(item.chunks)} passages</strong></div><span class="bar-track"><i style="width:${Math.max(5, item.documents / maxDocs * 100)}%"></i></span></div>
  `).join("");
  const statusCounts = (data.processing || []).map((item) => `<div class="bar-row"><div><span>${escapeHtml(item.company)} · ${escapeHtml(item.fiscal_year ? `FY ${item.fiscal_year}` : "General")}</span><strong>${formatNumber(item.documents)} · ${escapeHtml(item.processing_status || "unknown")}</strong></div><span class="bar-track"><i style="width:${Math.max(5, item.documents / Math.max(1, ...data.processing.map((row) => row.documents)) * 100)}%"></i></span></div>`);
  $("#processing-chart").innerHTML = statusCounts.join("") || '<p class="loading-card">No processing records yet.</p>';
  $("#quality-chart").innerHTML = (data.quality || []).map((item) => `
    <div class="quality-row"><div><strong>${escapeHtml(item.document_id)}</strong><span>${formatNumber(item.chunks)} passages · avg ${formatNumber(item.avg_chunk_chars)} chars</span></div><span class="quality-pill ${item.empty_chunks ? "warning" : "ok"}">${item.empty_chunks ? `${item.empty_chunks} empty` : "No empty passages"}</span></div>
  `).join("");
  renderCandidates(data);
}

function renderCandidates(data) {
  const inScopeBusinessCandidates = (data.business_candidates || []).filter((item) =>
    ["milk_supply", "market_performance"].includes(
      item.domain || businessMetricDefinitions.get(item.metric_name)?.domain
    )
  );
  const candidates = [
    ...(data.candidates || []),
    ...inScopeBusinessCandidates.map((item) => ({
      ...item, document_id: item.source_document_id,
      candidate_kind: "business", title: item.source_document_id,
      source_note: item.scope, candidate_values: [item.normalized_value],
    })),
  ];
  pendingMetricCandidates = candidates;
  const domainFilter = $("#candidate-domain-filter");
  const previousDomain = domainFilter.value || "all";
  const candidateDomain = (item) => item.domain
    || businessMetricDefinitions.get(item.metric_name)?.domain
    || "finance_and_operations";
  const domains = [...new Set(candidates.map(candidateDomain))].sort();
  const labelForDomain = (domain) => businessMetricDefinitions.get(
    candidates.find((item) => candidateDomain(item) === domain)?.metric_name
  )?.decision_profile_label || domain.replaceAll("_", " ");
  domainFilter.innerHTML = `<option value="all">All domains</option>${domains.map((domain) =>
    `<option value="${escapeHtml(domain)}">${escapeHtml(labelForDomain(domain))}</option>`
  ).join("")}`;
  domainFilter.value = domains.includes(previousDomain) ? previousDomain : "all";
  const visibleCandidates = domainFilter.value === "all" ? candidates
    : candidates.filter((item) => candidateDomain(item) === domainFilter.value);
  $("#candidate-review").hidden = !candidates.length;
  $("#candidate-list").innerHTML = visibleCandidates.map((item) => {
    const href = sourcePageUrl(item.source_url, item.page_number);
    const uploadedSourceHref = uploadedSourcePageUrl(item.document_id, item.page_number);
    const sourceHref = uploadedSourceHref || href;
    const sourceLabel = uploadedSourceHref ? "Open uploaded source" : "Open official original";
    const figures = Array.isArray(item.candidate_values)
      ? item.candidate_values.map(String).filter(Boolean)
      : [];
    const businessKind = item.candidate_kind === "business";
  const isManual = item.entry_method === "manual";
    const extraction = businessKind ? item.extraction_method === "parser_rule"
      ? `Parser rule · ${item.extractor_version || "version unknown"}`
      : "Source report · research candidate" : isManual ? "Manual entry · user supplied" : item.extraction_method === "llm_selected_financial_page"
      ? `LLM · ${item.extractor_model || "configured model"}`
      : item.text_extraction_method || "Rule-based evidence";
    const signals = item.selection_evidence || {};
    const selectionSummary = [
      ...(signals.financial_terms || []),
      ...(signals.metric_labels || []),
      signals.table_count ? `${signals.table_count} parsed tables` : "",
    ].filter(Boolean).join(" · ");
    const labelMatchNotice = signals.source_label_match === "ocr_near_match"
      ? "<small>OCR label is approximate; verify the printed metric label, value, and year in the source.</small>"
      : "";
    const evidenceCount = Math.max(1, Number(item.evidence_count) || 1);
    const extractionLabel = extraction.includes("tesseract") ? "OCR assisted" : extraction;
    const figuresMarkup = renderCandidateFigures(figures);
    const periodLabel = businessKind
      ? formatBusinessMetricPeriod({fiscal_year: item.fiscal_year, reporting_period: item.reporting_period})
      : item.fiscal_year || "Needs review";
    const qualifierLabel = businessKind && item.value_qualifier && item.value_qualifier !== "exact"
      ? ` · Report qualifier: ${item.value_qualifier.replaceAll("_", " ")}` : "";
    const visualEvidence = businessKind && item.extraction_config?.visual_label
      ? `<p>Visual source label: ${escapeHtml(item.extraction_config.visual_label)}${item.extraction_config.source_scope ? ` · ${escapeHtml(item.extraction_config.source_scope)}` : ""}</p>`
      : "";
    return `<article class="candidate-row">
      <div class="candidate-evidence">
        <div class="candidate-heading"><div><strong>${escapeHtml(item.metric_label)}</strong><span>${escapeHtml(item.company)} · ${escapeHtml(item.title)}</span></div><span class="candidate-status">Admin review${evidenceCount > 1 ? ` · ${formatNumber(evidenceCount)} excerpts` : ""}</span></div>
        <div class="candidate-facts"><span><small>Reporting period</small><strong>${escapeHtml(periodLabel)}</strong></span><span><small>Source page</small><strong>${escapeHtml(item.page_number ?? (isManual ? "Manual reference" : "—"))}</strong></span><span><small>Document</small><strong>${escapeHtml(item.document_id || (isManual ? "Manual entry" : "—"))}</strong></span><span><small>Entry method</small><strong>${escapeHtml(extractionLabel)}</strong></span></div>
        <div class="candidate-value"><small>${businessKind ? `Report value proposed · verify unit, scope, and report wording${qualifierLabel}` : isManual ? "User-supplied value · confirm its provenance and reporting basis" : figures.length > 1 ? "Figures in excerpt · select a value, then confirm its reporting year in the source" : "Figure found in excerpt · select it only after checking the source"}</small><div class="candidate-figures">${figuresMarkup}</div><small>Confirm the reporting year and scale. Use one consistent dashboard unit across periods.${evidenceCount > 1 ? " Rejecting this excerpt will show the next pending source excerpt." : ""}</small></div>
        <details class="candidate-source"><summary>${isManual ? "Review manual source context" : `Check source excerpt${sourceHref ? ` · <a href="${escapeHtml(sourceHref)}" target="_blank" rel="noopener noreferrer">${sourceLabel} · page ${escapeHtml(item.page_number)}</a>` : ""}`}</summary>${isManual ? `${item.source_reference ? `<p>Source reference: ${escapeHtml(item.source_reference)}</p>` : "<p>No external source URL supplied.</p>"}<p>${escapeHtml(item.source_note)}</p>` : `${businessKind ? `<p>Scope: ${escapeHtml(item.scope)}</p><p>Extraction provenance: ${escapeHtml(item.extraction_method || "source research")}${item.extractor_version ? ` · ${escapeHtml(item.extractor_version)}` : ""}${item.source_chunk_index !== null && item.source_chunk_index !== undefined ? ` · source chunk ${escapeHtml(item.source_chunk_index)}` : ""}</p>${visualEvidence}` : `${labelMatchNotice}${item.source_chunk_index !== null && item.source_chunk_index !== undefined ? `<p>Indexed source chunk ${escapeHtml(item.source_chunk_index)}</p>` : ""}`}<blockquote>${escapeHtml(item.source_quote)}</blockquote>${selectionSummary ? `<small>Page-selection signals · ${escapeHtml(selectionSummary)}</small>` : ""}${item.prompt_version ? `<small>Extraction prompt · ${escapeHtml(item.prompt_version)}</small>` : ""}`}</details>
      </div>
      <form data-candidate-id="${item.id}" data-candidate-kind="${businessKind ? "business" : "financial"}" class="review-form">
        <label>Verified value<input name="normalized_value" type="text" inputmode="decimal" pattern="[+-]?[0-9.,]+" value="${isManual || businessKind ? escapeHtml(figures[0] || "") : ""}" required placeholder="e.g. 59723 or 59.723" aria-describedby="metric-value-help"></label><small id="metric-value-help">Nhập chữ số liền nhau (59723) hoặc theo cách viết Việt Nam (59.723; phần thập phân: 59.723,5). Dashboard cũng hiển thị theo cách viết Việt Nam: 59.723.</small><output class="review-value-preview" aria-live="polite"></output>
        <label>Dashboard unit (verify)<input name="unit" value="${escapeHtml(item.unit || "")}" required placeholder="e.g. billion VND"></label>
        <div class="review-actions"><button type="submit">Verify and publish</button><button type="button" data-reject>Reject</button></div>
      </form>
    </article>`;
  }).join("");
}

$("#candidate-domain-filter").addEventListener("change", () => {
  renderCandidates({candidates: pendingMetricCandidates.filter((item) => item.candidate_kind !== "business"),
    business_candidates: pendingMetricCandidates.filter((item) => item.candidate_kind === "business")});
});

function renderDashboardVisualization(visualization) {
  if (visualization?.type !== "line" || !Array.isArray(visualization.categories) || visualization.categories.length < 2) return "";
  const categories = visualization.categories;
  const series = (visualization.series || []).filter((item) =>
    typeof item.name === "string" && Array.isArray(item.values) && item.values.length === categories.length
      && item.values.filter(Number.isFinite).length >= 2
  );
  if (!series.length) return "";
  const width = 680;
  const height = 270;
  const left = 70;
  const right = 22;
  const top = 24;
  const bottom = 42;
  const plotWidth = width - left - right;
  const plotHeight = height - top - bottom;
  const colors = ["#2463b5", "#da8a2d", "#24866b", "#8758a8"];
  const charts = series.map((item, seriesIndex) => {
    const values = item.values.map((value) => Number.isFinite(value) ? value : null);
    const max = Math.max(...values.filter((value) => value !== null), 0) || 1;
    const x = (index) => left + (categories.length === 1 ? plotWidth / 2 : index * plotWidth / (categories.length - 1));
    const y = (value) => top + plotHeight - value / (max * 1.1) * plotHeight;
    const segments = [];
    let segment = [];
    values.forEach((value, index) => {
      if (value === null) {
        if (segment.length > 1) segments.push(segment);
        segment = [];
      } else segment.push(`${segment.length ? "L" : "M"}${x(index).toFixed(1)},${y(value).toFixed(1)}`);
    });
    if (segment.length > 1) segments.push(segment);
    const grid = [0, 0.5, 1].map((fraction) => {
      const yPos = top + plotHeight - fraction * plotHeight;
      return `<g><line x1="${left}" y1="${yPos}" x2="${width - right}" y2="${yPos}" class="chart-gridline"/><text x="${left - 9}" y="${yPos + 4}" text-anchor="end" class="chart-axis-label">${escapeHtml(formatNumber(max * fraction))}</text></g>`;
    }).join("");
    const points = values.map((value, index) => value === null ? "" :
      `<circle cx="${x(index)}" cy="${y(value)}" r="4" fill="${colors[seriesIndex % colors.length]}"><title>FY ${escapeHtml(categories[index])}: ${escapeHtml(formatFinancialValue(value))} ${escapeHtml(visualization.unit)}</title></circle>`
    ).join("");
    const xLabels = categories.map((category, index) =>
      `<text x="${x(index)}" y="${height - 13}" text-anchor="middle" class="chart-axis-label">${escapeHtml(category)}</text>`
    ).join("");
    return `<article class="answer-chart"><h4>${escapeHtml(item.name)} · ${escapeHtml(visualization.unit)}</h4><svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(item.name)} by fiscal year">${grid}<line x1="${left}" y1="${top}" x2="${left}" y2="${top + plotHeight}" class="chart-axis"/>${segments.map((path) => `<path d="${path.join(" ")}" fill="none" stroke="${colors[seriesIndex % colors.length]}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>`).join("")}${points}${xLabels}</svg></article>`;
  }).join("");
  return `<section class="answer-visualization"><h3>${escapeHtml(visualization.title || "Verified financial trend")}</h3>${charts}<p class="chart-note">Values come from verified, role-visible source metrics. Exact amounts and citations are listed in the response above.</p></section>`;
}

function renderAnswerBody(answer) {
  const lines = String(answer || "").split(/\r?\n/);
  const blocks = [];
  let paragraph = [];
  const inline = (value) => escapeHtml(value)
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/`([^`]+)`/g, "<code>$1</code>");
  const cells = (line) => line.trim().replace(/^\|/, "").replace(/\|$/, "")
    .split(/(?<!\\)\|/).map((cell) => cell.trim().replace(/\\\|/g, "|"));
  const isRow = (line) => /^\s*\|.*\|\s*$/.test(line);
  const isDivider = (line) => isRow(line)
    && cells(line).every((cell) => /^:?-{3,}:?$/.test(cell));
  const flushParagraph = () => {
    if (paragraph.length) blocks.push(`<p>${paragraph.map(inline).join("<br>")}</p>`);
    paragraph = [];
  };

  for (let index = 0; index < lines.length;) {
    if (isRow(lines[index]) && isDivider(lines[index + 1] || "")) {
      flushParagraph();
      const headings = cells(lines[index]);
      index += 2;
      const rows = [];
      while (index < lines.length && isRow(lines[index])) rows.push(cells(lines[index++]));
      const header = headings.map((cell) => `<th scope="col">${inline(cell)}</th>`).join("");
      const body = rows.map((row) => `<tr>${headings.map((_, column) =>
        `<td>${inline(row[column] || "")}</td>`).join("")}</tr>`).join("");
      blocks.push(`<div class="commerce-table-wrap answer-markdown-table"><table aria-label="Answer details"><thead><tr>${header}</tr></thead><tbody>${body}</tbody></table></div>`);
      continue;
    }
    if (!lines[index].trim()) flushParagraph();
    else paragraph.push(lines[index]);
    index += 1;
  }
  flushParagraph();
  return blocks.join("");
}

function renderAnswer(data, panel = $("#answer-panel")) {
  panel.hidden = false;
  const citations = Array.isArray(data.citations) ? data.citations : [];
  const decisionModeNote = data.generation_provider === "deterministic_safety_fallback"
    ? '<p class="analysis-caveat answer-provenance-note" role="note"><strong>Audit-first safety fallback.</strong> The model draft did not pass grounding checks. This response uses verified KPIs to define the next evidence-gathering steps and does not select a specific intervention.</p>'
    : "";
  const referenceRetrievalNote = data.decision_reference_retrieval_limited
    ? '<p class="analysis-caveat answer-provenance-note" role="note"><strong>Document retrieval was temporarily rate-limited.</strong> This recommendation uses SQL and schema evidence only; no operating document could be checked for this answer.</p>'
    : "";
  const questionSqlFallbackNotes = {
    provider_rate_limited: "The model provider was rate-limited while generating question-specific SQL.",
    provider_unavailable: "The model provider was unavailable while generating question-specific SQL.",
    query_rejected: "Generated SQL did not pass the safety checks.",
    no_question_rows: "The question-specific query returned no rows.",
    requested_dimension_unavailable: "The requested reporting dimension is not in this domain's approved schema.",
  };
  const questionSqlFallbackNote = questionSqlFallbackNotes[data.question_sql_fallback]
    ? `<p class="analysis-caveat answer-provenance-note" role="note"><strong>Using bounded Commerce aggregates.</strong> ${questionSqlFallbackNotes[data.question_sql_fallback]} This answer may not reflect the exact filters or grouping in your question.</p>`
    : "";
  panel.innerHTML = `
    <div class="answer-header-wrap">
      <div class="answer-heading">
        <span class="answer-mark">AI</span>
        <div><span class="eyebrow">GROUNDED RESPONSE</span><h3>Synthesized Answer</h3></div>
      </div>
      <div class="answer-actions-bar">
        <button type="button" class="action-btn" id="copy-answer-btn" title="Copy response text">Copy</button>
      </div>
    </div>
    ${decisionModeNote}
    ${referenceRetrievalNote}
    ${questionSqlFallbackNote}
    <div class="answer-text">${renderAnswerBody(data.answer)}</div>
    ${renderDashboardVisualization(data.data?.visualization)}
    ${data.citation_validation_failed ? '<p class="error-message">Relevant passages were found, but citation verification did not meet the strict confidence threshold.</p>' : citations.length ? `
      <div class="citations">
        <div class="citation-header-row">
          <h4>Cited Sources (${citations.length})</h4>
          <span class="citation-count-badge">${citations.length} source${citations.length === 1 ? "" : "s"}</span>
        </div>
        ${citations.map((source) => {
          const href = uploadedSourcePageUrl(source.document_id, source.page_number)
            || validSourceUrl(source.source_url);
          const link = href ? `<a href="${escapeHtml(href)}" target="_blank" rel="noopener noreferrer">View original</a>` : "";
          const chunk = Number.isInteger(source.chunk_index) ? ` · Indexed chunk ${source.chunk_index}` : "";
          const location = source.page_number ? `Page ${source.page_number}${chunk}`
            : source.source_type === "commerce_sql" ? `SQL aggregate · ${(source.source_tables || []).join(", ")}`
              : source.source_type === "commerce_schema" ? `Schema coverage · ${(source.source_tables || []).join(", ")}`
              : Number.isInteger(source.chunk_index) ? `Passage ${source.chunk_index + 1}` : "Reference";
          const relevanceScore = Number.isFinite(source.score) ? source.score * 100 : null;
          const scoreClass = relevanceScore && relevanceScore >= 80 ? "high" : relevanceScore && relevanceScore >= 60 ? "med" : "low";
          const relevanceBadge = relevanceScore !== null
            ? `<span class="citation-relevance-meter ${scoreClass}">Relevance: ${relevanceScore.toFixed(1)}%</span>`
            : "";
          const referenceScope = source.reference_applicability
            ? `<p class="citation-scope"><strong>Source scope:</strong> ${escapeHtml(source.reference_applicability)}</p>`
            : "";
          const sqlTrace = source.sql_query
            ? `<details class="citation-sql-trace"><summary>Inspect generated SQL</summary><pre>${escapeHtml(source.sql_query)}</pre></details>`
            : "";
          const observationTrace = source.source_type === "commerce_sql"
            ? renderCommerceEvidence(source.commerce_observations, source.commerce_observation_group)
            : "";
          const sourceExcerpt = source.source_type === "commerce_sql"
            && Array.isArray(source.commerce_observations) && source.commerce_observations.length
            ? ""
            : `<p>${escapeHtml(source.excerpt)}</p>`;
          const publisher = source.source_publisher || source.company || "Verified source";
          return `
            <article class="citation">
              <div class="citation-title">
                <span class="citation-id">[${escapeHtml(source.id)}]</span>
                <strong>${escapeHtml(source.title)}</strong>
                <span>${escapeHtml(location)}</span>
              </div>
              ${referenceScope}
              ${sourceExcerpt}
              ${observationTrace}
              ${sqlTrace}
              <div class="citation-foot">
                <span>${escapeHtml(publisher)}${source.evidence_class ? ` · ${escapeHtml(source.evidence_class.replaceAll("_", " "))}` : ""}</span>
                ${relevanceBadge}
                ${link}
              </div>
            </article>`;
        }).join("")}
      </div>` : `<p class="no-citations">No matching documents found within your authorized scope.</p>`}`;

  const copyBtn = panel.querySelector("#copy-answer-btn");
  if (copyBtn) {
    copyBtn.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(data.answer);
        copyBtn.textContent = "Copied!";
        copyBtn.classList.add("copied");
        setTimeout(() => {
          copyBtn.textContent = "Copy";
          copyBtn.classList.remove("copied");
        }, 2000);
      } catch {
        alert("Unable to copy automatically. Please select the text and press Ctrl+C.");
      }
    });
  }

  panel.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function renderAgentMonitoring(data) {
  const summary = data.summary || {};
  const cards = [
    ["Runs · 24 hours", summary.total_runs ?? 0],
    ["Success rate", summary.success_rate == null ? "—" : `${summary.success_rate}%`],
    ["Average latency", summary.average_elapsed_ms == null ? "—" : `${formatNumber(summary.average_elapsed_ms)} ms`],
    ["P95 latency", summary.p95_elapsed_ms == null ? "—" : `${formatNumber(summary.p95_elapsed_ms)} ms`],
    ["Runs · last hour", summary.last_hour_runs ?? 0],
  ];
  $("#monitoring-summary").innerHTML = cards.map(([label, value]) => `<article class="monitoring-stat"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></article>`).join("");
  const agents = data.by_agent || [];
  const maxRuns = Math.max(1, ...agents.map((agent) => Number(agent.total_runs) || 0));
  $("#monitoring-agents").innerHTML = agents.length ? agents.map((agent) => `
    <div class="monitoring-agent"><div><strong>${escapeHtml(agent.agent_name)}</strong><span>${formatNumber(agent.completed_runs)} of ${formatNumber(agent.total_runs)} completed · avg ${agent.average_elapsed_ms == null ? "—" : `${formatNumber(agent.average_elapsed_ms)} ms`}</span></div><i><b style="width:${Math.max(3, Number(agent.total_runs) / maxRuns * 100)}%"></b></i></div>
  `).join("") : '<p class="analysis-empty">No agent runs have been recorded in the last 24 hours.</p>';
  const runs = data.recent_runs || [];
  $("#monitoring-runs").innerHTML = runs.length ? `<div class="monitoring-table-wrap"><table class="monitoring-table"><thead><tr><th>Time</th><th>Role</th><th>Agent</th><th>Retrieval</th><th>Result</th><th>Latency</th><th>Sources</th></tr></thead><tbody>${runs.map((run) => `<tr><td>${escapeHtml(new Date(run.created_at).toLocaleString())}</td><td>${escapeHtml(run.actor_role)}</td><td>${escapeHtml(run.agent_name)}</td><td>${escapeHtml(run.retrieval_method)}</td><td><span class="run-status ${escapeHtml(run.status)}">${escapeHtml(run.status.replaceAll("_", " "))}</span>${run.error_type ? `<small>${escapeHtml(run.error_type)}</small>` : ""}</td><td>${formatNumber(run.elapsed_ms)} ms</td><td>${formatNumber(run.citation_count)}</td></tr>`).join("")}</tbody></table></div>` : '<p class="analysis-empty">No requests recorded yet.</p>';
}

async function refreshAgentMonitoring() {
  const button = $("#monitoring-refresh");
  button.disabled = true;
  try {
    renderAgentMonitoring(await api("/api/admin/agent-monitoring"));
  } catch (error) {
    $("#monitoring-runs").innerHTML = `<p class="error-message">${escapeHtml(error.message)}</p>`;
  } finally {
    button.disabled = false;
  }
}

function askOverWebSocket(payload, onStatus) {
  return new Promise((resolve, reject) => {
    if (!window.WebSocket) {
      reject(Object.assign(new Error("WebSocket is unavailable"), { safeToFallback: true }));
      return;
    }
    const scheme = location.protocol === "https:" ? "wss:" : "ws:";
    const socket = new WebSocket(`${scheme}//${location.host}/ws/ask`);
    let sent = false;
    let settled = false;
    const timeout = setTimeout(() => {
      if (settled) return;
      settled = true;
      socket.close();
      reject(new Error("The answer request timed out"));
    }, 120000);
    const finish = (callback, value) => {
      if (settled) return;
      settled = true;
      clearTimeout(timeout);
      callback(value);
    };
    socket.onopen = () => {
      sent = true;
      socket.send(JSON.stringify(payload));
    };
    socket.onmessage = (event) => {
      let message;
      try { message = JSON.parse(event.data); }
      catch { finish(reject, new Error("The server returned an invalid WebSocket response")); return; }
      if (message.type === "status") onStatus(message.status);
      else if (message.type === "answer") finish(resolve, message);
      else if (message.type === "error") {
        const detail = Array.isArray(message.detail)
          ? message.detail.map((item) => item.msg).join("; ")
          : message.detail;
        finish(reject, new Error(detail || "Question answering failed"));
      }
    };
    socket.onerror = () => finish(reject, Object.assign(new Error("WebSocket connection failed"), { safeToFallback: !sent }));
    socket.onclose = () => {
      if (!settled) finish(reject, Object.assign(new Error("WebSocket closed before answering"), { safeToFallback: !sent }));
    };
  });
}

async function api(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (!(options.body instanceof FormData)) headers["Content-Type"] = "application/json";
  const response = await fetch(path, { credentials: "same-origin", ...options, headers });
  if (response.status === 401) {
    $("#login-view").hidden = false;
    $("#workspace").hidden = true;
    throw new Error("Sign in to continue");
  }
  const data = await response.json();
  if (!response.ok) throw Object.assign(new Error(data.detail || "Request failed"), { status: response.status });
  return data;
}

async function loadCommerceDashboardForActiveView() {
  const view = document.querySelector('[data-commerce-view][aria-selected="true"]')?.dataset.commerceView || "inventory";
  const domainByView = {
    inventory: "inventory_allocation",
    promotions: "promotion_planning",
    logistics: "nationwide_logistics",
  };
  const domain = domainByView[view];
  if (!domain || commerceLoadedDomains.has(domain) || commerceLoadingDomains.has(domain)) return;
  commerceLoadingDomains.add(domain);
  const status = $("#commerce-dashboard-status");
  status.textContent = `Loading ${view} data…`;
  status.hidden = false;
  const isCurrentView = () => activeTab === "analytics"
    && domainByView[document.querySelector('[data-commerce-view][aria-selected="true"]')?.dataset.commerceView || "inventory"] === domain;
  try {
    const data = await api(`/api/commerce/dashboard?domain=${encodeURIComponent(domain)}`);
    commerceSnapshot = { ...(commerceSnapshot || {}), ...data };
    commerceLoadedDomains.add(domain);
    renderCommerceDashboard(commerceSnapshot);
    if (isCurrentView()) status.hidden = true;
    if (domain === "promotion_planning" && $("#commerce-campaign-details").open) loadCommerceCampaigns();
  } catch (error) {
    if (isCurrentView()) {
      status.textContent = `Could not load ${view} data: ${error.message}`;
      status.hidden = false;
    }
  } finally {
    commerceLoadingDomains.delete(domain);
  }
}

async function loadCommerceCampaigns() {
  if (!commerceLoadedDomains.has("promotion_planning") || commerceCampaignsLoaded || commerceCampaignsLoading) return;
  commerceCampaignsLoading = true;
  const status = $("#commerce-dashboard-status");
  status.textContent = "Loading campaign results…";
  status.hidden = false;
  try {
    const data = await api("/api/commerce/dashboard?domain=promotion_planning&detail=campaigns");
    commerceSnapshot = { ...(commerceSnapshot || {}), ...data };
    commerceCampaignsLoaded = true;
    renderCommerceDashboard(commerceSnapshot);
    if (activeTab === "analytics" && document.querySelector('[data-commerce-view="promotions"]')?.getAttribute("aria-selected") === "true") {
      status.hidden = true;
    }
  } catch (error) {
    if (activeTab === "analytics" && document.querySelector('[data-commerce-view="promotions"]')?.getAttribute("aria-selected") === "true") {
      status.textContent = `Could not load campaign results: ${error.message}`;
      status.hidden = false;
    }
  } finally {
    commerceCampaignsLoading = false;
  }
}

async function loadWorkspace(user) {
  currentUser = user;
  $("#login-view").hidden = true;
  $("#workspace").hidden = false;
  $("#analytics-section").hidden = true;
  $("#upload-section").hidden = true;
  $("#admin-section").hidden = true;
  $("#monitoring-section").hidden = true;
  $("#metric-management-section").hidden = user.role !== "admin";
  $("#business-metric-management-section").hidden = user.role !== "admin";
  $("#candidate-review").hidden = true;
  syncWorkspaceTabs();
  $("#access-matrix").replaceChildren();
  $("#connection-status").textContent = "Knowledge base connected";
  $("#user-badge").textContent = `${user.username} · ${user.role}`;
  $("#user-badge").hidden = false;
  $("#logout-button").hidden = false;
  $(".intro").hidden = user.role === "tester";
  $(".stats").hidden = user.role === "tester";
  if (user.role === "tester") {
    try {
      await loadOcrTestRuns();
      $("#login-error").hidden = true;
    } catch (error) {
      $("#ocr-test-runs").innerHTML = `<p class="loading-card">${escapeHtml(error.message)}</p>`;
    }
    return;
  }
  try {
    const data = await api("/api/dashboard");
    renderCorpus(data);
    if (user.role === "admin") renderParsedChunkInspector(data);
    if (user.role === "admin") {
      $("#metric-management-section").hidden = false;
      const roles = await api("/api/documents/roles");
      $("#manual-metric-role-options").innerHTML = roles.roles.map((role) =>
        `<label><input type="checkbox" name="allowed_roles" value="${escapeHtml(role)}" ${["admin", "executive", "finance_analyst"].includes(role) ? "checked" : ""}> ${escapeHtml(role.replaceAll("_", " "))}</label>`
      ).join("");
      renderMetricCatalog(await api("/api/metrics/catalog"));
      renderBusinessMetricCatalog(await api("/api/business-metrics/catalog"));
      $("#business-metric-role-options").innerHTML = roles.roles.map((role) =>
        `<label><input type="checkbox" name="allowed_roles" value="${escapeHtml(role)}" ${["admin", "executive", "sustainability_analyst"].includes(role) ? "checked" : ""}> ${escapeHtml(role.replaceAll("_", " "))}</label>`
      ).join("");
      $("#business-metric-management-section").hidden = false;
    }
    try {
      const capability = await api("/api/documents/upload-capability");
      $("#upload-section").hidden = !capability.can_upload;
      if (capability.can_upload) {
        $("#upload-synthetic-policy-option").hidden = user.role !== "admin";
        const { roles } = await api("/api/documents/roles");
        $("#upload-role-options").innerHTML = roles.map((role) => `<label><input type="checkbox" name="allowed_roles" value="${escapeHtml(role)}"> ${escapeHtml(role.replaceAll("_", " "))}</label>`).join("");
      }
    } catch {
      $("#upload-section").hidden = true;
    }
    if (["operations", "finance_analyst", "sustainability_analyst", "executive", "admin"].includes(user.role)) {
      $("#commerce-dashboard").hidden = false;
      $(".analytics-subtabs").hidden = true;
      document.querySelectorAll(".analytics-subpanel").forEach((panel) => { panel.hidden = true; });
      renderDecisionDomainQuestions($("#commerce-decision-domain").value);
      $("#analytics-section").hidden = false;
    }
    if (user.role === "admin") {
      const access = await api("/api/admin/access-matrix");
      $("#access-matrix").innerHTML = access.roles.map((role) => `<article><strong>${escapeHtml(role.role)}</strong><span>${role.permissions.map(escapeHtml).join(" · ")}</span></article>`).join("");
      $("#admin-section").hidden = false;
      $("#monitoring-section").hidden = false;
      await refreshAgentMonitoring();
      await refreshKnowledgeDocuments();
    }
    if (user.role === "admin") await loadOcrTestRuns();
    syncWorkspaceTabs(user);
    $("#login-error").hidden = true;
  } catch (error) {
    syncWorkspaceTabs(user);
    if (error.message !== "Sign in to continue") {
      $("#login-error").textContent = `Signed in, but the workspace could not load: ${error.message}`;
      $("#login-error").hidden = false;
      $("#connection-status").textContent = "Signed in · data unavailable";
    }
  }
}

$("#workspace-tabs").addEventListener("click", (event) => {
  const button = event.target.closest("[data-tab-target]");
  if (button) selectWorkspaceTab(button.dataset.tabTarget);
});

$("#workspace-tabs").addEventListener("keydown", (event) => {
  const tabs = [...document.querySelectorAll(".workspace-tab:not([hidden])")];
  const current = tabs.indexOf(event.target);
  if (current < 0) return;
  const next = { ArrowRight: (current + 1) % tabs.length, ArrowLeft: (current - 1 + tabs.length) % tabs.length, Home: 0, End: tabs.length - 1 }[event.key];
  if (next === undefined) return;
  event.preventDefault();
  tabs[next].focus();
  selectWorkspaceTab(tabs[next].dataset.tabTarget);
});

$("#knowledge-documents-search").addEventListener("input", renderKnowledgeDocuments);
$("#knowledge-documents-refresh").addEventListener("click", async () => {
  try { await refreshKnowledgeDocuments(); }
  catch (error) { $("#knowledge-documents-status").textContent = error.message; }
});
$("#knowledge-documents-list").addEventListener("click", async (event) => {
  const button = event.target.closest("[data-knowledge-toggle]");
  if (!button) return;
  const active = button.dataset.active === "true";
  const documentId = button.dataset.knowledgeToggle;
  const action = active ? "Remove this source from AI retrieval? Its file and metrics will be retained." : "Restore this source to AI retrieval?";
  if (!window.confirm(action)) return;
  button.disabled = true;
  try {
    await api(`/api/admin/knowledge-documents/${encodeURIComponent(documentId)}`, {
      method: "PATCH", body: JSON.stringify({active: !active}),
    });
    await refreshKnowledgeDocuments();
  } catch (error) {
    $("#knowledge-documents-status").textContent = error.message;
    button.disabled = false;
  }
});

$("#parsed-chunk-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const documentId = $("#parsed-document").value;
  const offset = Math.max(0, Number.parseInt($("#parsed-offset").value || "0", 10));
  const focusChunkIndex = Number.parseInt(event.currentTarget.dataset.focusChunk || "", 10);
  const stage = event.currentTarget.dataset.stage || "parser";
  const sourceChunkId = Number.parseInt(event.currentTarget.dataset.sourceChunkId || "", 10);
  delete event.currentTarget.dataset.focusChunk;
  delete event.currentTarget.dataset.stage;
  delete event.currentTarget.dataset.sourceChunkId;
  $("#parsed-chunk-list").innerHTML = '<p class="loading-card">Loading saved parser output…</p>';
  $("#parsed-table-list").innerHTML = '<p class="loading-card">Loading extracted tables…</p>';
  try {
    const sourceChunkParameter = Number.isInteger(sourceChunkId) && sourceChunkId > 0
      ? `&source_chunk_id=${sourceChunkId}` : "";
    const result = await api(`/api/admin/processing/${encodeURIComponent(documentId)}/chunks?offset=${offset}&limit=25&stage=${stage}${sourceChunkParameter}`);
    renderParsedChunks(result.chunks, documentId);
    $("#parsed-chunk-list").insertAdjacentHTML("afterbegin", `<p class="corpus-note">Showing ${result.stage === "parser" ? "saved parser output before embeddings" : "indexed retrieval chunks after embeddings"}.</p>`);
    if (Number.isInteger(focusChunkIndex)) {
      requestAnimationFrame(() => document.getElementById(`document-chunk-${focusChunkIndex}`)?.scrollIntoView({behavior: "smooth", block: "center"}));
    }
  } catch (error) {
    $("#parsed-chunk-list").innerHTML = `<p class="loading-card">${escapeHtml(error.message)}</p>`;
  }
  try {
    const result = await api(`/api/admin/processing/${encodeURIComponent(documentId)}/business-metric-extraction-runs`);
    renderBusinessMetricExtractionRuns(result.runs);
  } catch (error) {
    $("#business-metric-extraction-runs").innerHTML = `<p class="loading-card">${escapeHtml(error.message)}</p>`;
  }
  try {
    const result = await api(`/api/admin/processing/${encodeURIComponent(documentId)}/tables?row_limit=100`);
    renderExtractedTables(result.tables, documentId);
  } catch (error) {
    $("#parsed-table-list").innerHTML = error.status === 404
      ? '<p class="loading-card">No structured tables were extracted from this document.</p>'
      : `<p class="loading-card">${escapeHtml(error.message)}</p>`;
  }
});

$("#business-metric-replay-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const documentId = $("#parsed-document").value;
  if (!documentId) return;
  const button = $("#business-metric-replay-button");
  button.disabled = true;
  $("#business-metric-replay-status").textContent = "Re-running extraction against saved parser chunks…";
  try {
    const result = await api(
      `/api/admin/processing/${encodeURIComponent(documentId)}/business-metric-extraction-runs`,
      {method: "POST", body: JSON.stringify({decision_domain: replayDomainSelect.value, metric_name: replayMetricSelect.value})},
    );
    $("#business-metric-replay-status").textContent = `Run ${result.run_id}: ${result.status}; ${formatNumber(result.selected_chunk_count || 0)} / ${formatNumber(result.input_chunk_count || 0)} chunks selected; ${formatNumber(result.candidate_count)} candidates await review.`;
    const history = await api(`/api/admin/processing/${encodeURIComponent(documentId)}/business-metric-extraction-runs`);
    renderBusinessMetricExtractionRuns(history.runs);
  } catch (error) {
    $("#business-metric-replay-status").textContent = error.message;
  } finally {
    button.disabled = false;
  }
});

$("#ocr-test-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const button = $("#ocr-test-button");
  button.disabled = true;
  $("#ocr-test-status").textContent = "Running OCR and saving page previews, chunks, and tables…";
  try {
    const result = await api("/api/ocr-tests", {method:"POST", body:new FormData(event.currentTarget)});
    $("#ocr-test-status").textContent = `Saved isolated run ${result.run_id}: ${result.page_count} pages, ${result.chunk_count} chunks, ${result.table_count} tables. No embeddings or production document were created.`;
    await loadOcrTestRuns();
    await openOcrTestRun(result.run_id);
    form.reset();
  } catch (error) {
    $("#ocr-test-status").textContent = error.message;
  } finally {
    button.disabled = false;
  }
});

$("#ocr-test-runs").addEventListener("click", (event) => {
  const button = event.target.closest("[data-ocr-run-id]");
  if (button) openOcrTestRun(button.dataset.ocrRunId);
});

$("#login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  $("#login-error").hidden = true;
  try {
    const user = await api("/api/auth/login", { method: "POST", body: JSON.stringify({ username: $("#username").value, password: $("#password").value }) });
    await loadWorkspace(user);
  } catch (error) {
    $("#login-error").textContent = error.message;
    $("#login-error").hidden = false;
  }
});

$("#logout-button").addEventListener("click", async () => {
  await api("/api/auth/logout", { method: "POST" });
  $("#workspace").hidden = true;
  $("#login-view").hidden = false;
  $("#user-badge").hidden = true;
  $("#logout-button").hidden = true;
  activeTab = "knowledge";
  commerceSnapshot = null;
  commerceLoadedDomains.clear();
  commerceLoadingDomains.clear();
  commerceCampaignsLoaded = false;
  commerceCampaignsLoading = false;
  syncWorkspaceTabs();
});

async function loadCorpus() {
  try {
    const user = await api("/api/auth/me");
    await loadWorkspace(user);
  } catch (error) {
    if (error.message !== "Sign in to continue") $("#login-error").textContent = error.message;
  }
}

function renderSkeletonAnswer(panel, statusMessage = "Retrieving passages and preparing cited answer…") {
  panel.hidden = false;
  panel.innerHTML = `
    <div class="answer-header-wrap">
      <div class="answer-heading">
        <span class="answer-mark">AI</span>
        <div><span class="eyebrow">PROCESSING QUERY</span><h3>${escapeHtml(statusMessage)}</h3></div>
      </div>
    </div>
    <div class="skeleton-loader">
      <div class="skeleton-line medium"></div>
      <div class="skeleton-line"></div>
      <div class="skeleton-line short"></div>
      <div class="skeleton-card"></div>
    </div>
  `;
}

function setupQuickPrompts() {
  const container = $("#quick-prompts");
  if (!container) return;
  container.addEventListener("click", (event) => {
    const chip = event.target.closest(".quick-chip");
    if (!chip) return;
    const prompt = chip.dataset.prompt;
    if (prompt) {
      const textarea = $("#question");
      textarea.value = prompt;
      textarea.focus();
      $("#ask-form").dispatchEvent(new Event("submit", { cancelable: true }));
    }
  });
}

$("#ask-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = $("#ask-button");
  const question = $("#question").value.trim();
  if (!question) return;
  button.disabled = true;
  button.innerHTML = '<span>Searching sources…</span>';
  const panel = $("#answer-panel");
  renderSkeletonAnswer(panel, "Retrieving passages and preparing cited answer…");
  try {
    const payload = { question, retrieval_method: $("#retrieval-method").value };
    let data;
    try {
      data = await askOverWebSocket(payload, (status) => {
        button.innerHTML = `<span>${escapeHtml(status || "Synthesizing answer...")}</span>`;
      });
    } catch (error) {
      if (!error.safeToFallback) throw error;
      data = await api("/api/ask", { method: "POST", body: JSON.stringify(payload) });
    }
    renderAnswer(data);
  } catch (error) {
    panel.innerHTML = `<p class="error-message">${escapeHtml(error.message)}. Please check service configuration or connection.</p>`;
  } finally {
    button.disabled = false;
    button.innerHTML = '<span>Run query</span>';
  }
});

$("#business-question-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = $("#business-question-button");
  const decisionSuggestions = decisionSuggestionsPending;
  decisionSuggestionsPending = false;
  const question = decisionSuggestions ? "" : $("#business-question").value.trim();
  const businessDecisionDomain = $("#commerce-decision-domain").value;
  const panel = $("#business-answer-panel");
  if ((!decisionSuggestions && question.length < 3) || (decisionSuggestions && !businessDecisionDomain)) return;
  button.disabled = true;
  button.innerHTML = '<span>Analyzing sources…</span>';
  renderSkeletonAnswer(panel, decisionSuggestions
    ? "Combining recent Commerce SQL observations and company references…"
    : "Combining Commerce SQL observations and cited company references…");
  try {
    const result = await api("/api/ask", { method: "POST", body: JSON.stringify({
      ...(question ? { question } : {}),
      business_decision_domain: businessDecisionDomain || null,
      decision_suggestions: decisionSuggestions,
    }) });
    renderAnswer(result, panel);
  } catch (error) {
    panel.innerHTML = `<p class="error-message">${escapeHtml(error.message)}</p>`;
  } finally {
    button.disabled = false;
    button.innerHTML = '<span>Analyze decision evidence</span>';
  }
});

$(".decision-question-prompts").addEventListener("click", (event) => {
  const questionPrompt = event.target.closest("[data-decision-question]");
  if (questionPrompt) {
    $("#business-question").value = questionPrompt.dataset.decisionQuestion;
    $("#business-question").focus();
    return;
  }
  if (!event.target.closest("[data-decision-suggestions]")) return;
  if (!$("#commerce-decision-domain").value) return;
  decisionSuggestionsPending = true;
  $("#business-question-form").requestSubmit();
});

$("#analytics-section").addEventListener("click", (event) => {
  const inspectButton = event.target.closest("[data-inspect-indexed-chunk]");
  if (inspectButton) {
    const documentId = inspectButton.dataset.documentId;
    const sourceChunkId = Number.parseInt(inspectButton.dataset.sourceChunkId, 10);
    const chunkIndex = Number.parseInt(inspectButton.dataset.chunkIndex, 10);
    if (!documentId || !Number.isInteger(sourceChunkId) || sourceChunkId < 1
        || !Number.isInteger(chunkIndex) || chunkIndex < 0) return;
    $("#parsed-document").value = documentId;
    $("#parsed-offset").value = String(Math.floor(chunkIndex / 25) * 25);
    $("#parsed-chunk-form").dataset.focusChunk = String(chunkIndex);
    $("#parsed-chunk-form").dataset.stage = "indexed";
    $("#parsed-chunk-form").dataset.sourceChunkId = String(sourceChunkId);
    selectWorkspaceTab("processing");
    $("#parsed-chunk-form").requestSubmit();
    return;
  }
  const link = event.target.closest("[data-open-tab]");
  if (link) selectWorkspaceTab(link.dataset.openTab);
});

$("#monitoring-refresh").addEventListener("click", refreshAgentMonitoring);

$("#upload-synthetic-policy").addEventListener("change", (event) => {
  if (!event.currentTarget.checked) return;
  const form = $("#upload-form");
  form.elements.reference_type.value = "company_policy_reference";
  form.elements.source_publisher.value = "Commerce Demo (fictional organization)";
  form.elements.reference_applicability.value = "Fictional Commerce Demo only; not a policy of a real company.";
});

$("#upload-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const button = $("#upload-button");
  const file = $("#upload-file").files[0];
  const roles = [...form.querySelectorAll('input[name="allowed_roles"]:checked')].map((input) => input.value);
  const knowledgeDomains = [...form.querySelectorAll('input[name="knowledge_domains"]:checked')].map((input) => input.value);
  const referenceType = form.elements.reference_type.value;
  const publisher = form.elements.source_publisher.value.trim();
  const applicability = form.elements.reference_applicability.value.trim();
  const syntheticPolicy = form.elements.synthetic_company_policy.checked;
  if (!file || !roles.length) {
    $("#upload-status").textContent = "Select a supported document and at least one access role.";
    return;
  }
  if ((referenceType || knowledgeDomains.length) && (!referenceType || !knowledgeDomains.length || !publisher || !applicability)) {
    $("#upload-status").textContent = "Commerce references need a publisher, reference type, applicability scope, and at least one decision domain.";
    return;
  }
  if (syntheticPolicy && referenceType !== "company_policy_reference") {
    $("#upload-status").textContent = "A synthetic Commerce Demo document must be classified as a company policy.";
    return;
  }
  const body = new FormData();
  body.append("file", file);
  for (const name of ["title", "document_type", "domain", "source_publisher", "reference_type", "reference_applicability", "fiscal_year", "source_url"]) {
    const value = form.elements[name].value.trim();
    if (value) body.append(name, value);
  }
  body.append("synthetic_company_policy", syntheticPolicy ? "true" : "false");
  knowledgeDomains.forEach((domain) => body.append("knowledge_domains", domain));
  roles.forEach((role) => body.append("allowed_roles", role));
  button.disabled = true;
  $("#upload-status").textContent = "Uploading and processing the document…";
  try {
    const result = await api("/api/documents/upload", { method: "POST", body, headers: {} });
    const referenceStatus = referenceType
      ? syntheticPolicy
        ? ` Registered as a synthetic Commerce Demo policy for ${knowledgeDomains.join(", ")} (scope: ${applicability}).`
        : ` Classified as ${referenceType} for ${knowledgeDomains.join(", ")} (scope: ${applicability}); source is attributed, not treated as Commerce Demo policy.`
      : " No Commerce decision domain was assigned; parsed content is available to general document search only.";
    const traceStatus = result.business_metric_extraction_run_id
      ? ` Extraction trace ${result.business_metric_extraction_run_id} is available in Document processing.`
      : "";
    const pageSummary = result.page_count ? `${formatNumber(result.page_count)} pages` : "File processed";
    const extractionSummary = `${formatNumber(result.parser_chunk_count)} parser passages · ${formatNumber(result.indexed_chunk_count)} indexed passages · ${formatNumber(result.ocr_chunk_count)} OCR passages · ${formatNumber(result.table_count)} tables`;
    $("#upload-status").textContent = `Processed ${result.document_id}; status: ${result.processing_status}; ${pageSummary}; ${extractionSummary}.${referenceStatus}${traceStatus}`;
    form.reset();
    await loadWorkspace(await api("/api/auth/me"));
    const parsedDocument = $("#parsed-document");
    if ([...parsedDocument.options].some((option) => option.value === result.document_id)) {
      parsedDocument.value = result.document_id;
      selectWorkspaceTab("processing");
      $("#parsed-chunk-form").requestSubmit();
    }
  } catch (error) {
    $("#upload-status").textContent = error.message;
  } finally {
    button.disabled = false;
  }
});

$("#manual-metric-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const values = Object.fromEntries(new FormData(form));
  values.allowed_roles = [...form.querySelectorAll('input[name="allowed_roles"]:checked')].map((input) => input.value);
  if (!values.allowed_roles.length) {
    $("#manual-metric-status").textContent = "Select at least one role allowed to view this metric.";
    return;
  }
  const button = $("#manual-metric-button");
  button.disabled = true;
  $("#manual-metric-status").textContent = "Saving metric for verification…";
  try {
    await api("/api/metrics/manual", {method: "POST", body: JSON.stringify(values)});
    form.reset();
    $("#manual-metric-status").textContent = "Saved to the review queue. Verify it below before it appears in Business Analysis.";
    await loadWorkspace(await api("/api/auth/me"));
  } catch (error) {
    $("#manual-metric-status").textContent = error.message;
  } finally {
    button.disabled = false;
  }
});

$("#business-metric-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const values = Object.fromEntries(new FormData(form));
  values.allowed_roles = [...form.querySelectorAll('input[name="allowed_roles"]:checked')].map((input) => input.value);
  if (!values.allowed_roles.length) {
    $("#business-metric-status").textContent = "Select at least one role allowed to view this metric.";
    return;
  }
  const button = $("#business-metric-button");
  button.disabled = true;
  $("#business-metric-status").textContent = "Saving source observation for verification…";
  try {
    await api("/api/business-metrics/candidates", {method: "POST", body: JSON.stringify(values)});
    form.reset();
    $("#business-metric-status").textContent = "Saved in the review queue. It will appear in Business Analysis only after admin verification.";
    await loadWorkspace(await api("/api/auth/me"));
  } catch (error) {
    $("#business-metric-status").textContent = error.message;
  } finally {
    button.disabled = false;
  }
});

$("#candidate-list").addEventListener("submit", async (event) => {
  const form = event.target.closest("form[data-candidate-id]");
  if (!form) return;
  event.preventDefault();
  const values = Object.fromEntries(new FormData(form));
  try {
    const path = form.dataset.candidateKind === "business"
      ? `/api/business-metrics/${form.dataset.candidateId}/review`
      : `/api/analytics/candidates/${form.dataset.candidateId}/review`;
    await api(path, {method:"POST", body:JSON.stringify({status:"verified", normalized_value:values.normalized_value, unit:values.unit})});
    await handleCandidateProcessed(form);
  } catch (error) { alert(error.message); }
});

$("#candidate-list").addEventListener("click", async (event) => {
  const valueButton = event.target.closest("[data-candidate-value]");
  if (valueButton) {
    const candidate = valueButton.closest(".candidate-row");
    candidate.querySelectorAll("[data-candidate-value]").forEach((button) => button.setAttribute("aria-pressed", String(button === valueButton)));
    const input = candidate.querySelector('input[name="normalized_value"]');
    input.value = normalizeCandidateFigure(valueButton.dataset.candidateValue);
    candidate.querySelector(".review-value-preview").textContent = `Hiển thị trên dashboard: ${formatFinancialValue(parseVietnameseFinancialInput(input.value))}`;
    input.focus();
    return;
  }
  if (!event.target.matches("[data-reject]")) return;
  const form = event.target.closest("form[data-candidate-id]");
  try {
    const path = form.dataset.candidateKind === "business"
      ? `/api/business-metrics/${form.dataset.candidateId}/review`
      : `/api/analytics/candidates/${form.dataset.candidateId}/review`;
    await api(path, {method:"POST", body:JSON.stringify({status:"rejected"})});
    await handleCandidateProcessed(form);
  } catch (error) { alert(error.message); }
});

$("#candidate-list").addEventListener("input", (event) => {
  const input = event.target.closest('input[name="normalized_value"]');
  if (!input) return;
  const preview = input.closest("form").querySelector(".review-value-preview");
  const parsed = parseVietnameseFinancialInput(input.value);
  preview.textContent = Number.isFinite(parsed)
    ? `Hiển thị trên dashboard: ${formatFinancialValue(parsed)}`
    : "Dùng dấu chấm cho nhóm hàng nghìn và dấu phẩy cho phần thập phân.";
});

async function handleCandidateProcessed(form) {
  const row = form.closest(".candidate-row");
  if (row) {
    row.classList.add("removing");
    await new Promise((resolve) => setTimeout(resolve, 220));
    row.remove();
    if (!$("#candidate-list").querySelector(".candidate-row")) {
      $("#candidate-review").hidden = true;
    }
  }
  await refreshCandidateData();
}

async function refreshCandidateData() {
  try {
    const data = await api("/api/dashboard");
    const candidates = data.candidates || [];
    $("#candidate-review").hidden = !candidates.length;
    renderCandidates(data);
    if (currentUser && ["finance_analyst", "sustainability_analyst", "executive", "admin"].includes(currentUser.role)) {
      const analytics = await api("/api/analytics");
      renderAnalytics(analytics);
    }
  } catch (error) {
    console.error("Failed to refresh candidate data:", error);
  }
}

function setupThemeToggle() {
  const button = $("#theme-toggle");
  if (!button) return;
  button.addEventListener("click", () => {
    const isDark = document.documentElement.getAttribute("data-theme") === "dark";
    const nextTheme = isDark ? "light" : "dark";
    if (nextTheme === "dark") {
      document.documentElement.setAttribute("data-theme", "dark");
    } else {
      document.documentElement.removeAttribute("data-theme");
    }
    try {
      localStorage.setItem("app_theme", nextTheme);
    } catch {}
  });
}

setupThemeToggle();
setupQuickPrompts();
loadCorpus();
