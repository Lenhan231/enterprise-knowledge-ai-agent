const $ = (selector) => document.querySelector(selector);
let activeTab = "knowledge";
let currentUser = null;
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

function syntheticPolicySourcePageUrl(source) {
  if (source.synthetic_company_policy !== true || !source.document_id) return "";
  const page = Number(source.page_number);
  return `/api/documents/${encodeURIComponent(source.document_id)}/source${Number.isInteger(page) && page > 0 ? `#page=${page}` : ""}`;
}

function selectWorkspaceTab(name) {
  const button = $(`[data-tab-target="${name}"]`);
  if (!button || button.hidden) return;
  activeTab = name;
  const isKnowledgeTab = name === "knowledge";
  $(".intro").hidden = !isKnowledgeTab;
  $(".agent-overview").hidden = !isKnowledgeTab
    || ["document_processing_owner", "document_uploader"].includes(currentUser?.role);
  $(".stats").hidden = !isKnowledgeTab || currentUser?.role === "document_processing_owner";
  $("#inventory-snapshot").hidden = !isKnowledgeTab;
  document.querySelectorAll(".workspace-tab").forEach((tab) => {
    const selected = tab === button;
    tab.setAttribute("aria-selected", String(selected));
    tab.tabIndex = selected ? 0 : -1;
    tab.classList.toggle("active", selected);
  });
  document.querySelectorAll(".tab-panel").forEach((panel) => {
    panel.hidden = panel.id !== button.getAttribute("aria-controls");
  });
}

function syncWorkspaceTabs(user = currentUser) {
  const isProcessingOwner = user?.role === "document_processing_owner";
  const isAdmin = user?.role === "admin";
  const canAskDocuments = !isProcessingOwner && user?.role !== "document_uploader";
  const canUpload = ["document_uploader", "admin", "document_processing_owner"].includes(user?.role);
  const available = {
    knowledge: canAskDocuments,
    upload: canUpload,
    processing: isProcessingOwner,
    "ocr-lab": isProcessingOwner,
    "knowledge-management": isAdmin,
    access: isAdmin,
    monitoring: isAdmin,
  };
  document.querySelectorAll(".workspace-tab").forEach((button) => {
    button.hidden = !available[button.dataset.tabTarget];
  });
  if (!available[activeTab]) {
    activeTab = isProcessingOwner ? "processing" : available.knowledge ? "knowledge" : available.upload ? "upload" : "knowledge";
  }
  selectWorkspaceTab(activeTab);
}

const UPLOAD_ROLE_LABELS = {
  employee: ["Employee", "General document Q&A"],
  finance_analyst: ["Finance analyst", "Finance and analytics sources"],
  sustainability_analyst: ["Sustainability analyst", "Sustainability sources and analytics"],
  procurement: ["Procurement", "Procurement and supplier sources"],
  operations: ["Operations", "Operations sources and analytics"],
  legal_compliance: ["Legal and compliance", "Legal and compliance sources"],
  executive: ["Executive", "Executive sources and analytics"],
  admin: ["Administrator", "Administrative and review access"],
};

document.querySelectorAll("[data-open-tab]").forEach((button) => {
  button.addEventListener("click", () => selectWorkspaceTab(button.dataset.openTab));
});

function renderCorpus(data) {
  const companies = new Set(data.documents.map((doc) => doc.domain || "General").filter(Boolean));
  $("#company-name").textContent = companies.size || 0;
  $("#document-count").textContent = formatNumber(data.document_count);
  $("#chunk-count").textContent = formatNumber(data.chunk_count);
  const inFlight = data.documents.filter((doc) => !["ready", "parsed"].includes(doc.processing_status)).length;
  $("#processing-count").textContent = formatNumber(inFlight);
  $("#connection-status").textContent = "Agent workspace";
  document.querySelector(".status-dot").classList.add("connected");
}

function renderParsedChunkInspector(documents) {
  const section = $("#parsed-chunk-inspector");
  const select = $("#parsed-document");
  const selectedDocument = select.value;
  section.hidden = documents.length === 0;
  select.innerHTML = documents.map((doc) =>
    `<option value="${escapeHtml(doc.document_id)}">${escapeHtml(doc.title)} · ${escapeHtml(doc.processing_status || "unknown")}${doc.knowledge_base_active ? "" : " · removed from Q&A"}</option>`
  ).join("");
  if (documents.some((doc) => doc.document_id === selectedDocument)) {
    select.value = selectedDocument;
  }
}

function knowledgeDocumentIsRetrievable(doc) {
  return doc.knowledge_base_active && doc.processing_status === "ready" && Number(doc.chunk_count) > 0;
}

