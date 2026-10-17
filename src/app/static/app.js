const $ = (selector) => document.querySelector(selector);
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

function syntheticPolicySourcePageUrl(source) {
  if (source.synthetic_company_policy !== true || !source.document_id) return "";
  const page = Number(source.page_number);
  return `/api/documents/${encodeURIComponent(source.document_id)}/source${Number.isInteger(page) && page > 0 ? `#page=${page}` : ""}`;
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

function syncWorkspaceTabs(user = currentUser) {
  const isTester = user?.role === "tester";
  const isAdmin = user?.role === "admin";
  const canAskDocuments = !isTester && user?.role !== "document_uploader";
  const canViewAnalytics = ["operations", "finance_analyst", "sustainability_analyst", "executive", "admin"].includes(user?.role);
  const canUpload = ["document_uploader", "admin"].includes(user?.role);
  const available = {
    knowledge: canAskDocuments,
    analytics: canViewAnalytics,
    upload: canUpload,
    processing: isAdmin,
    "ocr-lab": isTester || isAdmin,
    "knowledge-management": isAdmin,
    access: isAdmin,
    monitoring: isAdmin,
  };
  document.querySelectorAll(".workspace-tab").forEach((button) => {
    button.hidden = !available[button.dataset.tabTarget];
  });
  if (!available[activeTab]) {
    activeTab = isTester ? "ocr-lab" : available.knowledge ? "knowledge" : available.upload ? "upload" : "analytics";
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
  const commerceLabels = {
    inventory_allocation: "Inventory allocation",
    promotion_planning: "Promotion planning",
    nationwide_logistics: "Nationwide logistics",
  };
  const referenceLabels = {
    management_cookbook_reference: "Management method",
    company_practice_reference: "Company practice",
    company_policy_reference: "External policy · stated scope only",
    platform_operating_rule: "Platform operating rule",
  };
  const companies = new Set(data.documents.map((doc) => doc.company).filter(Boolean));
  $("#company-name").textContent = companies.size || 0;
  $("#document-count").textContent = formatNumber(data.document_count);
  $("#chunk-count").textContent = formatNumber(data.chunk_count);
  const inFlight = data.documents.filter((doc) => !["ready", "parsed"].includes(doc.processing_status)).length;
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
        <span>${escapeHtml(doc.source_publisher || doc.company || "Unknown publisher")} · ${escapeHtml(doc.format || "File")} · ${formatNumber(doc.chunk_count)} passages</span>
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
  renderKnowledgeDocuments();
  renderParsedChunkInspector(knowledgeDocuments);
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
    const tesseractConfig = selected.tesseract_config || {};
    const parserSettings = engine === "mineru"
      ? `MinerU · force OCR ${selected.mineru_force_ocr ? "on" : "off"} · pages ${selected.mineru_page_range || "all"}`
      : engine === "docling"
      ? `Docling · ${selected.docling_device || "cpu"} · OCR ${selected.docling_ocr ? "on" : "off"} (${selected.docling_ocr_language || "vi"}) · tables ${selected.docling_table_structure ? "on" : "off"} · ${selected.docling_num_threads || 4} threads`
      : engine === "pp-structurev3"
      ? `PP-StructureV3 · ${selected.paddle_device || "cpu"} · ${Math.round((selected.paddle_render_scale ?? 1.5) * 72)} DPI · formulas ${selected.paddle_formula_recognition ? "on" : "off"} · charts ${selected.paddle_chart_recognition ? "on" : "off"}`
      : engine === "built_in"
        ? `Built-in · PSM ${selected.tesseract_psm} · ${Math.round((selected.ocr_render_scale ?? 1.5) * 72)} DPI · threshold ${tesseractConfig.thresholding_method ?? 0} · table recognition ${tesseractConfig.textord_tablefind_recognize_tables ? "on" : "off"} · ${selected.tessdata_variant || "system"} data`
        : "Parser settings unavailable";
    const settings = config.layout_detector === "doclayout-yolo"
      ? `${parserSettings} · YOLO overlay ${config.layout_image_size}px · confidence ${config.layout_confidence_threshold}`
      : parserSettings;
    const embeddingSummary = run.embedding_status === "not_run"
      ? "embedding skipped"
      : `historical embedding ${run.embedding_status}`;
    const previewSummary = run.page_count ? `${formatNumber(run.page_count)} page previews` : "no page previews";
    const processingSummary = `processing ${formatDuration(run.runtime_info?.processing_time_ms)}`;
    return `<button type="button" class="ocr-run-button" data-ocr-run-id="${escapeHtml(run.run_id)}"><strong>${escapeHtml(run.source_filename)}</strong><span>${escapeHtml(new Date(run.created_at).toLocaleString())} · ${processingSummary} · ${previewSummary} · ${formatNumber(run.chunk_count)} parser chunks · ${embeddingSummary} · ${formatNumber(run.table_count)} tables · ${escapeHtml(settings)}</span></button>`;
  }).join("") || '<p class="loading-card">No upload tests yet. Upload a supported document above to create one.</p>';
}