function renderKnowledgeDocuments() {
  const query = $("#knowledge-documents-search").value.trim().toLocaleLowerCase();
  const selectedDomain = $("#knowledge-domain-filter").value;
  const selectedState = $("#knowledge-state-filter").value;
  const matches = knowledgeDocuments.filter((doc) => {
    const domains = doc.knowledge_domains || [];
    const retrievable = knowledgeDocumentIsRetrievable(doc);
    const stateMatches = selectedState === "all"
      || (selectedState === "available" && retrievable)
      || (selectedState === "removed" && !doc.knowledge_base_active)
      || (selectedState === "attention" && doc.knowledge_base_active && !retrievable);
    const domainMatches = selectedDomain === "all"
      || (selectedDomain === "general" && domains.length === 0)
      || domains.includes(selectedDomain);
    const textMatches = [doc.title, doc.document_id, doc.source_publisher,
      doc.domain, doc.evidence_class, doc.synthetic_company_policy ? "synthetic demo policy" : "",
      ...domains].join(" ").toLocaleLowerCase().includes(query);
    return stateMatches && domainMatches && textMatches;
  });
  const retrievableCount = knowledgeDocuments.filter(knowledgeDocumentIsRetrievable).length;
  const removedCount = knowledgeDocuments.filter((doc) => !doc.knowledge_base_active).length;
  const attentionCount = knowledgeDocuments.filter((doc) => doc.knowledge_base_active && !knowledgeDocumentIsRetrievable(doc)).length;
  $("#knowledge-documents-status").textContent = `Showing ${formatNumber(matches.length)} of ${formatNumber(knowledgeDocuments.length)} sources · ${formatNumber(retrievableCount)} retrievable · ${formatNumber(removedCount)} removed · ${formatNumber(attentionCount)} need attention`;
  $("#knowledge-documents-list").innerHTML = matches.map((doc) => {
    const domains = (doc.knowledge_domains || []).join(", ") || doc.domain || "General";
    const href = validSourceUrl(doc.source_url);
    const sourceKind = doc.synthetic_company_policy
      ? "Synthetic demo policy · fictional Commerce Demo only"
      : ({ management_cookbook_reference: "Management method · general guidance",
          company_practice_reference: "Company practice · attributed example",
          platform_operating_rule: "Platform rule · scope-specific" }[doc.evidence_class] || "Knowledge source");
    const uploadedSource = doc.source_type === "user_upload" && doc.processing_status === "ready"
      ? uploadedSourcePageUrl(doc.document_id)
      : "";
    const sourceLink = doc.synthetic_company_policy
      ? `<a href="/api/admin/knowledge-documents/${encodeURIComponent(doc.document_id)}/source" target="_blank" rel="noopener noreferrer">Open original PDF</a>`
      : uploadedSource
        ? `<a href="${escapeHtml(uploadedSource)}" target="_blank" rel="noopener noreferrer">Open uploaded file</a>`
        : href ? `<a href="${escapeHtml(href)}" target="_blank" rel="noopener noreferrer">Open source</a>` : "";
    const canRetryEmbedding = doc.source_type === "user_upload" && doc.processing_status === "failed";
    return `<article class="knowledge-document-row ${doc.knowledge_base_active ? "" : "is-removed"}">
      <div class="knowledge-document-copy"><strong>${escapeHtml(doc.title)}</strong>
        <span class="knowledge-source-kind ${doc.synthetic_company_policy ? "is-synthetic" : ""}">${escapeHtml(sourceKind)}</span>
        <span>${escapeHtml(doc.source_publisher || "Unknown publisher")} · ${escapeHtml(doc.format || "File")} · ${formatNumber(doc.chunk_count)} passages</span>
        <small>${escapeHtml(domains)} · ${escapeHtml(doc.processing_status || "unknown")} · ${knowledgeDocumentIsRetrievable(doc) ? "Available to AI" : doc.knowledge_base_active ? "Not retrievable" : "Removed from AI retrieval"}</small>
        <code>${escapeHtml(doc.document_id)}</code>${sourceLink}
        <details class="knowledge-access-editor"><summary>Access roles: ${escapeHtml((doc.allowed_roles || []).join(", ") || "none")}</summary>
          <form class="knowledge-access-form" data-document-id="${escapeHtml(doc.document_id)}">
            <div class="knowledge-access-options">${Object.entries(UPLOAD_ROLE_LABELS).map(([role, [label]]) => `<label><input type="checkbox" name="allowed_roles" value="${escapeHtml(role)}" ${(doc.allowed_roles || []).includes(role) ? "checked" : ""}><span>${escapeHtml(label)}</span></label>`).join("")}</div>
            <button class="secondary-button" type="submit">Save access</button>
            <small data-access-status aria-live="polite"></small>
          </form>
        </details>
      </div>
      <div class="knowledge-document-actions">
        ${canRetryEmbedding ? `<button class="secondary-button" type="button" data-retry-embedding="${escapeHtml(doc.document_id)}">Retry embedding</button>` : ""}
        <button class="${doc.knowledge_base_active ? "danger-button" : "secondary-button"}" type="button" data-knowledge-toggle="${escapeHtml(doc.document_id)}" data-active="${doc.knowledge_base_active ? "true" : "false"}">${doc.knowledge_base_active ? "Remove from knowledge base" : "Restore to knowledge base"}</button>
      </div>
    </article>`;
  }).join("") || '<p class="loading-card">No matching indexed sources.</p>';
}

async function refreshKnowledgeDocuments() {
  $("#knowledge-documents-status").textContent = "Loading indexed sources…";
  const result = await api("/api/admin/knowledge-documents");
  knowledgeDocuments = result.documents;
  if (currentUser?.role === "admin") renderKnowledgeDocuments();
  if (currentUser?.role === "document_processing_owner") renderParsedChunkInspector(knowledgeDocuments);
}

function renderOcrDiagnostics(diagnostics) {
  if (!Array.isArray(diagnostics) || diagnostics.length === 0) return "";
  return diagnostics.map((item) => {
    const message = item.reason === "low_mean_word_confidence"
      ? `Embedded image OCR skipped: confidence ${formatNumber(item.mean_word_confidence)}/100 was below the ${formatNumber(item.minimum_word_confidence)}/100 threshold.`
      : `Embedded image OCR skipped: only ${formatNumber(item.word_count)} words were recognized.`;
    return `<p class="ocr-diagnostic" role="note"><strong>OCR review needed.</strong> ${escapeHtml(message)} No OCR-derived text or table from this image region was added; inspect the original page.</p>`;
  }).join("");
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
        <div class="candidate-heading"><strong>${pageNumber ? `Page ${formatNumber(pageNumber)} · ` : ""}Passage ${formatNumber(chunk.chunk_index + 1)}</strong><span>${escapeHtml(chunk.metadata?.text_extraction_method || "parser output")}</span></div>
      ${sourceUrl ? `<a class="document-link" href="${escapeHtml(sourceUrl)}" target="_blank" rel="noopener noreferrer">${escapeHtml(sourceLabel)}</a>` : ""}
      ${renderOcrDiagnostics(chunk.metadata?.ocr_diagnostics)}
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
    const continuation = [
      table.metadata?.continued_from_page && `Continued from page ${formatNumber(table.metadata.continued_from_page)}`,
      table.metadata?.continued_to_page && `Continues on page ${formatNumber(table.metadata.continued_to_page)}`,
    ].filter(Boolean).join(" · ");
    const sourceLocation = table.page_number
      ? `Page ${formatNumber(table.page_number)}`
      : table.metadata?.sheet_name ? `Sheet ${escapeHtml(table.metadata.sheet_name)}`
        : table.metadata?.slide_number ? `Slide ${formatNumber(table.metadata.slide_number)}` : null;
    return `<article class="candidate-row">
      <div class="candidate-heading"><strong>${sourceLocation ? `${sourceLocation} · ` : ""}Table ${formatNumber(table.table_index + 1)}</strong><span>${formatNumber(table.row_count)} rows · showing ${formatNumber(rows.length)}</span></div>
      ${continuation ? `<p class="corpus-note">${escapeHtml(continuation)}</p>` : ""}
      ${sourceUrl ? `<a class="document-link" href="${escapeHtml(sourceUrl)}" target="_blank" rel="noopener noreferrer">${escapeHtml(sourceLabel)}</a>` : ""}
      <div class="extracted-table-wrap"><table class="extracted-table"><thead><tr>${columns.map((column) => `<th>${escapeHtml(column)}</th>`).join("")}</tr></thead><tbody>${rows.map((row) => `<tr>${columns.map((column) => `<td>${escapeHtml(row?.[column] ?? "")}</td>`).join("")}</tr>`).join("")}</tbody></table></div>
      <details class="candidate-source"><summary>Table metadata</summary><pre>${escapeHtml(JSON.stringify(table.metadata, null, 2))}</pre></details>
    </article>`;
  }).join("") || '<p class="loading-card">No structured tables were extracted from this document.</p>';
}

async function loadOcrTestRuns() {
  const result = await api("/api/upload-tests");
  $("#ocr-test-runs").innerHTML = result.runs.map((run) => {
    const config = run.processor_config || {};
    const engine = config.parser_engine;
    const selected = config.parser_settings?.[engine] || config;
    const parserSettings = `Docling · ${selected.docling_device || "cpu"} · OCR ${selected.docling_ocr ? "on" : "off"} (${selected.docling_ocr_language || "vi"}) · tables ${selected.docling_table_structure ? "on" : "off"} · ${selected.docling_num_threads || 4} threads`;
    const settings = parserSettings;
    const previewSummary = run.page_count ? `${formatNumber(run.page_count)} page previews` : "no page previews";
    const processingSummary = `processing ${formatDuration(run.runtime_info?.processing_time_ms)}`;
    return `<button type="button" class="ocr-run-button" data-ocr-run-id="${escapeHtml(run.run_id)}"><strong>${escapeHtml(run.source_filename)}</strong><span>${escapeHtml(new Date(run.created_at).toLocaleString())} · ${processingSummary} · ${previewSummary} · ${formatNumber(run.element_count)} parser elements · ${formatNumber(run.table_count)} tables · ${escapeHtml(settings)}</span></button>`;
  }).join("") || '<p class="loading-card">No upload tests yet. Upload a supported document above to create one.</p>';
}