function renderOcrTestDetails(run) {
  const layoutPages = run.runtime_info?.layout_detections || [];
  const allPages = [...new Set([
    ...run.pages,
    ...layoutPages.map((page) => page.page_number == null ? NaN : Number(page.page_number)).filter(Number.isFinite),
    ...run.chunks.map((chunk) => chunk.metadata?.page_number == null ? NaN : Number(chunk.metadata.page_number)).filter(Number.isFinite),
    ...run.tables.map((table) => table.page_number == null ? NaN : Number(table.page_number)).filter(Number.isFinite),
  ])].sort((a, b) => a - b);
  const pageContent = allPages.map((pageNumber, pageIndex) => {
    const layoutPage = layoutPages.find((page) => Number(page.page_number) === pageNumber);
    const layoutRegions = layoutPage?.regions || [];
    const layoutOverlay = layoutPage ? `<div class="ocr-layout-preview">
      <img loading="lazy" alt="Rendered source page ${formatNumber(pageNumber)}" src="/api/upload-tests/${encodeURIComponent(run.run_id)}/pages/${pageNumber}/preview">
      <svg viewBox="0 0 ${Number(layoutPage.width)} ${Number(layoutPage.height)}" role="img" aria-label="${formatNumber(layoutRegions.length)} DocLayout-YOLO regions detected">
        ${layoutRegions.map((region) => {
          const [x1, y1, x2, y2] = region.bbox.map(Number);
          const x = x1 * Number(layoutPage.width), y = y1 * Number(layoutPage.height);
          const width = Math.max(0, (x2 - x1) * Number(layoutPage.width));
          const height = Math.max(0, (y2 - y1) * Number(layoutPage.height));
          const label = `${region.class} ${Number(region.score).toFixed(2)}`;
          return `<g class="layout-region layout-region-${escapeHtml(region.class)}"><rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${width.toFixed(1)}" height="${height.toFixed(1)}"></rect><text x="${x.toFixed(1)}" y="${Math.max(12, y - 3).toFixed(1)}">${escapeHtml(label)}</text></g>`;
        }).join("")}
      </svg></div>` : `<img loading="lazy" alt="Rendered source page ${formatNumber(pageNumber)}" src="/api/upload-tests/${encodeURIComponent(run.run_id)}/pages/${pageNumber}/preview">`;
    const chunks = run.chunks.filter((chunk) => Number(chunk.metadata?.page_number) === pageNumber);
    const tables = run.tables.filter((table) => Number(table.page_number) === pageNumber);
    const ocrDiagnostics = chunks.flatMap((chunk) => chunk.metadata?.ocr_diagnostics || []);
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
      <summary>Page ${formatNumber(pageNumber)} · ${formatNumber(chunks.length)} parser chunks · ${formatNumber(tables.length)} tables</summary>
      <div class="ocr-test-page-content">
      <section class="ocr-test-raw"><h4>Raw page</h4>${layoutOverlay}${layoutPage ? `<p class="corpus-note">DocLayout-YOLO · ${formatNumber(layoutRegions.length)} regions at ${formatNumber(run.processor_config?.layout_image_size)}px, threshold ${escapeHtml(run.processor_config?.layout_confidence_threshold)}</p>` : ""}</section>
      <section class="ocr-test-extracted"><h4>Extracted output</h4>
        ${renderOcrDiagnostics(ocrDiagnostics)}
        <details class="ocr-test-chunks"><summary>Parser output · ${formatNumber(chunks.length)} chunks</summary>${chunks.map((chunk) => `<article class="ocr-test-chunk"><div class="candidate-heading"><strong>Chunk ${formatNumber(chunk.chunk_index + 1)}</strong><span>${formatNumber(chunk.metadata?.actual_char_count ?? chunk.content.length)} chars actual · ${formatNumber(chunk.metadata?.chunk_size_chars ?? 0)} char limit · ${escapeHtml(chunk.metadata?.text_extraction_method || "parser output")} · ${escapeHtml(chunk.metadata?.layout_type || "text")}</span></div><pre>${escapeHtml(chunk.content)}</pre><details class="candidate-source"><summary>Chunk metadata</summary><pre>${escapeHtml(JSON.stringify(chunk.metadata, null, 2))}</pre></details></article>`).join("") || '<p class="ocr-test-empty">No parser chunks on this page.</p>'}</details>
        <h4 class="ocr-test-table-heading">Extracted tables</h4>
        ${tablesHtml || '<p class="ocr-test-empty">No structured table detected on this page.</p>'}
      </section>
      </div>
    </details>`;
  }).join("");
  const unpagedChunks = run.chunks.filter((chunk) => chunk.metadata?.page_number == null);
  const unpagedTables = run.tables.filter((table) => table.page_number == null);
  const unpagedOutput = unpagedChunks.length || unpagedTables.length
    ? `<section class="ocr-test-page">
        <h3>Document content · no page previews</h3>
        <section class="ocr-test-extracted"><h4>Extracted output · ${formatNumber(unpagedChunks.length)} shared chunks</h4>
          ${unpagedChunks.map((chunk) => `<article class="ocr-test-chunk"><div class="candidate-heading"><strong>Chunk ${formatNumber(chunk.chunk_index + 1)}</strong><span>${formatNumber(chunk.metadata?.actual_char_count ?? chunk.content.length)} chars · ${escapeHtml(chunk.metadata?.text_extraction_method || "parser output")}</span></div><pre>${escapeHtml(chunk.content)}</pre><details class="candidate-source"><summary>Chunk metadata</summary><pre>${escapeHtml(JSON.stringify(chunk.metadata, null, 2))}</pre></details></article>`).join("") || '<p class="ocr-test-empty">No parser chunks.</p>'}
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
    <div class="candidate-heading"><strong>${escapeHtml(run.source_filename)}</strong><span>${processingSummary} · ${run.page_count ? `${formatNumber(run.page_count)} page previews` : "No page previews"} · ${formatNumber(run.chunks.length)} parser chunks · ${formatNumber(run.tables.length)} tables</span></div>
    <p class="corpus-note">SHA-256: <code>${escapeHtml(run.source_sha256)}</code></p>
    <p class="corpus-note">Tokenization and embedding are downstream stages and are not run by Upload Test.</p>
    <details class="candidate-source"><summary>Parser configuration and versions</summary><pre>${escapeHtml(JSON.stringify({processor_config:run.processor_config,runtime_info:{...run.runtime_info,layout_detections:undefined}},null,2))}</pre></details>
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
  const max = unit === "%" ? Math.max(100, ...values) : Math.max(1, ...values) * 1.08;
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
  const activeView = document.querySelector('[data-commerce-view][aria-selected="true"]')?.dataset.commerceView || "inventory";
  const yearSelect = $("#commerce-year-filter");
  const selectedYear = yearSelect.value;
  const domainYears = {
    inventory: (data.inventory_by_year || []).map((row) => row.year),
    promotions: [
      ...(data.promotions_by_year || []).map((row) => row.year),
      ...(data.promotions_by_campaign || []).map((row) => row.year),
    ],
    logistics: (data.logistics_by_year_region || []).map((row) => row.year),
  };
  const years = [...new Set((domainYears[activeView] || []).filter(Number.isFinite))].sort((a, b) => a - b);
  yearSelect.innerHTML = '<option value="">All available years</option>' + years.map((year) =>
    `<option value="${year}">${year}</option>`).join("");
  yearSelect.value = years.includes(Number(selectedYear)) ? selectedYear : "";
  const year = yearSelect.value ? Number(yearSelect.value) : null;
  const byYear = (rows) => rows.filter((row) => year == null || Number(row.year) === year);
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
    const fillRate = Number(latest.avg_fill_rate);
    renderCommerceCards([
      ["SKU snapshots", formatCommerceValue(latest.sku_snapshots), inventoryPeriod],
      ["Average units on hand", formatCommerceValue(latest.avg_stock_on_hand), inventoryPeriod],
      ["Average fill rate", Number.isFinite(fillRate) ? `${(fillRate * 100).toFixed(2)}%` : "—", "Mean of source fill_rate values"],
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
      ["Regional-year median range", medianRange, "Range across displayed region/year aggregates, not individual shipments"],
      ["Weighted average shipping fee", formatCommerceValue(weighted("avg_shipping_fee")), "Dataset units; currency not declared"],
    ], "Descriptive regional summary; no carrier or route-level data");
  }
  const inventoryRows = byYear(data.inventory_by_year || []);
  renderCommerceChart("#commerce-inventory-chart", inventoryRows, [
    { label: "Stockout snapshots", color: "#c54845", matches: () => true, value: (row) => row.stockout_snapshots },
    { label: "Overstock snapshots", color: "#3972bd", matches: () => true, value: (row) => row.overstock_snapshots },
  ], "snapshot count", "line", yearLabel);
  renderCommerceChart("#commerce-inventory-fill-rate-chart", inventoryRows, [
    { label: "Average fill rate", color: "#48a17c", matches: () => true, value: (row) => Number(row.avg_fill_rate) * 100 },
  ], "%", "line", yearLabel);
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
    ["avg_fill_rate", "Average fill rate", (value) => Number.isFinite(Number(value)) ? `${(Number(value) * 100).toFixed(2)}%` : "—"],
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

function selectedCommerceDomain() {
  const domainByView = {
    inventory: "inventory_allocation",
    promotions: "promotion_planning",
    logistics: "nationwide_logistics",
  };
  const activeView = document.querySelector('[data-commerce-view][aria-selected="true"]')?.dataset.commerceView;
  return domainByView[activeView] || "inventory_allocation";
}

document.querySelectorAll("[data-commerce-view]").forEach((button) => {
  button.addEventListener("click", () => {
    $("#commerce-dashboard-status").hidden = true;
    document.querySelectorAll("[data-commerce-view]").forEach((tab) => {
      const selected = tab === button;
      tab.setAttribute("aria-selected", String(selected));
      $("#commerce-view-" + tab.dataset.commerceView).hidden = !selected;
    });
    renderDecisionDomainQuestions(selectedCommerceDomain());
    renderCommerceDashboard();
    loadCommerceDashboardForActiveView();
  });
});
$("#commerce-campaign-details").addEventListener("toggle", (event) => {
  if (event.currentTarget.open) loadCommerceCampaigns();
});
const commerceTabList = $(".commerce-dashboard-tabs");
const commerceTabsAreHorizontal = window.matchMedia("(max-width: 640px)");
const syncCommerceTabOrientation = () => commerceTabList.setAttribute(
  "aria-orientation", commerceTabsAreHorizontal.matches ? "horizontal" : "vertical",
);
syncCommerceTabOrientation();
commerceTabsAreHorizontal.addEventListener("change", syncCommerceTabOrientation);
commerceTabList.addEventListener("keydown", (event) => {
  const tabs = [...document.querySelectorAll("[data-commerce-view]")];
  const current = tabs.indexOf(event.target);
  const forward = commerceTabsAreHorizontal.matches ? "ArrowRight" : "ArrowDown";
  const backward = commerceTabsAreHorizontal.matches ? "ArrowLeft" : "ArrowUp";
  const next = { [forward]: (current + 1) % tabs.length, [backward]: (current - 1 + tabs.length) % tabs.length,
    Home: 0, End: tabs.length - 1 }[event.key];
  if (current < 0 || next === undefined) return;
  event.preventDefault();
  tabs[next].focus();
  tabs[next].click();
});
$("#commerce-year-filter").addEventListener("change", () => renderCommerceDashboard());
function selectedQuestionSuggestionDomain() {
  return $("#business-question-domain").value || selectedCommerceDomain();
}

$("#business-question-domain").addEventListener("change", () => {
  renderDecisionDomainQuestions(selectedQuestionSuggestionDomain());
});

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
    `<button type="button" data-decision-domain="${escapeHtml(domain)}" data-decision-question="${escapeHtml(question)}"><strong>${escapeHtml(title)}</strong><small>Select to load this question and its domain into the editor.</small></button>`
  ).join("");
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
  panel.innerHTML = `
    <div class="answer-header-wrap">
      <div class="answer-heading">
        <span class="answer-mark">${usedEvidenceFallback ? "EV" : "AI"}</span>
        <div><span class="eyebrow">GROUNDED RESPONSE</span><h3>${usedEvidenceFallback ? "Evidence fallback" : "Synthesized answer"}</h3></div>
      </div>
      <div class="answer-actions-bar">
        <button type="button" class="action-btn" id="copy-answer-btn" title="Copy response text">Copy</button>
      </div>
    </div>
    ${domainNote}
    ${decisionModeNote}
    ${referenceRetrievalNote}
    ${questionSqlFallbackNote}
    ${tokenUsage}
    <div class="answer-text">${renderAnswerBody(data.answer)}</div>
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
    $("#login-brand-sidebar").hidden = false;
    throw new Error("Sign in to continue");
  }
  const data = await response.json();
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
  $("#login-brand-sidebar").hidden = true;
  $("#workspace").hidden = false;
  $("#analytics-section").hidden = true;
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
  if (["admin", "document_uploader"].includes(user.role)) {
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
            updateUploadPlanSummary();
          });
        });
        updateUploadRoleSelection();
        syncUploadReferenceFields();
        $("#upload-button").disabled = false;
        $("#parser-handoff-button").disabled = false;
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
    const data = await api("/api/dashboard");
    renderCorpus(data);
    if (["operations", "finance_analyst", "sustainability_analyst", "executive", "admin"].includes(user.role)) {
      $("#commerce-dashboard").hidden = false;
      renderDecisionDomainQuestions(selectedQuestionSuggestionDomain());
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
  const useYoloOverlay = form.elements.namedItem("layout_detector").value === "doclayout-yolo";
  const parserLabel = parserEngine === "pp-structurev3"
    ? "PP-StructureV3"
    : parserEngine === "mineru" ? "MinerU (local)"
    : parserEngine === "docling" ? "Docling" : "Built-in";
  $("#ocr-test-status").textContent = `Running ${parserLabel}, then shared cleanup and parser chunking. Tokenization and embedding are downstream${useYoloOverlay ? " (plus diagnostic YOLO overlay)" : ""}…`;
  try {
    const result = await api("/api/upload-tests", {method:"POST", body:new FormData(form)});
    $("#ocr-test-status").textContent = `Saved isolated run ${result.run_id}: ${result.page_count} pages, ${result.chunk_count} parser chunks, ${result.table_count} tables. No production document was created.`;
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
  const businessDecisionDomain = decisionSuggestions
    ? selectedCommerceDomain()
    : $("#business-question-domain").value || null;
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
      business_decision_domain: businessDecisionDomain,
      commerce_decision_support: true,
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
    $("#business-question-domain").value = questionPrompt.dataset.decisionDomain;
    $("#business-question").focus();
    return;
  }
  if (!event.target.closest("[data-decision-suggestions]")) return;
  decisionSuggestionsPending = true;
  $("#business-question-form").requestSubmit();
});

$("#analytics-section").addEventListener("click", (event) => {
  const link = event.target.closest("[data-open-tab]");
  if (link) selectWorkspaceTab(link.dataset.openTab);
});

$("#monitoring-refresh").addEventListener("click", refreshAgentMonitoring);

function syncUploadReferenceFields() {
  const form = $("#upload-form");
  const isReference = form.elements.commerce_decision_support.checked;
  if (!isReference) {
    form.elements.reference_type.value = "";
    form.querySelectorAll('input[name="knowledge_domains"]').forEach((input) => { input.checked = false; });
    form.elements.synthetic_company_policy.checked = false;
    form.elements.source_publisher.value = "";
    form.elements.reference_applicability.value = "";
  } else if (form.elements.synthetic_company_policy.checked && form.elements.reference_type.value !== "company_policy_reference") {
    form.elements.synthetic_company_policy.checked = false;
    form.elements.source_publisher.value = "";
    form.elements.reference_applicability.value = "";
  }
  $("#upload-reference-fields").hidden = !isReference;
  $("#upload-commerce-details").hidden = !isReference;
  $("#upload-commerce-details").open = isReference;
  $("#upload-synthetic-policy-option").hidden = !isReference || currentUser?.role !== "admin";
  form.elements.reference_type.required = isReference;
  form.elements.source_publisher.required = isReference;
  form.elements.reference_applicability.required = isReference;
  updateUploadPlanSummary();
}