function renderOcrTestDetails(run) {
  const allPages = [...new Set([
    ...run.pages,
    ...run.elements.map((element) => element.metadata?.page_number == null ? NaN : Number(element.metadata.page_number)).filter(Number.isFinite),
    ...run.tables.map((table) => table.page_number == null ? NaN : Number(table.page_number)).filter(Number.isFinite),
  ])].sort((a, b) => a - b);
  const pageContent = allPages.map((pageNumber, pageIndex) => {
    const pagePreview = `<img loading="lazy" alt="Rendered source page ${formatNumber(pageNumber)}" src="/api/upload-tests/${encodeURIComponent(run.run_id)}/pages/${pageNumber}/preview">`;
    const elements = run.elements.filter((element) => Number(element.metadata?.page_number) === pageNumber);
    const tables = run.tables.filter((table) => Number(table.page_number) === pageNumber);
    const ocrDiagnostics = elements.flatMap((element) => element.metadata?.ocr_diagnostics || []);
    const tablesHtml = tables.map((table) => {
      const data = table.structured_data || {};
      const context = table.context || {};
      const columns = Array.isArray(data.columns) ? data.columns : [];
      const rows = Array.isArray(data.rows) ? data.rows : [];
      const headers = columns.length ? columns : [...new Set(rows.flatMap((row) => Object.keys(row || {})))];
      const metadata = table.metadata || {};
      const parserMetadata = metadata.parser_details || {};
      const ocr = { ...(metadata.ocr || parserMetadata.ocr || {}) };
      if (!ocr.engine && parserMetadata.parser === "paddleocr.PP-StructureV3") {
        ocr.engine = parserMetadata.parser;
        ocr.render_scale = parserMetadata.render_scale;
      }
      const bbox = Array.isArray(metadata.bbox)
        ? metadata.bbox.map((value) => Number(value).toFixed(1)).join(" · ")
        : "Not available";
      const continuation = [
        metadata.continued_from_page && `from page ${formatNumber(metadata.continued_from_page)}`,
        metadata.continued_to_page && `to page ${formatNumber(metadata.continued_to_page)}`,
      ].filter(Boolean).join(" · ");
      const parserDetails = [
        ["OCR", [ocr.engine, ocr.language && `language ${ocr.language}`, ocr.table_psm && `PSM ${ocr.table_psm}`, ocr.render_scale && `scale ${ocr.render_scale}×`, ocr.mean_word_confidence != null && `mean word confidence ${ocr.mean_word_confidence}/100`, ocr.orientation_correction_degrees && `rotation corrected ${ocr.orientation_correction_degrees}°`, ocr.deskew_correction_degrees && `deskew corrected ${ocr.deskew_correction_degrees}°`].filter(Boolean).join(" · ") || "Not available"],
        ["Extraction", metadata.table_extraction_method || parserMetadata.table_extraction_method || parserMetadata.table_model || "Not available"],
        ["Detection", metadata.table_detection_strategy || parserMetadata.table_detection_strategy || parserMetadata.layout_model || "Not available"],
        ["Table region", `${bbox}${metadata.bbox_coordinate_system ? ` (${metadata.bbox_coordinate_system})` : ""}`],
        ["Structure", `${formatNumber(rows.length)} rows · ${formatNumber(headers.length)} columns`],
        ...(continuation ? [["Continuation", continuation]] : []),
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
      <summary>Page ${formatNumber(pageNumber)} · ${formatNumber(elements.length)} parser elements · ${formatNumber(tables.length)} tables</summary>
      <div class="ocr-test-page-content">
      <section class="ocr-test-raw"><h4>Raw page</h4>${pagePreview}</section>
      <section class="ocr-test-extracted"><h4>Extracted output</h4>
        ${renderOcrDiagnostics(ocrDiagnostics)}
        <details class="ocr-test-elements"><summary>Document elements · ${formatNumber(elements.length)} elements</summary>${elements.map((element) => `<article class="ocr-test-element"><div class="candidate-heading"><strong>Element ${formatNumber(element.element_index + 1)}</strong><span>${formatNumber(element.content.length)} chars · ${escapeHtml(element.metadata?.element_type || "text")} · ${escapeHtml(element.metadata?.text_extraction_method || "parser output")}</span></div><pre>${escapeHtml(element.content)}</pre><details class="candidate-source"><summary>Element metadata</summary><pre>${escapeHtml(JSON.stringify(element.metadata, null, 2))}</pre></details></article>`).join("") || '<p class="ocr-test-empty">No parser elements on this page.</p>'}</details>
        <h4 class="ocr-test-table-heading">Extracted tables</h4>
        ${tablesHtml || '<p class="ocr-test-empty">No structured table detected on this page.</p>'}
      </section>
      </div>
    </details>`;
  }).join("");
  const unpagedElements = run.elements.filter((element) => element.metadata?.page_number == null);
  const unpagedTables = run.tables.filter((table) => table.page_number == null);
  const unpagedOutput = unpagedElements.length || unpagedTables.length
    ? `<section class="ocr-test-page">
        <h3>Document content · no page previews</h3>
        <section class="ocr-test-extracted"><h4>Extracted output · ${formatNumber(unpagedElements.length)} document elements</h4>
          ${unpagedElements.map((element) => `<article class="ocr-test-element"><div class="candidate-heading"><strong>Element ${formatNumber(element.element_index + 1)}</strong><span>${formatNumber(element.content.length)} chars · ${escapeHtml(element.metadata?.element_type || "text")} · ${escapeHtml(element.metadata?.text_extraction_method || "parser output")}</span></div><pre>${escapeHtml(element.content)}</pre><details class="candidate-source"><summary>Element metadata</summary><pre>${escapeHtml(JSON.stringify(element.metadata, null, 2))}</pre></details></article>`).join("") || '<p class="ocr-test-empty">No parser elements.</p>'}
          <h4 class="ocr-test-table-heading">Extracted tables · ${formatNumber(unpagedTables.length)}</h4>
          ${unpagedTables.map((table) => {
            const data = table.structured_data || {};
            const rows = Array.isArray(data.rows) ? data.rows : [];
            const columns = Array.isArray(data.columns) && data.columns.length
              ? data.columns : [...new Set(rows.flatMap((row) => Object.keys(row || {})))];
            const location = table.metadata?.sheet_name ? ` · ${escapeHtml(table.metadata.sheet_name)}` : "";
            return `<article class="ocr-test-table"><h5>Table ${formatNumber(table.table_index + 1)}${location} <span>${formatNumber(rows.length)} rows</span></h5>
              ${columns.length ? `<div class="ocr-test-table-wrap"><table class="extracted-table"><thead><tr>${columns.map((column) => `<th>${escapeHtml(column)}</th>`).join("")}</tr></thead><tbody>${rows.map((row) => `<tr>${columns.map((column) => `<td>${escapeHtml(row?.[column] ?? "")}</td>`).join("")}</tr>`).join("")}</tbody></table></div>` : `<pre>${escapeHtml(JSON.stringify(data, null, 2))}</pre>`}
              <details class="candidate-source"><summary>Table metadata</summary><pre>${escapeHtml(JSON.stringify(table.metadata, null, 2))}</pre></details></article>`;
          }).join("") || '<p class="ocr-test-empty">No unpaged structured tables.</p>'}
        </section>
      </section>`
    : "";
  const processingSummary = `Processing time: ${formatDuration(run.runtime_info?.processing_time_ms)}`;
  $("#ocr-test-results").innerHTML = `<article class="ocr-test-run">
    <div class="candidate-heading"><strong>${escapeHtml(run.source_filename)}</strong><span>${processingSummary} · ${run.page_count ? `${formatNumber(run.page_count)} page previews` : "No page previews"} · ${formatNumber(run.elements.length)} parser elements · ${formatNumber(run.tables.length)} tables</span></div>
    <p class="corpus-note">SHA-256: <code>${escapeHtml(run.source_sha256)}</code></p>
    <details class="candidate-source"><summary>Parser configuration and versions</summary><pre>${escapeHtml(JSON.stringify({processor_config:run.processor_config,runtime_info:run.runtime_info},null,2))}</pre></details>
    <div class="ocr-test-pages">${pageContent}${unpagedOutput}</div>
  </article>`;
}

async function openOcrTestRun(runId) {
  $("#ocr-test-results").innerHTML = '<p class="loading-card">Loading test pages and parser output…</p>';
  try {
    renderOcrTestDetails(await api(`/api/upload-tests/${encodeURIComponent(runId)}`));
  } catch (error) {
    $("#ocr-test-results").innerHTML = `<p class="loading-card">${escapeHtml(error.message)}</p>`;
  }
}

function updateUploadTestParserSettings() {
  const engine = $("#ocr-test-parser").value;
  document.querySelectorAll("#ocr-test-form [data-parser-settings]").forEach((fieldset) => {
    const active = fieldset.dataset.parserSettings === engine;
    fieldset.hidden = !active;
    fieldset.querySelectorAll("input, select, textarea").forEach((control) => {
      control.disabled = !active;
    });
  });
}

$("#ocr-test-parser").addEventListener("change", updateUploadTestParserSettings);
updateUploadTestParserSettings();

function formatNumber(value) {
  return new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 3 }).format(value);
}

function formatDuration(milliseconds) {
  const value = Number(milliseconds);
  if (!Number.isFinite(value)) return "time unavailable";
  return value < 1000 ? `${formatNumber(value)} ms` : `${formatNumber(value / 1000)} s`;
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
    const observedMax = Math.max(...values.filter((value) => value !== null), 0) || 1;
    const max = visualization.unit === "%" ? Math.max(100, observedMax) : observedMax * 1.1;
    const x = (index) => left + (categories.length === 1 ? plotWidth / 2 : index * plotWidth / (categories.length - 1));
    const y = (value) => top + plotHeight - value / max * plotHeight;
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
  return `<section class="answer-visualization"><h3>${escapeHtml(visualization.title || "Verified data trend")}</h3>${charts}<p class="chart-note">Chart values come from the cited database observations. Review the source and scope in the response above.</p></section>`;
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
  const usedEvidenceFallback = Boolean(data.answer_fallback_reason);
  const domainLabels = {
    inventory_allocation: "Inventory allocation",
    promotion_planning: "Promotion planning",
    nationwide_logistics: "Nationwide logistics",
  };
  const domainNote = domainLabels[data.business_decision_domain]
    ? `<p class="analysis-caveat answer-provenance-note" role="status"><strong>Decision domain:</strong> ${escapeHtml(domainLabels[data.business_decision_domain])}${data.business_domain_auto_detected ? " · detected from your question" : " · selected"}</p>`
    : data.needs_domain_clarification
      ? '<p class="analysis-caveat answer-provenance-note" role="status"><strong>No analysis was run.</strong> Choose one decision domain or clarify the question.</p>'
      : "";
  const answerFallbackNotes = {
    provider_rate_limited: "The answer model was rate-limited. This response uses a conservative, built-in evidence fallback; it is not a model-synthesized recommendation.",
    provider_unavailable: "The answer model was unavailable. This response uses a conservative, built-in evidence fallback; it is not a model-synthesized recommendation.",
    evidence_validation_failed: "The model draft did not pass grounding checks. This response uses a conservative, built-in evidence fallback instead.",
    unsupported_measure: "The Commerce data cannot establish campaign ROI or incremental profit without campaign costs and a valid counterfactual; this response summarizes the available evidence without estimating either measure.",
  };
  const fallbackNote = data.decision_suggestions_fallback && ["provider_rate_limited", "provider_unavailable"].includes(data.answer_fallback_reason)
    ? `The model provider was ${data.answer_fallback_reason === "provider_rate_limited" ? "rate-limited" : "unavailable"}. One conservative next step is shown; the requested multi-action recommendation could not be generated.`
    : data.decision_suggestions_fallback && data.answer_fallback_reason === "evidence_validation_failed"
      ? "The model draft failed grounding checks. One conservative next step is shown; the requested multi-action recommendation could not be validated."
    : data.agent === "knowledge" && ["provider_rate_limited", "provider_unavailable"].includes(data.answer_fallback_reason)
    ? "The model provider was unavailable. Retrieved passages are shown verbatim; no synthesized answer was generated."
    : data.agent === "knowledge" && data.answer_fallback_reason === "evidence_validation_failed"
      ? "The model draft lacked valid source citations and was rejected. Retrieved passages are shown verbatim."
      : answerFallbackNotes[data.answer_fallback_reason];
  const decisionModeNote = answerFallbackNotes[data.answer_fallback_reason]
    ? `<p class="analysis-caveat answer-provenance-note" role="note"><strong>${data.agent === "knowledge" ? "Source-only fallback." : "Decision-support fallback."}</strong> ${fallbackNote}</p>`
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
  const usage = data.token_usage;
  const usageStages = usage ? [
    ["SQL generation", usage.sql_generation],
    ["Answer generation", usage.answer_generation],
  ].filter(([, value]) => value && Number.isInteger(value.total_tokens)) : [];
  const tokenUsage = usageStages.length
    ? `<details class="token-usage"><summary>Generation tokens · ${Number(usage.total?.total_tokens || 0).toLocaleString()} total</summary><ul>${usageStages.map(([label, value]) => `<li>${escapeHtml(label)}: ${Number(value.input_tokens || 0).toLocaleString()} in · ${Number(value.output_tokens || 0).toLocaleString()} out · ${Number(value.total_tokens).toLocaleString()} total</li>`).join("")}</ul><small>SQL and answer model calls only; embeddings and routing are not included.</small></details>`
    : "";
  const limitations = Array.isArray(data.limitations) && data.limitations.length
    ? `<p class="analysis-caveat answer-provenance-note"><strong>Limits:</strong> ${data.limitations.map(escapeHtml).join(" · ")}</p>`
    : "";
  panel.innerHTML = `
    <div class="answer-header-wrap">
      <div class="answer-heading">
        <span class="answer-mark">${usedEvidenceFallback ? "EV" : "AI"}</span>
        <div><span class="eyebrow">${escapeHtml(({knowledge:"KNOWLEDGE AGENT",sql_analytics:"ANALYTICS AGENT",dashboard:"INVENTORY AGENT",report:"REPORT AGENT",agentic:"AGENTIC ROUTER",hybrid:"KNOWLEDGE + ANALYTICS"})[data.agent] || "AGENT RESPONSE")}</span><h3>${usedEvidenceFallback ? "Evidence fallback" : "Synthesized answer"}</h3></div>
      </div>
      <div class="answer-actions-bar">
        <button type="button" class="action-btn" id="copy-answer-btn" title="Copy response text">Copy</button>
      </div>
    </div>
    ${domainNote}
    ${decisionModeNote}
    ${referenceRetrievalNote}
    ${questionSqlFallbackNote}
    ${limitations}
    ${tokenUsage}
    <div class="answer-text">${renderAnswerBody(data.answer)}</div>
    ${renderAgentInventoryDashboard(data.data?.dashboard)}
    ${renderAgentRows(data.data)}
    ${renderDashboardVisualization(data.data?.visualization)}
    ${data.citation_validation_failed ? `<p class="error-message">The answer was withheld because it failed evidence validation.${data.decision_validation_failure ? ` <details><summary>Admin diagnostic</summary><code>${escapeHtml(data.decision_validation_failure)}</code>${data.decision_validation_numeric_tokens?.length ? `<p>Unsupported numeric claims: ${data.decision_validation_numeric_tokens.map(escapeHtml).join(", ")}</p>` : ""}</details>` : ""}</p>` : citations.length ? `
      <div class="citations">
        <div class="citation-header-row">
          <h4>Cited Sources (${citations.length})</h4>
          <span class="citation-count-badge">${citations.length} source${citations.length === 1 ? "" : "s"}</span>
        </div>
        ${citations.map((source) => {
          const href = uploadedSourcePageUrl(source.document_id, source.page_number)
            || syntheticPolicySourcePageUrl(source)
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
          const ocrInfo = source.ocr && typeof source.ocr === "object" ? source.ocr : null;
          const ocrMethod = String(source.text_extraction_method || "").toLocaleLowerCase();
          const ocrDerived = Boolean(ocrInfo) || /(?:^|[_+])(?:tesseract|paddleocr|ocr)(?:$|[_+])/.test(ocrMethod);
          const ocrLabel = ocrInfo?.engine ? ` · ${escapeHtml(ocrInfo.engine)}` : "";
          const ocrNote = ocrDerived
            ? `<p class="citation-ocr-note"><strong>OCR-extracted text${ocrLabel}.</strong> OCR may misread words; check the original page before treating this passage as a rule.</p>`
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
              ${ocrNote}
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

  panel.scrollIntoView({ behavior: "smooth", block: "start" });
}

function renderAgentInventoryDashboard(dashboard) {
  if (dashboard?.outline_id !== "inventory_control") return "";
  const kpis = dashboard.kpis || {};
  const metrics = [["SKUs", kpis.sku_count], ["Stockout rate", kpis.stockout_rate == null ? null : `${Number(kpis.stockout_rate).toFixed(1)}%`],
    ["Overstock rate", kpis.overstock_rate == null ? null : `${Number(kpis.overstock_rate).toFixed(1)}%`],
    ["Mean fill rate", kpis.mean_fill_rate == null ? null : `${(Number(kpis.mean_fill_rate) * 100).toFixed(1)}%`]];
  const exceptions = dashboard.exceptions || [];
  const columns = ["product_name", "category", "stock_on_hand", "days_of_supply", "stockout_flag", "overstock_flag", "reorder_flag"];
  const rows = exceptions.slice(0, 25).map((row) => `<tr>${columns.map((key) => `<td>${escapeHtml(row[key] ?? "—")}</td>`).join("")}</tr>`).join("");
  return `<section class="agent-inventory-result"><div class="section-heading"><div><p class="eyebrow">LATEST SNAPSHOT · ${escapeHtml(dashboard.snapshot_date || "date unavailable")}</p><h3>${escapeHtml(dashboard.title || "Inventory Control & Exceptions")}</h3></div></div>
    <div class="agent-result-kpis">${metrics.map(([label,value]) => `<article><span>${escapeHtml(label)}</span><strong>${escapeHtml(value ?? "Unavailable")}</strong></article>`).join("")}</div>
    <h4>Flagged products</h4>${rows ? `<div class="commerce-table-wrap"><table><thead><tr>${columns.map((key) => `<th scope="col">${escapeHtml(key.replaceAll("_", " "))}</th>`).join("")}</tr></thead><tbody>${rows}</tbody></table></div>` : `<p class="no-citations">No inventory exceptions were returned.</p>`}
  </section>`;
}

async function loadInventorySnapshot() {
  const panel = $("#inventory-snapshot");
  panel.hidden = false;
  panel.innerHTML = '<p class="analysis-empty">Loading latest inventory snapshot…</p>';
  try {
    const result = await api("/api/agents/chat", {
      method: "POST",
      body: JSON.stringify({
        question: "Show the latest inventory snapshot and stock exceptions.",
        agent_mode: "dashboard",
      }),
    });
    const dashboard = renderAgentInventoryDashboard(result.data?.dashboard);
    panel.innerHTML = dashboard || '<p class="analysis-empty">No inventory snapshot is available.</p>';
  } catch (error) {
    panel.innerHTML = `<p class="analysis-empty">Inventory snapshot unavailable: ${escapeHtml(error.message)}</p>`;
  }
}

function renderAgentRows(data) {
  const groups = [["Results", data], ...["sql", "analytics", "knowledge"].map((key) => [key, data?.[key]])];
  return groups.map(([label, value]) => {
    const rows = value?.rows;
    if (!Array.isArray(rows) || !rows.length || !rows.every((row) => row && typeof row === "object" && !Array.isArray(row))) return "";
    const columns = Object.keys(rows[0]).slice(0, 12);
    return `<section class="agent-data-result"><h4>${escapeHtml(label)}</h4><div class="commerce-table-wrap"><table><thead><tr>${columns.map((key) => `<th scope="col">${escapeHtml(key.replaceAll("_", " "))}</th>`).join("")}</tr></thead><tbody>${rows.slice(0, 50).map((row) => `<tr>${columns.map((key) => `<td>${escapeHtml(row[key] ?? "—")}</td>`).join("")}</tr>`).join("")}</tbody></table></div></section>`;
  }).join("");
}

function renderAgentResult(result) {
  const citations = (result.evidence || []).map((item) => {
    const metadata = item.metadata || {};
    return { ...metadata, id: item.citation_id, title: item.source, source_type: item.source_type,
      content: item.content, score: metadata.similarity_score };
  });
  renderAnswer({ ...result.metadata, ...result, citations });
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

async function api(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (!(options.body instanceof FormData)) headers["Content-Type"] = "application/json";
  headers["ngrok-skip-browser-warning"] = "1";
  const response = await fetch(path, { credentials: "same-origin", ...options, headers });
  if (response.status === 401) {
    $("#login-view").hidden = false;
    $("#workspace").hidden = true;
    $("#login-brand-sidebar").hidden = false;
    throw new Error("Sign in to continue");
  }
  let data;
  try { data = await response.json(); }
  catch {
    throw new Error(`Server returned a non-JSON response (HTTP ${response.status}); check the backend tunnel and Vercel rewrite.`);
  }
  if (!response.ok) {
    const detail = Array.isArray(data.detail)
      ? data.detail.map((issue) => {
        const field = Array.isArray(issue.loc) ? issue.loc.at(-1) : "";
        return [field, issue.msg].filter(Boolean).join(": ");
      }).filter(Boolean).join("; ")
      : data.detail;
    throw Object.assign(new Error(detail || "Request failed"), { status: response.status });
  }
  return data;
}

async function loadWorkspace(user) {
  currentUser = user;
  $("#login-view").hidden = true;
  $("#login-brand-sidebar").hidden = true;
  $("#workspace").hidden = false;
  $("#upload-section").hidden = true;
  $("#processing-upload-status").hidden = true;
  $("#processing-upload-status").textContent = "";
  delete $("#processing-upload-status").dataset.state;
  $("#admin-section").hidden = true;
  $("#monitoring-section").hidden = true;
  syncWorkspaceTabs();
  $("#access-matrix").replaceChildren();
  $("#connection-status").textContent = "Knowledge base connected";
  $("#user-badge").textContent = `${user.username} · ${user.role}`;
  $("#user-badge").hidden = false;
  $("#logout-button").hidden = false;
  $(".intro").hidden = user.role === "document_processing_owner";
  $(".agent-overview").hidden = ["document_processing_owner", "document_uploader"].includes(user.role);
  $(".stats").hidden = user.role === "document_processing_owner";
  const canUseAnalytics = ["admin", "finance_analyst", "sustainability_analyst", "operations", "executive"].includes(user.role);
  $("#inventory-snapshot").hidden = false;
  ["#analytics-agent-card", "#inventory-agent-card", "#report-agent-card", "#report-agent-form-section"].forEach((selector) => {
    $(selector).hidden = !canUseAnalytics;
  });
  ["sql", "agentic"].forEach((mode) => {
    $("#agent-mode option[value='" + mode + "']").hidden = !canUseAnalytics;
  });
  if (!canUseAnalytics && ["sql", "agentic"].includes($("#agent-mode").value)) {
    $("#agent-mode").value = "knowledge";
  }
  if (user.role !== "document_processing_owner") {
    try { renderCorpus(await api("/api/dashboard")); }
    catch (error) { $("#connection-status").textContent = `Knowledge base unavailable: ${error.message}`; }
  }
  if (canUseAnalytics) void loadInventorySnapshot();
  else $("#inventory-snapshot").innerHTML = '<p class="analysis-empty">Inventory snapshot requires analytics access.</p>';
  if (["admin", "document_uploader", "document_processing_owner"].includes(user.role)) {
    try {
      const capability = await api("/api/documents/upload-capability");
      if (capability.can_upload) {
        const { roles } = await api("/api/documents/roles");
        $("#upload-role-options").innerHTML = roles.map((role) => {
          const [label, description] = UPLOAD_ROLE_LABELS[role] || [role.replaceAll("_", " "), "Document Q&A access"];
          return `<label class="upload-role-option"><input type="checkbox" name="allowed_roles" value="${escapeHtml(role)}"><span><strong>${escapeHtml(label)}</strong><small>${escapeHtml(description)}</small></span></label>`;
        }).join("");
        $("#upload-role-options").querySelectorAll('input[name="allowed_roles"]').forEach((input) => {
          input.addEventListener("change", () => {
            updateUploadRoleSelection();
          });
        });
        updateUploadRoleSelection();
        $("#upload-button").disabled = false;
        const canSaveParserOutput = user.role === "document_processing_owner";
        $("#parser-handoff-button").hidden = !canSaveParserOutput;
        $("#parser-handoff-button").disabled = !canSaveParserOutput;
        $("#upload-section").hidden = false;
        $("#upload-status").textContent = "";
        delete $("#upload-status").dataset.state;
      }
    } catch (error) {
      $("#upload-section").hidden = false;
      $("#upload-button").disabled = true;
      $("#parser-handoff-button").disabled = true;
      $("#upload-status").dataset.state = "error";
      $("#upload-status").textContent = `Upload permissions could not be loaded: ${error.message}`;
    }
  }
  try {
    if (user.role === "admin") {
      const access = await api("/api/admin/access-matrix");
      $("#access-matrix").innerHTML = access.roles.map((role) => `<article><strong>${escapeHtml(role.role)}</strong><span>${role.permissions.map(escapeHtml).join(" · ")}</span></article>`).join("");
      $("#admin-section").hidden = false;
      $("#monitoring-section").hidden = false;
      await refreshAgentMonitoring();
      await refreshKnowledgeDocuments();
    }
    if (user.role === "document_processing_owner") {
      await refreshKnowledgeDocuments();
      await loadOcrTestRuns();
    }
    syncWorkspaceTabs(user);
    $("#login-error").hidden = true;
  } catch (error) {
    syncWorkspaceTabs(user);
    if (error.message !== "Sign in to continue") {
      $("#connection-status").textContent = `Workspace loaded with an error: ${error.message}`;
    }
  }
}

$("#workspace-tabs").addEventListener("click", (event) => {
  const button = event.target.closest("[data-tab-target]");
  if (button) selectWorkspaceTab(button.dataset.tabTarget);
});

const workspaceTabsAreHorizontal = window.matchMedia("(max-width: 780px)");
const syncWorkspaceTabOrientation = () => $("#workspace-tabs").setAttribute(
  "aria-orientation", workspaceTabsAreHorizontal.matches ? "horizontal" : "vertical",
);
syncWorkspaceTabOrientation();
workspaceTabsAreHorizontal.addEventListener("change", syncWorkspaceTabOrientation);
$("#workspace-tabs").addEventListener("keydown", (event) => {
  const tabs = [...document.querySelectorAll(".workspace-tab:not([hidden])")];
  const current = tabs.indexOf(event.target);
  if (current < 0) return;
  const forward = workspaceTabsAreHorizontal.matches ? "ArrowRight" : "ArrowDown";
  const backward = workspaceTabsAreHorizontal.matches ? "ArrowLeft" : "ArrowUp";
  const next = { [forward]: (current + 1) % tabs.length, [backward]: (current - 1 + tabs.length) % tabs.length,
    Home: 0, End: tabs.length - 1 }[event.key];
  if (next === undefined) return;
  event.preventDefault();
  tabs[next].focus();
  selectWorkspaceTab(tabs[next].dataset.tabTarget);
});

$("#knowledge-documents-search").addEventListener("input", renderKnowledgeDocuments);
$("#knowledge-domain-filter").addEventListener("change", renderKnowledgeDocuments);
$("#knowledge-state-filter").addEventListener("change", renderKnowledgeDocuments);
$("#knowledge-documents-refresh").addEventListener("click", async () => {
  try { await refreshKnowledgeDocuments(); }
  catch (error) { $("#knowledge-documents-status").textContent = error.message; }
});
$("#knowledge-documents-list").addEventListener("click", async (event) => {
  const retryButton = event.target.closest("[data-retry-embedding]");
  if (retryButton) {
    const documentId = retryButton.dataset.retryEmbedding;
    retryButton.disabled = true;
    retryButton.textContent = "Retrying embedding…";
    try {
      const result = await api(`/api/admin/processing/${encodeURIComponent(documentId)}/retry-embedding`, {
        method: "POST",
      });
      await refreshKnowledgeDocuments();
      $("#knowledge-documents-status").textContent = `Embedding recovered · ${formatNumber(result.indexed_chunk_count)} passages indexed`;
    } catch (error) {
      $("#knowledge-documents-status").textContent = error.message;
      retryButton.disabled = false;
      retryButton.textContent = "Retry embedding";
    }
    return;
  }
  const button = event.target.closest("[data-knowledge-toggle]");
  if (!button) return;
  const active = button.dataset.active === "true";
  const documentId = button.dataset.knowledgeToggle;
  const action = active ? "Remove this source from AI retrieval? Its original file and parser output will be retained." : "Restore this source to AI retrieval?";
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

$("#knowledge-documents-list").addEventListener("submit", async (event) => {
  const form = event.target.closest(".knowledge-access-form");
  if (!form) return;
  event.preventDefault();
  const roles = [...form.querySelectorAll('input[name="allowed_roles"]:checked')].map((input) => input.value);
  const status = form.querySelector("[data-access-status]");
  const button = form.querySelector('button[type="submit"]');
  if (!roles.length) {
    status.textContent = "Select at least one role.";
    return;
  }
  button.disabled = true;
  status.textContent = "Saving…";
  try {
    await api(`/api/admin/knowledge-documents/${encodeURIComponent(form.dataset.documentId)}/access`, {
      method: "PATCH", body: JSON.stringify({allowed_roles: roles}),
    });
    await refreshKnowledgeDocuments();
  } catch (error) {
    status.textContent = error.message;
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
    const result = await api(`/api/admin/processing/${encodeURIComponent(documentId)}/tables?row_limit=100`);
    renderExtractedTables(result.tables, documentId);
  } catch (error) {
    $("#parsed-table-list").innerHTML = error.status === 404
      ? '<p class="loading-card">No structured tables were extracted from this document.</p>'
      : `<p class="loading-card">${escapeHtml(error.message)}</p>`;
  }
});

$("#ocr-test-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const button = $("#ocr-test-button");
  button.disabled = true;
  const parserEngine = form.elements.namedItem("parser_engine").value;
  const parserLabel = "Docling";
  $("#ocr-test-status").textContent = `Running ${parserLabel} with shared output cleanup…`;
  try {
    const result = await api("/api/upload-tests", {method:"POST", body:new FormData(form)});
    $("#ocr-test-status").textContent = `Saved isolated run ${result.run_id}: ${result.page_count} pages, ${result.element_count} parser elements, ${result.table_count} tables. No production document was created.`;
    await loadOcrTestRuns();
    await openOcrTestRun(result.run_id);
    form.reset();
    updateUploadTestParserSettings();
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
  $("#login-brand-sidebar").hidden = false;
  $("#user-badge").hidden = true;
  $("#logout-button").hidden = true;
  activeTab = "knowledge";
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

$(".agent-grid").addEventListener("click", (event) => {
  const card = event.target.closest("[data-agent-mode]");
  if (card) {
    $("#agent-mode").value = card.dataset.agentMode;
    $("#question").value = card.dataset.agentPrompt;
    $("#ask-form").requestSubmit();
  } else if (event.target.closest("[data-open-report]")) {
    $("#report-agent-form-section").hidden = false;
    $("#report-agent-template").focus();
  }
});

$("#ask-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = $("#ask-button");
  const question = $("#question").value.trim();
  if (!question) return;
  button.disabled = true;
  button.innerHTML = "<span>Working...</span>";
  const panel = $("#answer-panel");
  renderSkeletonAnswer(panel, "Routing your request to the right agent...");
  try {
    const data = await api("/api/agents/chat", { method: "POST", body: JSON.stringify({
      question, agent_mode: $("#agent-mode").value, retrieval_method: "translated_hybrid_rerank",
    }) });
    $("#connection-status").textContent = "Agent services connected";
    $(".status-dot").classList.add("connected");
    renderAgentResult(data);
  } catch (error) {
    panel.innerHTML = '<p class="error-message">' + escapeHtml(error.message) + '. Please check service configuration or connection.</p>';
  } finally {
    button.disabled = false;
    button.innerHTML = "<span>Ask agent</span>";
  }
});

$("#report-agent-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = $("#report-agent-submit");
  const status = $("#report-agent-status");
  button.disabled = true;
  status.textContent = "Generating report from authorized sources...";
  try {
    const response = await fetch("/api/agents/report", {
      method: "POST", body: new FormData(event.currentTarget), credentials: "same-origin",
      headers: { "ngrok-skip-browser-warning": "1" },
    });
    if (!response.ok) {
      let detail = "Report request failed (HTTP " + response.status + ")";
      try { detail = (await response.json()).detail || detail; } catch {}
      throw new Error(detail);
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "report" + ($("#report-agent-template").files[0]?.name.match(/\.[^.]+$/)?.[0] || ".docx");
    link.click();
    URL.revokeObjectURL(url);
    status.textContent = "Report generated and downloaded.";
  } catch (error) {
    status.textContent = error.message;
  } finally {
    button.disabled = false;
  }
});
$("#monitoring-refresh").addEventListener("click", refreshAgentMonitoring);

function updateUploadRoleSelection() {
  const selectedRoles = [...$("#upload-role-options").querySelectorAll('input[name="allowed_roles"]:checked')];
  const summary = $("#upload-role-selection");
  summary.textContent = selectedRoles.length
    ? `${selectedRoles.length} role${selectedRoles.length === 1 ? "" : "s"} can retrieve this document.`
    : "No roles selected yet. Select at least one role to allow document Q&A access.";
}

const MAX_UPLOAD_BYTES = 50 * 1024 * 1024;
const SUPPORTED_UPLOAD_EXTENSIONS = new Set([".pdf", ".docx", ".pptx", ".xlsx", ".csv", ".txt", ".md", ".png", ".jpg", ".jpeg", ".tif", ".tiff"]);

function validateUploadFile(file) {
  if (!file) return "Choose a document to upload.";
  const extension = "." + file.name.split(".").pop().toLocaleLowerCase();
  if (!SUPPORTED_UPLOAD_EXTENSIONS.has(extension)) return "This file type is not supported. Choose PDF, DOCX, PPTX, XLSX, CSV, TXT, MD, PNG, JPG or TIF.";
  if (file.size > MAX_UPLOAD_BYTES) return "The file is larger than the 50 MiB upload limit.";
  return "";
}

$("#upload-file").addEventListener("change", (event) => {
  const file = event.currentTarget.files[0];
  const title = $("#upload-title");
  if (file && title.dataset.userEdited !== "true") {
    title.value = file.name.replace(/\.[^.]+$/, "").replace(/[_-]+/g, " ").trim();
  }
  const error = validateUploadFile(file);
  $("#upload-file-info").textContent = error || file.name + " · " + (file.size / 1024 / 1024).toFixed(1) + " MiB. The original stays private; review OCR output in Document Processing.";
  $("#upload-file-info").setAttribute("role", error ? "alert" : "status");
});

const uploadDropzone = $("#upload-dropzone");
uploadDropzone.addEventListener("dragover", (event) => {
  event.preventDefault();
  if ($("#upload-form").getAttribute("aria-busy") === "true") return;
  uploadDropzone.classList.add("is-dragging");
});
uploadDropzone.addEventListener("dragleave", (event) => {
  if (!event.relatedTarget || !uploadDropzone.contains(event.relatedTarget)) {
    uploadDropzone.classList.remove("is-dragging");
  }
});
uploadDropzone.addEventListener("drop", (event) => {
  event.preventDefault();
  uploadDropzone.classList.remove("is-dragging");
  if ($("#upload-form").getAttribute("aria-busy") === "true") return;
  const files = event.dataTransfer?.files;
  if (!files?.length) return;
  if (files.length !== 1) {
    $("#upload-file").value = "";
    $("#upload-file-info").textContent = "Upload one file at a time.";
    $("#upload-file-info").setAttribute("role", "alert");
    return;
  }
  const input = $("#upload-file");
  input.files = files;
  input.dispatchEvent(new Event("change", { bubbles: true }));
});

$("#upload-title").addEventListener("input", (event) => {
  event.currentTarget.dataset.userEdited = "true";
});

$("#upload-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const parserHandoff = event.submitter?.dataset.uploadMode === "parser-handoff";
  const file = $("#upload-file").files[0];
  const roles = [...form.querySelectorAll('input[name="allowed_roles"]:checked')].map((input) => input.value);
  const fileError = validateUploadFile(file);
  if (fileError || !roles.length) {
    const status = $("#upload-status");
    $("#upload-status-wrap").hidden = false;
    $("#upload-progress").hidden = true;
    status.dataset.state = "error";
    status.textContent = fileError || "Select at least one role authorized to retrieve this document.";
    return;
  }
  const body = new FormData();
  body.append("file", file);
  for (const name of ["title"]) {
    const value = form.elements[name].value.trim();
    if (value) body.append(name, value);
  }
  body.append("document_type", "knowledge_document");
  body.append("domain", "general_knowledge");
  roles.forEach((role) => body.append("allowed_roles", role));
  const controls = [...form.querySelectorAll("input, select, textarea, button")];
  const controlsWereDisabled = controls.map((control) => control.disabled);
  controls.forEach((control) => { control.disabled = true; });
  form.setAttribute("aria-busy", "true");
  const status = $("#upload-status");
  const progress = $("#upload-progress");
  const elapsedLabel = $("#upload-elapsed");
  $("#upload-status-wrap").hidden = false;
  progress.hidden = false;
  elapsedLabel.hidden = false;
  const processingStartedAt = Date.now();
  const updateProcessingTime = () => {
    const elapsedSeconds = Math.floor((Date.now() - processingStartedAt) / 1000);
    elapsedLabel.textContent = "Elapsed: " + (elapsedSeconds < 60
      ? `${elapsedSeconds}s`
      : `${Math.floor(elapsedSeconds / 60)}m ${String(elapsedSeconds % 60).padStart(2, "0")}s`);
  };
  status.dataset.state = "processing";
  status.textContent = parserHandoff
    ? "Uploading, extracting and saving parser output. Tokenization and indexing are downstream. Keep this tab open."
    : "Uploading, extracting text/OCR, chunking and indexing. Keep this tab open.";
  updateProcessingTime();
  const processingTimer = window.setInterval(updateProcessingTime, 1000);
  let result;
  try {
    result = await api(parserHandoff ? "/api/documents/parser-handoff" : "/api/documents/upload", { method: "POST", body, headers: {} });
    const referenceStatus = parserHandoff
      ? " Parser output is saved in public for downstream tokenization and indexing; this document is not searchable yet."
      : " Indexed for document Q&A.";
    const pageSummary = result.page_count ? `${formatNumber(result.page_count)} pages` : "File processed";
    const extractionSummary = parserHandoff
      ? `${formatNumber(result.parser_chunk_count)} parser chunks · ${formatNumber(result.ocr_chunk_count)} OCR chunks · ${formatNumber(result.table_count)} tables · 0 indexed`
      : `${formatNumber(result.parser_chunk_count)} parser passages · ${formatNumber(result.indexed_chunk_count)} indexed passages · ${formatNumber(result.ocr_chunk_count)} OCR passages · ${formatNumber(result.table_count)} tables`;
    const uploadedTitle = form.elements.title.value || file.name;
    status.dataset.state = "success";
    progress.hidden = true;
    elapsedLabel.hidden = true;
    status.textContent = `Processed ${result.document_id}; status: ${result.processing_status}; ${pageSummary}; ${extractionSummary}.${referenceStatus}`;
    form.reset();
    $("#upload-title").dataset.userEdited = "false";
    updateUploadRoleSelection();
      $("#upload-file-info").textContent = "Choose one file. Scanned PDFs and images use OCR; Admins can review extracted text and tables in Document Processing.";
    $("#upload-file-info").setAttribute("role", "status");
    try {
      if (currentUser?.role === "admin") await refreshKnowledgeDocuments();
    } catch (error) {
      status.dataset.state = "warning";
      status.textContent = `The file was processed successfully as ${result.document_id}, but the admin document list could not refresh: ${error.message}`;
    }
    const parsedDocument = $("#parsed-document");
    if (currentUser?.role === "document_processing_owner") {
      const processingStatus = $("#processing-upload-status");
      processingStatus.dataset.state = status.dataset.state || "success";
      processingStatus.textContent = status.textContent;
      processingStatus.hidden = false;
      if (![...parsedDocument.options].some((option) => option.value === result.document_id)) {
        parsedDocument.add(new Option(`${uploadedTitle} · ${result.processing_status}`, result.document_id));
      }
      parsedDocument.value = result.document_id;
      selectWorkspaceTab("processing");
      $("#parsed-chunk-form").requestSubmit();
    } else {
      selectWorkspaceTab("upload");
    }
  } catch (error) {
    progress.hidden = true;
    elapsedLabel.hidden = true;
    status.dataset.state = result ? "warning" : "error";
    status.textContent = result
      ? `The file was processed successfully as ${result.document_id}, but the workspace could not refresh: ${error.message}`
      : error.message;
  } finally {
    window.clearInterval(processingTimer);
    controls.forEach((control, index) => { control.disabled = controlsWereDisabled[index]; });
    form.removeAttribute("aria-busy");
  }
});

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