function updateUploadRoleSelection() {
  const selectedRoles = [...$("#upload-role-options").querySelectorAll('input[name="allowed_roles"]:checked')];
  const summary = $("#upload-role-selection");
  summary.textContent = selectedRoles.length
    ? `${selectedRoles.length} role${selectedRoles.length === 1 ? "" : "s"} can retrieve this document.`
    : "No roles selected yet. Select at least one role to allow document Q&A access.";
}

function updateUploadPlanSummary() {
  const form = $("#upload-form");
  const referenceEnabled = form.elements.commerce_decision_support.checked;
  const title = form.elements.title.value.trim() || $("#upload-file").files[0]?.name || "Selected file";
  const roles = [...form.querySelectorAll('input[name="allowed_roles"]:checked')]
    .map((input) => input.closest("label")?.querySelector("strong")?.textContent.trim())
    .filter(Boolean);
  const lines = [
    `Document Q&A: ${title} can be fully indexed, or saved as parser output for downstream processing.`,
    `Access: ${roles.length ? roles.join(", ") : "select at least one role above"}.`,
  ];
  if (referenceEnabled) {
    const sourceType = form.elements.reference_type.selectedOptions[0]?.textContent.trim();
    const domains = [...form.querySelectorAll('input[name="knowledge_domains"]:checked')]
      .map((input) => input.closest("label")?.querySelector("strong")?.textContent.trim())
      .filter(Boolean);
    const missing = [
      !sourceType || form.elements.reference_type.value === "" ? "source type" : "",
      !form.elements.source_publisher.value.trim() ? "publisher" : "",
      !form.elements.reference_applicability.value.trim() ? "scope" : "",
      domains.length ? "" : "decision domain",
    ].filter(Boolean);
    lines.push(`Decision support: ${sourceType && form.elements.reference_type.value ? sourceType : "Commerce reference"}${domains.length ? ` · ${domains.join(", ")}` : ""}.`);
    if (missing.length) lines.push(`Complete: ${missing.join(", ")}.`);
  } else {
    lines.push("Decision support: off; this file is for document Q&A only.");
  }
  lines.push("Commerce dashboard data: unchanged.");
  $("#upload-plan-summary").textContent = lines.join("\n");
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
  updateUploadPlanSummary();
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
  updateUploadPlanSummary();
});

$("#upload-commerce-reference").addEventListener("change", syncUploadReferenceFields);
$("#upload-reference-type").addEventListener("change", syncUploadReferenceFields);
$("#upload-reference-fields").addEventListener("input", updateUploadPlanSummary);
$("#upload-reference-fields").addEventListener("change", updateUploadPlanSummary);
syncUploadReferenceFields();

$("#upload-synthetic-policy").addEventListener("change", (event) => {
  const form = $("#upload-form");
  if (event.currentTarget.checked) {
    form.elements.commerce_decision_support.checked = true;
    form.elements.reference_type.value = "company_policy_reference";
    form.elements.source_publisher.value = "Commerce Demo (fictional organization)";
    form.elements.reference_applicability.value = "Fictional Commerce Demo only; not a policy of a real company.";
  } else {
    form.elements.reference_type.value = "";
    form.elements.source_publisher.value = "";
    form.elements.reference_applicability.value = "";
  }
  syncUploadReferenceFields();
});

$("#upload-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const parserHandoff = event.submitter?.dataset.uploadMode === "parser-handoff";
  const file = $("#upload-file").files[0];
  const roles = [...form.querySelectorAll('input[name="allowed_roles"]:checked')].map((input) => input.value);
  const knowledgeDomains = [...form.querySelectorAll('input[name="knowledge_domains"]:checked')].map((input) => input.value);
  const knowledgeUse = form.elements.commerce_decision_support.checked ? "commerce" : "general";
  const referenceType = form.elements.reference_type.value;
  const publisher = form.elements.source_publisher.value.trim();
  const applicability = form.elements.reference_applicability.value.trim();
  const syntheticPolicy = form.elements.synthetic_company_policy.checked;
  const fileError = validateUploadFile(file);
  if (fileError || !roles.length) {
    const status = $("#upload-status");
    $("#upload-status-wrap").hidden = false;
    $("#upload-progress").hidden = true;
    status.dataset.state = "error";
    status.textContent = fileError || "Select at least one role authorized to retrieve this document.";
    return;
  }
  if (knowledgeUse === "commerce" && (!referenceType || !knowledgeDomains.length || !publisher || !applicability)) {
    const status = $("#upload-status");
    $("#upload-status-wrap").hidden = false;
    $("#upload-progress").hidden = true;
    status.dataset.state = "error";
    status.textContent = "Commerce references need a publisher, reference type, applicability scope, and at least one decision domain.";
    return;
  }
  if (syntheticPolicy && referenceType !== "company_policy_reference") {
    const status = $("#upload-status");
    $("#upload-status-wrap").hidden = false;
    $("#upload-progress").hidden = true;
    status.dataset.state = "error";
    status.textContent = "A synthetic Commerce Demo document must be classified as a company policy.";
    return;
  }
  const body = new FormData();
  body.append("file", file);
  for (const name of ["title", "source_publisher", "reference_type", "reference_applicability", "fiscal_year", "source_url", "ocr_language"]) {
    const value = form.elements[name].value.trim();
    if (value) body.append(name, value);
  }
  body.append("document_type", knowledgeUse === "commerce" ? referenceType : "knowledge_document");
  body.append("domain", knowledgeUse === "commerce"
    ? knowledgeDomains.length === 1 ? knowledgeDomains[0] : "commerce_operations"
    : "general_knowledge");
  body.append("synthetic_company_policy", syntheticPolicy ? "true" : "false");
  knowledgeDomains.forEach((domain) => body.append("knowledge_domains", domain));
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
      : knowledgeUse === "commerce"
      ? syntheticPolicy
        ? ` Indexed as synthetic demo guidance for ${knowledgeDomains.join(", ")} (scope: ${applicability}); dashboard SQL is unchanged.`
        : ` Indexed as ${referenceType} for ${knowledgeDomains.join(", ")} (scope: ${applicability}); dashboard SQL is unchanged.`
      : " Indexed for document Q&A; Commerce dashboard SQL is unchanged.";
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
    syncUploadReferenceFields();
    $("#upload-file-info").textContent = "Choose one file. Scanned PDFs and images use OCR; Admins can review extracted text and tables in Document Processing.";
    $("#upload-file-info").setAttribute("role", "status");
    try {
      const workspace = await api("/api/dashboard");
      renderCorpus(workspace);
      if (currentUser?.role === "admin") await refreshKnowledgeDocuments();
    } catch (error) {
      status.dataset.state = "warning";
      status.textContent = `The file was processed successfully as ${result.document_id}, but the corpus overview could not refresh: ${error.message}`;
    }
    const parsedDocument = $("#parsed-document");
    if (currentUser?.role === "admin") {
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
