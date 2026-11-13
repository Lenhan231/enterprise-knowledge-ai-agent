const $ = (selector) => document.querySelector(selector);
let activeTab = "general-chat";
let currentUser = null;
let knowledgeDocuments = [];
let activeKnowledgeReview = null;
let invoiceReviewItems = [];
let activeInvoiceReview = null;
let invoiceReviewPage = 1;
const INVOICE_REVIEW_PAGE_SIZE = 8;
const invoiceReviewEvidenceCache = new Map();
const invoiceReviewSourceUrlCache = new Map();
const invoiceReviewSourceRequests = new Map();
const INVOICE_REVIEW_SOURCE_CACHE_SIZE = 4;
const INVOICE_REVIEW_EVIDENCE_CACHE_SIZE = 12;
let invoiceProgressGeneration = 0;
let agentConversationId = crypto.randomUUID();
let reportConversationId = crypto.randomUUID();
let sessionTurns = [];
let generalConversationId = crypto.randomUUID();
let generalTurns = [];
let sessionGeneration = 0;
let sessionSubject = null;
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
  // Rows settle in only while a tab is opening, not when a filter or selection re-renders the list.
  const panel = $(`#tab-${name}`);
  if (panel) {
    clearTimeout(panel.freshTimer);
    panel.classList.add("is-fresh");
    panel.freshTimer = setTimeout(() => panel.classList.remove("is-fresh"), 2500);
    panel.querySelectorAll(".monitoring-stat strong").forEach(countUp);
  }
  $("#workspace-main").classList.toggle("invoice-review-active", name === "invoice-review");
  const isKnowledgeTab = name === "knowledge";
  $(".intro").hidden = !isKnowledgeTab;
  $(".agent-overview").hidden = !isKnowledgeTab
    || ["document_processing_owner", "document_uploader"].includes(currentUser?.role);
  $(".stats").hidden = !isKnowledgeTab || currentUser?.role === "document_processing_owner";
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
    // General Chat is the one chat (with Route to); the Reports tab (id "knowledge") keeps the report generator; its old chat box stays hidden.
    knowledge: canAskDocuments,
    "general-chat": canAskDocuments,
    upload: canUpload,
    "invoice-review": canUpload,
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
    activeTab = isProcessingOwner ? "processing" : available["general-chat"] ? "general-chat" : available.upload ? "upload" : "general-chat";
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
  if (data.document_count) $("#chat-library-head").innerHTML = `<strong>${formatNumber(data.document_count)} documents</strong> and the sales data are ready to ask. Try one of these:`;
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

function renderKnowledgeProcessingReview(doc) {
  if (activeKnowledgeReview?.status === "loading") {
    return '<section class="knowledge-output-review"><p class="corpus-note">Loading parser evidence…</p></section>';
  }
  if (activeKnowledgeReview?.error) {
    return `<section class="knowledge-output-review"><p class="error-message">${escapeHtml(activeKnowledgeReview.error)}</p></section>`;
  }

  const output = activeKnowledgeReview?.output;
  if (!output) return "";
  const sourceUrl = doc.source_type === "user_upload"
    ? uploadedSourcePageUrl(doc.document_id)
    : doc.synthetic_company_policy
      ? `/api/admin/knowledge-documents/${encodeURIComponent(doc.document_id)}/source`
      : "";
  const format = String(doc.format || "").toLowerCase();
  const sourcePreview = format === "pdf"
    ? `<iframe class="knowledge-output-source" title="${escapeHtml(doc.title)} source" data-api-src="${escapeHtml(sourceUrl)}"></iframe>`
    : ["png", "jpg", "jpeg", "tif", "tiff"].includes(format)
      ? `<img class="knowledge-output-image" src="${escapeHtml(sourceUrl)}" alt="Source file: ${escapeHtml(doc.title)}">`
      : `<p class="corpus-note">Inline preview is unavailable for ${escapeHtml(format.toUpperCase() || "this format")} files. <a href="${escapeHtml(sourceUrl)}" target="_blank" rel="noopener noreferrer">Open original file</a></p>`;
  const elements = Array.isArray(output.elements) ? output.elements : [];
  const tables = Array.isArray(output.tables) ? output.tables : [];
  const elementList = elements.map((element) => {
    const metadata = element.metadata || {};
    const page = metadata.page_number ?? element.page_number ?? "?";
    const type = metadata.element_type || metadata.layout_type || element.element_type || "text";
    const content = element.text ?? element.content ?? (element.table_ref != null ? `Table reference ${element.table_ref}` : "No text content");
    return `<details class="knowledge-output-element">
      <summary>Page ${escapeHtml(page)} · ${escapeHtml(type)} · ${formatNumber(String(content).length)} chars</summary>
      <pre>${escapeHtml(content)}</pre>
      <details class="knowledge-output-metadata"><summary>Element metadata</summary><pre>${escapeHtml(JSON.stringify(metadata, null, 2))}</pre></details>
    </details>`;
  }).join("");
  const tableList = tables.map((table, index) => {
    const rows = Array.isArray(table.rows) ? table.rows : [];
    const columns = Array.isArray(table.columns) ? table.columns : (rows[0] && !Array.isArray(rows[0]) ? Object.keys(rows[0]) : []);
    const header = columns.map((column) => `<th>${escapeHtml(column)}</th>`).join("");
    const body = rows.map((row) => `<tr>${columns.map((column, cellIndex) => `<td>${escapeHtml(Array.isArray(row) ? row[cellIndex] : row?.[column])}</td>`).join("")}</tr>`).join("");
    const page = table.metadata?.page_number ?? table.page_number ?? "?";
    return `<details class="knowledge-output-table"><summary>Table ${index + 1} · Page ${escapeHtml(page)} · ${formatNumber(rows.length)} rows</summary>
      <div class="knowledge-output-table-scroll"><table><thead><tr>${header}</tr></thead><tbody>${body}</tbody></table></div>
    </details>`;
  }).join("");

  return `<section class="knowledge-output-review" aria-label="Parser output review">
    <header><div><strong>Parser output</strong><span>${escapeHtml(output.pipeline_id || output.metadata?.pipeline_id || "Parser")} · ${formatNumber(elements.length)} elements · ${formatNumber(tables.length)} tables</span></div>
      <button type="button" class="secondary-button" data-close-knowledge-review>Close review</button></header>
    <div class="knowledge-output-columns"><div class="knowledge-output-source-pane">${sourcePreview}</div>
      <div class="knowledge-output-evidence"><h3>Elements</h3>${elementList || '<p class="corpus-note">No parser elements were saved.</p>'}
        <h3>Tables</h3>${tableList || '<p class="corpus-note">No tables were extracted.</p>'}</div></div>
  </section>`;
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
    const domainLabel = (key) => $(`#knowledge-domain-filter option[value="${CSS.escape(key)}"]`)?.textContent || displayName({}, key);
    const domains = (doc.knowledge_domains || []).map(domainLabel).join(", ") || "General";
    const retrievable = knowledgeDocumentIsRetrievable(doc);
    const state = retrievable ? ["ok", "Available to AI"] : doc.knowledge_base_active
      ? doc.processing_status === "failed" ? ["warn", "Processing failed"] : doc.processing_status === "ready" ? ["warn", "No passages yet"] : ["warn is-live", "Still processing"]
      : ["off", "Removed from AI retrieval"];
    const roles = (doc.allowed_roles || []).map((role) => displayName(ROLE_NAMES, role)).join(", ") || "No roles";
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
    const reviewOpen = activeKnowledgeReview?.document_id === doc.document_id;
    return `<div class="knowledge-document-entry"><article class="knowledge-document-row ${doc.knowledge_base_active ? "" : "is-removed"}">
      <div class="knowledge-document-copy"><strong>${escapeHtml(doc.title)}</strong>
        <span class="knowledge-doc-badges"><span class="knowledge-state is-${state[0]}">${escapeHtml(state[1])}</span>${sourceKind === "Knowledge source" ? "" : `<span class="knowledge-source-kind ${doc.synthetic_company_policy ? "is-synthetic" : ""}">${escapeHtml(sourceKind)}</span>`}</span>
        <span>${escapeHtml(doc.source_publisher || "Unknown publisher")} · ${escapeHtml(doc.format || "File")} · ${formatNumber(doc.chunk_count)} passages · ${escapeHtml(domains)}</span>
        <small><code>${escapeHtml(doc.document_id)}</code>${sourceLink}</small>
        <details class="knowledge-access-editor"><summary>Readers: ${escapeHtml(roles)}</summary>
          <form class="knowledge-access-form" data-document-id="${escapeHtml(doc.document_id)}">
            <div class="knowledge-access-options">${Object.entries(UPLOAD_ROLE_LABELS).map(([role, [label]]) => `<label><input type="checkbox" name="allowed_roles" value="${escapeHtml(role)}" ${(doc.allowed_roles || []).includes(role) ? "checked" : ""}><span>${escapeHtml(label)}</span></label>`).join("")}</div>
            <button class="secondary-button" type="submit">Save access</button>
            <small data-access-status aria-live="polite"></small>
          </form>
        </details>
      </div>
      <div class="knowledge-document-actions">
        ${doc.has_processing_output ? `<button class="secondary-button" type="button" data-review-elements="${escapeHtml(doc.document_id)}" aria-expanded="${reviewOpen ? "true" : "false"}">${reviewOpen ? "Hide element review" : "Review elements"}</button>` : ""}
        ${canRetryEmbedding ? `<button class="secondary-button" type="button" data-retry-embedding="${escapeHtml(doc.document_id)}">Retry embedding</button>` : ""}
        ${doc.knowledge_base_active === false && doc.source_type === "user_upload" ? `<button class="danger-button" type="button" data-knowledge-delete="${escapeHtml(doc.document_id)}" data-title="${escapeHtml(doc.title)}">Delete permanently</button>` : ""}
        <button class="${doc.knowledge_base_active ? "danger-button" : "secondary-button"}" type="button" data-knowledge-toggle="${escapeHtml(doc.document_id)}" data-active="${doc.knowledge_base_active ? "true" : "false"}">${doc.knowledge_base_active ? "Remove from knowledge base" : "Restore to knowledge base"}</button>
      </div>
    </article>${reviewOpen ? renderKnowledgeProcessingReview(doc) : ""}</div>`;
  }).join("") || '<p class="loading-card">No matching indexed sources.</p>';
}

const INVOICE_REVIEW_FIELDS = [
  ["invoice_no", "Invoice number"], ["date", "Invoice date"], ["seller", "Seller"],
  ["buyer", "Buyer"], ["subtotal", "Subtotal"], ["tax_amount", "Tax amount"],
  ["total_amount", "Total amount"],
];
const INVOICE_ITEM_FIELDS = [
  ["description", "Description"], ["quantity", "Quantity"], ["unit", "Unit"],
  ["unit_price", "Unit price"], ["amount", "Amount"],
];
const invoiceReviewValue = (value) => value == null ? "" : String(value);
const formatInvoiceDate = (value) => {
  const raw = invoiceReviewValue(value).trim();
  const match = raw.match(/^(?:(\d{4})-(\d{2})-(\d{2})|(\d{1,2})\/(\d{1,2})\/(\d{4})|(\d{1,2})\s+tháng\s+(\d{1,2})\s+năm\s+(\d{4}))$/i);
  if (!match) return raw;
  const [, isoYear, isoMonth, isoDay, slashDay, slashMonth, slashYear, viDay, viMonth, viYear] = match;
  const day = Number(isoDay || slashDay || viDay);
  const month = Number(isoMonth || slashMonth || viMonth);
  const year = Number(isoYear || slashYear || viYear);
  const parsed = new Date(Date.UTC(year, month - 1, day));
  if (parsed.getUTCFullYear() !== year || parsed.getUTCMonth() !== month - 1 || parsed.getUTCDate() !== day) return raw;
  return `${String(day).padStart(2, "0")}/${String(month).padStart(2, "0")}/${year}`;
};

function readInvoiceCache(cache, key) {
  if (!cache.has(key)) return undefined;
  const value = cache.get(key);
  cache.delete(key);
  cache.set(key, value);
  return value;
}

function writeInvoiceCache(cache, key, value, limit, onEvict = null) {
  if (cache.has(key)) cache.delete(key);
  cache.set(key, value);
  while (cache.size > limit) {
    const [oldKey, oldValue] = cache.entries().next().value;
    cache.delete(oldKey);
    onEvict?.(oldValue);
  }
}

function clearInvoiceReviewCaches() {
  invoiceReviewEvidenceCache.clear();
  invoiceReviewSourceRequests.clear();
  for (const url of invoiceReviewSourceUrlCache.values()) URL.revokeObjectURL(url);
  invoiceReviewSourceUrlCache.clear();
}

async function fetchInvoiceSource(invoiceId, session) {
  const cached = readInvoiceCache(invoiceReviewSourceUrlCache, invoiceId);
  if (cached) return cached;
  const pending = invoiceReviewSourceRequests.get(invoiceId);
  if (pending) return pending;

  const request = (async () => {
    const response = await backendFetch(`/api/invoices/${encodeURIComponent(invoiceId)}/source`, {
      credentials: "same-origin",
      headers: { "ngrok-skip-browser-warning": "1" },
    });
    if (response.status === 401) {
      if (session === sessionGeneration) clearExpiredSession();
      throw new Error("Sign in to continue");
    }
    if (response.status === 404) return null;
    if (!response.ok) throw new Error(`Could not load invoice source (HTTP ${response.status})`);
    const url = URL.createObjectURL(await response.blob());
    if (session !== sessionGeneration) {
      URL.revokeObjectURL(url);
      return null;
    }
    writeInvoiceCache(invoiceReviewSourceUrlCache, invoiceId, url, INVOICE_REVIEW_SOURCE_CACHE_SIZE,
      (oldUrl) => URL.revokeObjectURL(oldUrl));
    return url;
  })();
  invoiceReviewSourceRequests.set(invoiceId, request);
  try {
    return await request;
  } finally {
    if (invoiceReviewSourceRequests.get(invoiceId) === request) invoiceReviewSourceRequests.delete(invoiceId);
  }
}

// Image invoices open fitted to the pane; zoom with the buttons, Ctrl + wheel or + / − keys, drag to pan.
function mountInvoiceImageViewer(wrapper, url) {
  wrapper.querySelector(".invoice-zoom")?.remove();
  const viewer = document.createElement("div");
  viewer.className = "invoice-zoom";
  viewer.innerHTML = `<div class="invoice-zoom-bar" role="toolbar" aria-label="Zoom the original invoice">
      <button type="button" data-zoom="out" aria-label="Zoom out" title="Zoom out"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12h14"/></svg></button>
      <output aria-live="polite">100%</output>
      <button type="button" data-zoom="in" aria-label="Zoom in" title="Zoom in"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14M5 12h14"/></svg></button>
      <button type="button" data-zoom="fit" class="invoice-zoom-fit">Fit</button>
      <button type="button" data-zoom="actual" class="invoice-zoom-fit">100%</button>
    </div>
    <div class="invoice-zoom-stage" tabindex="0" aria-label="Original invoice image"><img alt="Original invoice" draggable="false"></div>`;
  wrapper.prepend(viewer);
  const stage = viewer.querySelector(".invoice-zoom-stage");
  const image = viewer.querySelector("img");
  const label = viewer.querySelector("output");
  let scale = 1;
  let fitScale = 1;
  const apply = (next, anchor = null) => {
    const previous = scale;
    scale = Math.min(6, Math.max(0.1, next));
    image.style.width = `${Math.round(image.naturalWidth * scale)}px`;
    label.textContent = `${Math.round(scale * 100)}%`;
    viewer.querySelector("[data-zoom=fit]").setAttribute("aria-pressed", String(Math.abs(scale - fitScale) < 0.005));
    if (anchor) {
      const ratio = scale / previous;
      stage.scrollLeft = (stage.scrollLeft + anchor.x) * ratio - anchor.x;
      stage.scrollTop = (stage.scrollTop + anchor.y) * ratio - anchor.y;
    }
  };
  const fit = () => {
    if (!image.naturalWidth) return;
    fitScale = Math.min((stage.clientWidth - 24) / image.naturalWidth, (stage.clientHeight - 24) / image.naturalHeight, 1.5);
    apply(fitScale);
    stage.scrollTo(0, 0);
  };
  image.addEventListener("load", fit, { once: true });
  image.src = url;
  viewer.querySelector(".invoice-zoom-bar").addEventListener("click", (event) => {
    const action = event.target.closest("[data-zoom]")?.dataset.zoom;
    const centre = { x: stage.clientWidth / 2, y: stage.clientHeight / 2 };
    if (action === "in") apply(scale * 1.25, centre);
    if (action === "out") apply(scale / 1.25, centre);
    if (action === "fit") fit();
    if (action === "actual") apply(1, centre);
  });
  stage.addEventListener("wheel", (event) => {
    if (!event.ctrlKey && !event.metaKey) return;
    event.preventDefault();
    const box = stage.getBoundingClientRect();
    apply(scale * (event.deltaY < 0 ? 1.12 : 1 / 1.12), { x: event.clientX - box.left, y: event.clientY - box.top });
  }, { passive: false });
  stage.addEventListener("keydown", (event) => {
    const centre = { x: stage.clientWidth / 2, y: stage.clientHeight / 2 };
    if (event.key === "+" || event.key === "=") { event.preventDefault(); apply(scale * 1.25, centre); }
    if (event.key === "-") { event.preventDefault(); apply(scale / 1.25, centre); }
    if (event.key === "0") { event.preventDefault(); fit(); }
  });
  let drag = null;
  stage.addEventListener("pointerdown", (event) => {
    if (event.button !== 0) return;
    drag = { x: event.clientX, y: event.clientY, left: stage.scrollLeft, top: stage.scrollTop };
    stage.setPointerCapture(event.pointerId);
    stage.classList.add("is-panning");
  });
  stage.addEventListener("pointermove", (event) => {
    if (!drag) return;
    stage.scrollLeft = drag.left - (event.clientX - drag.x);
    stage.scrollTop = drag.top - (event.clientY - drag.y);
  });
  const endDrag = () => { drag = null; stage.classList.remove("is-panning"); };
  stage.addEventListener("pointerup", endDrag);
  stage.addEventListener("pointercancel", endDrag);
}

function attachInvoiceSource(invoice, session, sourcePromise = null) {
  if (!invoice.source_available) return;
  const invoiceId = invoice.invoice_id;
  const detail = $("#invoice-review-detail");
  const wrapper = [...detail.querySelectorAll(".invoice-review-source-wrap")]
    .find((candidate) => candidate.dataset.invoiceId === invoiceId);
  const frame = wrapper?.querySelector("iframe");
  const status = wrapper?.querySelector("[data-invoice-source-status]");
  if (!wrapper || !frame || !status) return;
  const pendingSource = sourcePromise || fetchInvoiceSource(invoiceId, session).then(
    (url) => ({ url }),
    (error) => ({ error }),
  );
  pendingSource.then((result) => {
    if (session !== sessionGeneration || activeInvoiceReview?.invoice_id !== invoiceId || !wrapper.isConnected) return;
    if (result.url) {
      if (/\.(png|jpe?g|gif|webp|bmp|svg)$/i.test(invoice.source_filename || "")) mountInvoiceImageViewer(wrapper, result.url);
      else {
        frame.src = `${result.url}#zoom=page-fit`;
        frame.hidden = false;
      }
      status.remove();
    } else {
      status.textContent = result.error?.message || "Original file is unavailable.";
    }
  });
}

async function loadInvoiceReviewEvidence(details) {
  if (details.dataset.loaded === "true" || details.dataset.loading === "true") return;
  const invoiceId = details.dataset.invoiceId;
  const content = details.querySelector("[data-invoice-evidence-content]");
  const summary = details.querySelector("summary");
  if (!invoiceId || !content || !summary) return;
  details.dataset.loading = "true";
  content.textContent = "Loading OCR evidence…";
  try {
    let evidence = readInvoiceCache(invoiceReviewEvidenceCache, invoiceId);
    if (!evidence) {
      evidence = await api(`/api/invoices/${encodeURIComponent(invoiceId)}/evidence`);
      writeInvoiceCache(invoiceReviewEvidenceCache, invoiceId, evidence, INVOICE_REVIEW_EVIDENCE_CACHE_SIZE);
    }
    if (activeInvoiceReview?.invoice_id !== invoiceId || !details.isConnected) return;
    const elements = Array.isArray(evidence.ocr_elements) ? evidence.ocr_elements : [];
    const tables = Array.isArray(evidence.ocr_tables) ? evidence.ocr_tables : [];
    summary.textContent = `OCR evidence (${elements.length} elements, ${tables.length} tables)`;
    content.innerHTML = elements.map((element) => `<details class="invoice-ocr-element"><summary>Page ${escapeHtml(element.page_number ?? "?")} · ${escapeHtml(element.label || element.type || "OCR text")}</summary><pre>${escapeHtml(element.text || element.content || JSON.stringify(element))}</pre></details>`).join("") || "<p>No OCR text was saved.</p>";
    details.dataset.loaded = "true";
  } catch (error) {
    if (details.isConnected) content.textContent = `Could not load OCR evidence: ${error.message}`;
  } finally {
    delete details.dataset.loading;
  }
}

let invoiceOpenGeneration = 0;

function renderInvoiceReviewList() {
  const statusFilter = $("#invoice-review-filter").value;
  const filteredInvoices = statusFilter === "all"
    ? invoiceReviewItems
    : invoiceReviewItems.filter((invoice) => invoice.processing_status === statusFilter);
  const pageCount = Math.max(1, Math.ceil(filteredInvoices.length / INVOICE_REVIEW_PAGE_SIZE));
  invoiceReviewPage = Math.min(invoiceReviewPage, pageCount);
  const start = (invoiceReviewPage - 1) * INVOICE_REVIEW_PAGE_SIZE;
  $("#invoice-review-list").innerHTML = filteredInvoices.slice(start, start + INVOICE_REVIEW_PAGE_SIZE).map((invoice) => {
    const data = invoice.invoice_data || {};
    const selected = invoice.invoice_id === activeInvoiceReview?.invoice_id;
    const status = invoice.processing_status || "unknown";
    return `<button class="invoice-review-card ${selected ? "active" : ""}" type="button" data-invoice-review-id="${escapeHtml(invoice.invoice_id)}">
      <strong>${escapeHtml(invoice.source_filename || invoice.invoice_id)}</strong>
      <span>${escapeHtml(data.invoice_no || "Invoice number not extracted")} · ${escapeHtml(data.seller || "Seller not extracted")}</span>
      <small><span class="invoice-status-badge is-${escapeHtml(({approved: "approved", review_required: "review", failed: "failed", processing: "processing", rejected: "rejected"})[status] || "unknown")}">${escapeHtml(({review_required: "Needs review", failed: "Extraction failed", processing: "Processing", approved: "Approved", rejected: "Rejected"})[status] || status)}</span> <time>${escapeHtml(formatShortDate(invoice.updated_at || invoice.created_at))}</time></small>
    </button>`;
  }).join("") || '<p class="analysis-empty">No invoices match this status.</p>';
  $("#invoice-review-page").textContent = `${filteredInvoices.length ? start + 1 : 0}–${Math.min(start + INVOICE_REVIEW_PAGE_SIZE, filteredInvoices.length)} of ${filteredInvoices.length}`;
  $("#invoice-review-prev").disabled = invoiceReviewPage === 1;
  $("#invoice-review-next").disabled = invoiceReviewPage === pageCount;
}

function renderInvoiceReviewDetail(invoice, { sourcePromise = null } = {}) {
  invoiceProgressGeneration += 1;
  activeInvoiceReview = invoice;
  renderInvoiceReviewList();
  const data = invoice.invoice_data || {};
  const editable = invoice.processing_status === "review_required";
  const canApprove = currentUser?.role === "admin" && editable;
  const canReject = currentUser?.role === "admin" && editable;
  const fields = INVOICE_REVIEW_FIELDS.map(([key, label]) => `<label>${escapeHtml(label)}<input name="${key}" value="${escapeHtml(key === "date" ? formatInvoiceDate(data[key]) : invoiceReviewValue(data[key]))}" ${editable ? "" : "readonly"}></label>`).join("");
  const items = Array.isArray(data.items) ? data.items : [];
  const itemRows = items.map((item, index) => `<fieldset class="invoice-review-item" data-item-index="${index}"><legend>Line item ${index + 1}</legend>
    ${INVOICE_ITEM_FIELDS.map(([key, label]) => `<label>${escapeHtml(label)}${key === "description" ? `<textarea name="items.${index}.${key}" ${editable ? "" : "readonly"}>${escapeHtml(invoiceReviewValue(item?.[key]))}</textarea>` : `<input name="items.${index}.${key}" value="${escapeHtml(invoiceReviewValue(item?.[key]))}" ${editable ? "" : "readonly"}>`}</label>`).join("")}
    ${editable ? `<button class="secondary-button" type="button" data-remove-invoice-item="${index}">Remove line</button>` : ""}
  </fieldset>`).join("");
  const source = invoice.source_available
    ? '<p class="invoice-source-status" data-invoice-source-status role="status">Loading original invoice…</p><iframe class="invoice-review-source" title="Original invoice" hidden></iframe>'
    : '<p class="analysis-empty">Original file is unavailable.</p>';
  const failed = invoice.processing_status === "failed";
  const retry = failed && invoice.source_available ? `
    <form id="invoice-retry-form" data-invoice-id="${escapeHtml(invoice.invoice_id)}">
      <div class="invoice-review-actions">
        <label for="invoice-retry-model">Extraction model</label>
        <select id="invoice-retry-model" name="model_provider">${$("#invoice-model").innerHTML}</select>
        <button class="primary-button" type="submit">Retry extraction</button>
      </div>
      <p class="corpus-note" data-invoice-retry-status role="status"></p>
    </form>` : "";
  const processing = invoice.processing_status === "processing";
  const detail = $("#invoice-review-detail");
  const existingSource = detail.querySelector(".invoice-review-source-wrap");
  const keepSource = existingSource?.dataset.invoiceId === invoice.invoice_id && !!existingSource.querySelector("iframe") === !!invoice.source_available;
  const previousWorkspace = keepSource ? existingSource.parentElement : null;
  if (previousWorkspace) previousWorkspace.removeChild(previousWorkspace.querySelector(".invoice-review-editor"));
  const rendered = document.createElement("div");
  rendered.innerHTML = `
    ${failed ? `<p role="status">Extraction failed${invoice.error_message ? `: ${escapeHtml(invoice.error_message)}` : "."}</p>` : ""}
    ${retry}
    ${processing ? `<div class="upload-status-wrap invoice-processing-progress" aria-busy="true">
      <div class="upload-progress" role="progressbar" aria-label="Invoice extraction" aria-valuetext="OCR and extraction in progress"><span></span></div>
      <p role="status" data-invoice-progress-status>Running OCR and extraction. Status updates automatically.</p>
      <small class="upload-elapsed" data-invoice-progress-elapsed aria-live="off"></small>
    </div>` : ""}
    <div class="invoice-review-workspace">
    <div class="invoice-review-source-wrap" data-invoice-id="${escapeHtml(invoice.invoice_id)}">${source}</div>
    <div class="invoice-review-editor">
    ${(failed || processing) && !Object.keys(data).length ? `<p class="analysis-empty">${failed ? "No extracted data. Retry extraction to create a draft." : "Your draft will appear here when extraction finishes."}</p>` : `<form id="invoice-review-form" data-invoice-id="${escapeHtml(invoice.invoice_id)}">
      <div class="invoice-review-fields">${fields}</div><div id="invoice-review-items">${itemRows}</div>
      ${editable ? `<div class="invoice-review-actions"><button class="secondary-button" type="button" data-add-invoice-item>Add line item</button><button class="${canApprove ? "secondary-button" : "primary-button"}" type="submit">Save corrections</button>${canApprove ? `<button class="primary-button" type="button" data-approve-invoice>Approve and publish</button>` : ""}${canReject ? `<button class="danger-button" type="button" data-reject-invoice>Reject invoice</button>` : ""}</div>` : `<p class="corpus-note">This invoice is ${escapeHtml(invoice.processing_status)} and read-only.</p>`}
      <p class="corpus-note" data-invoice-edit-status aria-live="polite"></p>
    </form>`}
    <details class="invoice-ocr-evidence" data-invoice-id="${escapeHtml(invoice.invoice_id)}"><summary>OCR evidence · open to load</summary><div class="invoice-ocr-evidence-content" data-invoice-evidence-content>OCR evidence loads when expanded.</div></details>
    </div></div>`;
  if (keepSource) {
    previousWorkspace.append(rendered.querySelector(".invoice-review-editor"));
    for (const child of [...detail.children]) if (child !== previousWorkspace) child.remove();
    while (rendered.firstElementChild && !rendered.firstElementChild.classList.contains("invoice-review-workspace")) detail.insertBefore(rendered.firstElementChild, previousWorkspace);
  } else {
    detail.replaceChildren(...rendered.childNodes);
    detail.classList.remove("is-entering");
    void detail.offsetWidth;
    detail.classList.add("is-entering");
  }
  if (!keepSource) attachInvoiceSource(invoice, sessionGeneration, sourcePromise);
  detail.querySelector(".invoice-ocr-evidence")?.addEventListener("toggle", (event) => {
    if (event.currentTarget.open) void loadInvoiceReviewEvidence(event.currentTarget);
  });
  if (retry) $("#invoice-retry-model").value = "groq";
  if (processing) watchInvoiceProgress(invoice, invoiceProgressGeneration);
}

async function watchInvoiceProgress(invoice, progressGeneration) {
  const session = sessionGeneration;
  const parsedStart = Date.parse(invoice.updated_at || invoice.created_at);
  const startedAt = Number.isFinite(parsedStart) ? parsedStart : Date.now();
  let nextPollAt = Date.now() + 4000;
  while (
    progressGeneration === invoiceProgressGeneration
    && session === sessionGeneration
    && activeInvoiceReview?.invoice_id === invoice.invoice_id
  ) {
    const elapsed = $("#invoice-review-detail [data-invoice-progress-elapsed]");
    if (!elapsed) return;
    const seconds = Math.floor(Math.max(0, Date.now() - startedAt) / 1000);
    elapsed.textContent = `Elapsed: ${Math.floor(seconds / 60)}m ${seconds % 60}s · Checking status every 4s`;
    await new Promise((resolve) => window.setTimeout(resolve, 1000));
    if (progressGeneration !== invoiceProgressGeneration || session !== sessionGeneration) return;
    if (Date.now() < nextPollAt) continue;
    nextPollAt = Date.now() + 4000;
    let result;
    try {
      result = await api(`/api/invoices/${encodeURIComponent(invoice.invoice_id)}?include_evidence=false`, { cache: "no-store" });
    } catch (error) {
      if (progressGeneration !== invoiceProgressGeneration || session !== sessionGeneration) return;
      $("#invoice-review-detail [data-invoice-progress-status]").textContent =
        `Could not check status: ${error.message}. Reconnecting…`;
      continue;
    }
    if (progressGeneration !== invoiceProgressGeneration || session !== sessionGeneration) return;
    invoiceReviewItems = invoiceReviewItems.map((item) => item.invoice_id === result.invoice_id ? { ...item, ...result } : item);
    if (result.processing_status !== "processing") {
      renderInvoiceReviewDetail(result);
      $("#invoice-review-status").textContent = result.processing_status === "review_required"
        ? "Extraction finished. Review the invoice fields below."
        : result.processing_status === "failed" ? "Extraction failed. You can retry with another model." : `Invoice status: ${result.processing_status}`;
      return;
    }
    activeInvoiceReview = result;
    $("#invoice-review-detail [data-invoice-progress-status]").textContent =
      "Running OCR and extraction. Status updates automatically.";
  }
}

async function refreshInvoiceReview(selectId = activeInvoiceReview?.invoice_id) {
  $("#invoice-review-status").textContent = "Loading invoice drafts…";
  const result = await api("/api/invoices");
  invoiceReviewItems = result.invoices || [];
  renderInvoiceReviewList();
  const target = invoiceReviewItems.find((item) => item.invoice_id === selectId)
    || invoiceReviewItems.find((item) => item.processing_status === "review_required");
  if (target) await openInvoiceReview(target.invoice_id);
  else {
    activeInvoiceReview = null;
    $("#invoice-review-detail").innerHTML = '<p class="analysis-empty">Choose an invoice to review.</p>';
  }
  $("#invoice-review-status").textContent = `${invoiceReviewItems.length} invoice${invoiceReviewItems.length === 1 ? "" : "s"} · drafts stay private until approved.`;
}

async function openInvoiceReview(invoiceId) {
  const generation = ++invoiceOpenGeneration;
  const session = sessionGeneration;
  const summary = invoiceReviewItems.find((item) => item.invoice_id === invoiceId);
  if (!summary) return;
  const sourcePromise = fetchInvoiceSource(invoiceId, session).then(
    (url) => ({ url }),
    (error) => ({ error }),
  );
  if (generation !== invoiceOpenGeneration || session !== sessionGeneration) return;
  renderInvoiceReviewDetail(structuredClone(summary), { sourcePromise });
}

async function retryInvoiceExtraction(form) {
  const invoiceId = form.dataset.invoiceId;
  invoiceReviewEvidenceCache.delete(invoiceId);
  const path = `/api/invoices/${encodeURIComponent(invoiceId)}`;
  const generation = sessionGeneration;
  const button = form.querySelector('button[type="submit"]');
  const status = form.querySelector("[data-invoice-retry-status]");
  const modelProvider = form.elements.namedItem("model_provider").value;
  button.disabled = true;
  status.textContent = "Starting extraction…";
  try {
    await api(`${path}/retry`, {
      method: "POST",
      body: JSON.stringify({ model_provider: modelProvider }),
    });
  } catch (error) {
    status.textContent = error.message;
    button.disabled = false;
    return;
  }

  if (generation !== sessionGeneration) return;
  const invoice = activeInvoiceReview?.invoice_id === invoiceId ? activeInvoiceReview
    : invoiceReviewItems.find((item) => item.invoice_id === invoiceId);
  if (invoice) {
    const processingInvoice = { ...invoice, processing_status: "processing", error_message: null, updated_at: new Date().toISOString() };
    invoiceReviewItems = invoiceReviewItems.map((item) => item.invoice_id === invoiceId ? processingInvoice : item);
    if (activeInvoiceReview?.invoice_id === invoiceId) renderInvoiceReviewDetail(processingInvoice);
    else renderInvoiceReviewList();
  }
}

function invoiceReviewPayload(form) {
  const data = Object.fromEntries(INVOICE_REVIEW_FIELDS.map(([key]) => [key, form.elements.namedItem(key).value.trim() || null]));
  data.items = [...form.querySelectorAll(".invoice-review-item")].map((row) => Object.fromEntries(
    INVOICE_ITEM_FIELDS.map(([key]) => [key, row.querySelector(`[name="items.${row.dataset.itemIndex}.${key}"]`).value.trim() || null]),
  ));
  return data;
}

async function saveInvoiceReview(form, approve = false) {
  const status = form.querySelector("[data-invoice-edit-status]");
  const invoiceId = form.dataset.invoiceId;
  const button = approve ? form.querySelector("[data-approve-invoice]") : form.querySelector('[type="submit"]');
  button.disabled = true;
  status.textContent = approve ? "Approving invoice…" : "Saving corrections…";
  try {
    const invoiceData = invoiceReviewPayload(form);
    await api(`/api/invoices/${encodeURIComponent(invoiceId)}${approve ? "/approve" : ""}`, {
      method: approve ? "POST" : "PATCH", body: JSON.stringify({ invoice_data: invoiceData }),
    });
    await refreshInvoiceReview(invoiceId);
    $("#invoice-review-status").textContent = approve ? "Invoice approved and published to analytics." : "Corrections saved.";
  } catch (error) {
    status.textContent = error.message;
    button.disabled = false;
  }
}

async function rejectInvoice(form) {
  const invoiceId = form.dataset.invoiceId;
  if (!(await confirmDialog({ title: "Reject this invoice?", message: "It stays available for review but will not be published to analytics.", confirmLabel: "Reject invoice", danger: true }))) return;
  const button = form.querySelector("[data-reject-invoice]");
  const status = form.querySelector("[data-invoice-edit-status]");
  button.disabled = true;
  status.textContent = "Rejecting invoice…";
  try {
    await api(`/api/invoices/${encodeURIComponent(invoiceId)}/reject`, { method: "POST" });
    await refreshInvoiceReview(invoiceId);
    $("#invoice-review-status").textContent = "Invoice rejected and kept out of analytics.";
  } catch (error) {
    status.textContent = error.message;
    button.disabled = false;
  }
}

$("#invoice-review-refresh").addEventListener("click", () => refreshInvoiceReview().catch((error) => {
  $("#invoice-review-status").textContent = `Could not load invoices: ${error.message}`;
}));
$("#invoice-review-list").addEventListener("click", (event) => {
  const button = event.target.closest("[data-invoice-review-id]");
  if (button) openInvoiceReview(button.dataset.invoiceReviewId).catch((error) => {
    $("#invoice-review-status").textContent = error.message;
  });
});
$("#invoice-review-filter").addEventListener("change", () => {
  invoiceReviewPage = 1;
  renderInvoiceReviewList();
});
$("#invoice-review-prev").addEventListener("click", () => {
  invoiceReviewPage = Math.max(1, invoiceReviewPage - 1);
  renderInvoiceReviewList();
});
$("#invoice-review-next").addEventListener("click", () => {
  invoiceReviewPage += 1;
  renderInvoiceReviewList();
});
$("#invoice-review-detail").addEventListener("submit", (event) => {
  if (event.target.id === "invoice-retry-form") {
    event.preventDefault();
    retryInvoiceExtraction(event.target);
    return;
  }
  if (event.target.id !== "invoice-review-form") return;
  event.preventDefault();
  saveInvoiceReview(event.target);
});
$("#invoice-review-detail").addEventListener("click", (event) => {
  const form = event.target.closest("#invoice-review-form");
  if (!form) return;
  if (event.target.closest("[data-approve-invoice]")) return saveInvoiceReview(form, true);
  if (event.target.closest("[data-reject-invoice]")) return rejectInvoice(form);
  if (event.target.closest("[data-add-invoice-item]")) {
    const currentData = invoiceReviewPayload(form);
    currentData.items.push(Object.fromEntries(INVOICE_ITEM_FIELDS.map(([key]) => [key, null])));
    activeInvoiceReview.invoice_data = currentData;
    renderInvoiceReviewDetail(activeInvoiceReview);
  }
  const remove = event.target.closest("[data-remove-invoice-item]");
  if (remove) {
    const index = Number(remove.dataset.removeInvoiceItem);
    const currentData = invoiceReviewPayload(form);
    currentData.items.splice(index, 1);
    activeInvoiceReview.invoice_data = currentData;
    renderInvoiceReviewDetail(activeInvoiceReview);
  }
});

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
    const intent = config.intent || "document";
    const parserSettings = intent === "document"
      ? `Document · Docling · ${selected.docling_device || "cpu"} · OCR ${selected.docling_ocr ? "on" : "off"} (${selected.docling_ocr_language || "vi"}) · tables ${selected.docling_table_structure ? "on" : "off"} · ${selected.docling_num_threads || 4} threads`
      : intent === "invoice" ? "Invoice extraction · Docling OCR + Qwen text model" : "Image caption · Vintern";
    const settings = parserSettings;
    const previewSummary = run.page_count ? `${formatNumber(run.page_count)} page previews` : "no page previews";
    const processingSummary = `processing ${formatDuration(run.runtime_info?.processing_time_ms)}`;
    return `<button type="button" class="ocr-run-button" data-ocr-run-id="${escapeHtml(run.run_id)}"><strong>${escapeHtml(run.source_filename)}</strong><span>${escapeHtml(formatDateTime(run.created_at))} · ${processingSummary} · ${previewSummary} · ${formatNumber(run.element_count)} parser elements · ${formatNumber(run.table_count)} tables · ${escapeHtml(settings)}</span></button>`;
  }).join("") || '<p class="loading-card">No upload tests yet. Upload a supported document above to create one.</p>';
}

function renderOcrTestDetails(run) {
  const previewPages = run.pages || [];
  const invoiceExtraction = run.runtime_info?.invoice_extraction;
  const invoiceOutput = invoiceExtraction ? `<section class="ocr-test-invoice">
    <div class="candidate-heading"><strong>Invoice JSON draft</strong><span>${escapeHtml(invoiceExtraction.model || "Text model")} · ${invoiceExtraction.review_required ? "review required" : "status unknown"}</span></div>
    <p class="corpus-note">Schema ${escapeHtml(invoiceExtraction.schema_version || "invoice.v1")} · inference ${formatDuration((invoiceExtraction.metrics?.inference_seconds || 0) * 1000)} · this draft is separate from the parser elements and table output.</p>
    <pre>${escapeHtml(JSON.stringify(invoiceExtraction.fields ?? null, null, 2))}</pre>
    ${invoiceExtraction.parse_error ? `<p class="corpus-note" data-state="warning">${escapeHtml(invoiceExtraction.parse_error)}. Raw model response is available below.</p>` : ""}
    ${invoiceExtraction.raw_response ? `<details class="candidate-source"><summary>Raw model response</summary><pre>${escapeHtml(invoiceExtraction.raw_response)}</pre></details>` : ""}
  </section>` : "";
  const singlePreviewPage = previewPages.length === 1 ? Number(previewPages[0]) : null;
  const elementPage = (element) => element.metadata?.page_number;
  const tablePage = (table) => table.page_number ?? table.metadata?.page_number;
  const inferredPageAssignment = singlePreviewPage != null && (
    run.elements.some((element) => elementPage(element) == null)
    || run.tables.some((table) => tablePage(table) == null)
  );
  const allPages = [...new Set([
    ...previewPages,
    ...run.elements.map((element) => elementPage(element) == null ? NaN : Number(elementPage(element))).filter(Number.isFinite),
    ...run.tables.map((table) => tablePage(table) == null ? NaN : Number(tablePage(table))).filter(Number.isFinite),
  ])].sort((a, b) => a - b);
  const pageContent = allPages.map((pageNumber, pageIndex) => {
    const elements = run.elements.filter((element) => {
      const value = elementPage(element);
      return value == null ? singlePreviewPage === pageNumber : Number(value) === pageNumber;
    });
    const tables = run.tables.filter((table) => {
      const value = tablePage(table);
      return value == null ? singlePreviewPage === pageNumber : Number(value) === pageNumber;
    });
    const pageSize = run.runtime_info?.parser_page_sizes?.[String(pageNumber)]
      || run.runtime_info?.preview_page_sizes?.[String(pageNumber)];
    const pageWidth = Number(pageSize?.width);
    const pageHeight = Number(pageSize?.height);
    const hasOutOfBoundsBox = elements.some((element) => {
      const metadata = element.metadata || {};
      const bbox = metadata.bbox;
      if (metadata.bbox_coordinate_system !== "docling_page_coordinate" || !Array.isArray(bbox) || bbox.length !== 4) return false;
      const [left, top, right, bottom] = bbox.map(Number);
      return [left, top, right, bottom].every(Number.isFinite)
        && (left < -1 || top < -1 || right > pageWidth + 1 || bottom > pageHeight + 1);
    });
    const boxes = hasOutOfBoundsBox ? "" : elements.flatMap((element) => {
      const metadata = element.metadata || {};
      const bbox = metadata.bbox;
      if (
        metadata.bbox_coordinate_system !== "docling_page_coordinate"
        || !Array.isArray(bbox) || bbox.length !== 4
        || !Number.isFinite(pageWidth) || !Number.isFinite(pageHeight)
        || pageWidth <= 0 || pageHeight <= 0
      ) return [];
      const [left, top, right, bottom] = bbox.map(Number);
      if (![left, top, right, bottom].every(Number.isFinite)) return [];
      const x = Math.max(0, Math.min(pageWidth, left));
      const y = Math.max(0, Math.min(pageHeight, top));
      const width = Math.max(0, Math.min(pageWidth, right) - x);
      const height = Math.max(0, Math.min(pageHeight, bottom) - y);
      if (!width || !height) return [];
      const label = String(metadata.element_type || "text").toLowerCase().replace(/[^a-z0-9_-]/g, "");
      const snippet = String(element.content || "").replace(/\s+/g, " ").slice(0, 100);
      const linkId = `${pageNumber}:${element.element_index}`;
      return [`<g class="layout-region layout-region-${escapeHtml(label)}" data-bbox-link="${escapeHtml(linkId)}"><title>Element ${formatNumber(element.element_index + 1)} · ${escapeHtml(label)}${snippet ? `: ${escapeHtml(snippet)}` : ""}</title><rect x="${x}" y="${y}" width="${width}" height="${height}" /></g>`];
    }).join("");
    const pagePreviewImage = `<img loading="lazy" alt="Rendered source page ${formatNumber(pageNumber)}" src="/api/upload-tests/${encodeURIComponent(run.run_id)}/pages/${pageNumber}/preview">`;
    const pagePreview = boxes && pageSize
      ? `<div class="ocr-layout-preview">${pagePreviewImage}<svg viewBox="0 0 ${pageWidth} ${pageHeight}" preserveAspectRatio="none" aria-label="Parser element bounding boxes">${boxes}</svg></div>`
      : pagePreviewImage;
    const missingBoxScale = !pageSize && elements.some((element) => Array.isArray(element.metadata?.bbox));
    const ocrDiagnostics = elements.flatMap((element) => element.metadata?.ocr_diagnostics || []);
    const tablesHtml = tables.map((table) => {
      const data = table.structured_data || {};
      const context = table.context || {};
      const columns = Array.isArray(data.columns) ? data.columns : [];
      const rows = Array.isArray(data.rows) ? data.rows : [];
      const headers = columns.length ? columns : [...new Set(rows.flatMap((row) => Object.keys(row || {})))];
      const tableMinWidth = Math.max(460, headers.length * 115);
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
        ${headers.length ? `<div class="ocr-test-table-wrap"><table class="extracted-table" style="min-width:${tableMinWidth}px"><thead><tr>${headers.map((column) => `<th>${escapeHtml(column)}</th>`).join("")}</tr></thead><tbody>${rows.map((row) => `<tr>${headers.map((column) => `<td>${escapeHtml(row?.[column] ?? "")}</td>`).join("")}</tr>`).join("")}</tbody></table></div>` : `<pre>${escapeHtml(JSON.stringify(data, null, 2))}</pre>`}
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
        ${missingBoxScale ? '<p class="corpus-note">This run has element boxes but no saved page dimensions. Re-run Upload Test to overlay them on the page.</p>' : ""}
        ${hasOutOfBoundsBox ? '<p class="corpus-note">Saved element boxes do not fit the page dimensions for this older run, so the overlay is hidden. Re-run Upload Test to save matching parser coordinates.</p>' : ""}
        ${inferredPageAssignment ? '<p class="corpus-note">Page assignment inferred from the only preview; parser metadata has no page number.</p>' : ""}
        ${renderOcrDiagnostics(ocrDiagnostics)}
        <details class="ocr-test-elements"><summary>Document elements · ${formatNumber(elements.length)} elements</summary>${elements.map((element) => `<article class="ocr-test-element" data-bbox-link="${escapeHtml(`${pageNumber}:${element.element_index}`)}" tabindex="0" aria-label="Element ${formatNumber(element.element_index + 1)} on page ${formatNumber(pageNumber)}"><div class="candidate-heading"><strong>Element ${formatNumber(element.element_index + 1)}</strong><span>${formatNumber(element.content.length)} chars · ${escapeHtml(element.metadata?.element_type || "text")} · ${escapeHtml(element.metadata?.text_extraction_method || "parser output")}</span></div><pre>${escapeHtml(element.content)}</pre><details class="candidate-source"><summary>Element metadata</summary><pre>${escapeHtml(JSON.stringify(element.metadata, null, 2))}</pre></details></article>`).join("") || '<p class="ocr-test-empty">No parser elements on this page.</p>'}</details>
        <h4 class="ocr-test-table-heading">Extracted tables</h4>
        ${tablesHtml || '<p class="ocr-test-empty">No structured table detected on this page.</p>'}
      </section>
      </div>
    </details>`;
  }).join("");
  const unpagedElements = run.elements.filter((element) => elementPage(element) == null && singlePreviewPage == null);
  const unpagedTables = run.tables.filter((table) => tablePage(table) == null && singlePreviewPage == null);
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
            const tableMinWidth = Math.max(460, columns.length * 115);
            const location = table.metadata?.sheet_name ? ` · ${escapeHtml(table.metadata.sheet_name)}` : "";
            return `<article class="ocr-test-table"><h5>Table ${formatNumber(table.table_index + 1)}${location} <span>${formatNumber(rows.length)} rows</span></h5>
              ${columns.length ? `<div class="ocr-test-table-wrap"><table class="extracted-table" style="min-width:${tableMinWidth}px"><thead><tr>${columns.map((column) => `<th>${escapeHtml(column)}</th>`).join("")}</tr></thead><tbody>${rows.map((row) => `<tr>${columns.map((column) => `<td>${escapeHtml(row?.[column] ?? "")}</td>`).join("")}</tr>`).join("")}</tbody></table></div>` : `<pre>${escapeHtml(JSON.stringify(data, null, 2))}</pre>`}
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
    ${invoiceOutput}
    <div class="ocr-test-pages">${pageContent}${unpagedOutput}</div>
  </article>`;
}

function setUploadTestHighlight(item) {
  const page = item.closest(".ocr-test-page-content");
  if (!page) return;
  page.querySelectorAll("[data-bbox-link]").forEach((linkedItem) => {
    linkedItem.classList.toggle("is-highlighted", linkedItem.dataset.bboxLink === item.dataset.bboxLink);
  });
}

function clearUploadTestHighlight(item) {
  item.closest(".ocr-test-page-content")?.querySelectorAll(".is-highlighted").forEach((linkedItem) => {
    linkedItem.classList.remove("is-highlighted");
  });
}

document.addEventListener("pointerover", (event) => {
  const item = event.target.closest?.("[data-bbox-link]");
  if (!item || (event.relatedTarget instanceof Element && item.contains(event.relatedTarget))) return;
  setUploadTestHighlight(item);
});

document.addEventListener("pointerout", (event) => {
  const item = event.target.closest?.("[data-bbox-link]");
  if (!item || (event.relatedTarget instanceof Node && item.contains(event.relatedTarget))) return;
  const nextItem = event.relatedTarget instanceof Element ? event.relatedTarget.closest("[data-bbox-link]") : null;
  if (nextItem && nextItem.closest(".ocr-test-page-content") === item.closest(".ocr-test-page-content")) {
    setUploadTestHighlight(nextItem);
  } else {
    clearUploadTestHighlight(item);
  }
});

document.addEventListener("focusin", (event) => {
  const item = event.target.closest?.("[data-bbox-link]");
  if (item) setUploadTestHighlight(item);
});

document.addEventListener("focusout", (event) => {
  const item = event.target.closest?.("[data-bbox-link]");
  if (!item) return;
  const nextItem = event.relatedTarget instanceof Element ? event.relatedTarget.closest("[data-bbox-link]") : null;
  if (nextItem && nextItem.closest(".ocr-test-page-content") === item.closest(".ocr-test-page-content")) {
    setUploadTestHighlight(nextItem);
  } else {
    clearUploadTestHighlight(item);
  }
});

async function openOcrTestRun(runId) {
  $("#ocr-test-results").innerHTML = '<p class="loading-card">Loading test pages and parser output…</p>';
  try {
    renderOcrTestDetails(await api(`/api/upload-tests/${encodeURIComponent(runId)}`));
  } catch (error) {
    $("#ocr-test-results").innerHTML = `<p class="loading-card">${escapeHtml(error.message)}</p>`;
  }
}

function updateUploadTestParserSettings() {
  const intent = $("#ocr-test-parser").value;
  document.querySelectorAll("#ocr-test-form [data-parser-settings]").forEach((fieldset) => {
    const active = fieldset.dataset.parserSettings === intent;
    fieldset.hidden = !active;
    fieldset.querySelectorAll("input, select, textarea").forEach((control) => {
      control.disabled = !active;
    });
  });
  $("#ocr-test-file").accept = intent === "document"
    ? ".pdf,.docx,.pptx,.xlsx,.csv,.txt,.md,.png,.jpg,.jpeg,.tif,.tiff,.svg,.webp"
    : ".pdf,.png,.jpg,.jpeg,.tif,.tiff,.webp";
}

$("#ocr-test-parser").addEventListener("change", updateUploadTestParserSettings);
updateUploadTestParserSettings();

// The chrome is English, so numbers group with commas: "3.180" reads as 3.18 to an English reader.
function formatNumber(value) {
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 3 }).format(value);
}

// "12 Nov 2026, 16:20" cannot be misread the way 11/12/2026 is (day-first in VN, month-first in US).
const DATE_TIME_FORMAT = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
const SHORT_DATE_FORMAT = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric" });
// Figures count up from zero once when they appear, keeping their decimals and unit.
function countUp(element) {
  element.dataset.value ??= element.textContent;
  const match = element.dataset.value.match(/^([\d,]*\.?\d+)(.*)$/);
  if (!match || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const target = Number(match[1].replaceAll(",", ""));
  const decimals = (match[1].split(".")[1] || "").length;
  const started = performance.now();
  const step = (now) => {
    const t = Math.min(1, (now - started) / 700);
    const value = target * (1 - (1 - t) ** 3);
    element.textContent = value.toLocaleString("en-US", { minimumFractionDigits: decimals, maximumFractionDigits: decimals }) + match[2];
    if (t < 1 && element.isConnected) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

function formatShortDate(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value ?? "") : SHORT_DATE_FORMAT.format(date);
}

function formatDateTime(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value ?? "") : DATE_TIME_FORMAT.format(date);
}

// People read names, not identifiers; unknown keys fall back to a readable form of the key.
const ROLE_NAMES = {
  ...Object.fromEntries(Object.entries(UPLOAD_ROLE_LABELS).map(([key, [label]]) => [key, label])),
  document_uploader: "Document uploader", document_processing_owner: "Document processing owner", tester: "Tester",
};
const PERMISSION_NAMES = {
  view_corpus: "See the document list", ask_documents: "Ask about documents", view_analytics: "Use analytics",
  run_sql_analytics: "Query sales data", upload_documents: "Upload documents", classify_documents: "Classify documents",
  manage_access: "Manage access", manage_knowledge: "Manage the knowledge base", view_agent_monitoring: "See agent monitoring",
  list_processing_documents: "See document processing", process_documents: "Process documents", inspect_parsing: "Inspect parsing",
  review_invoices: "Review invoices", run_upload_tests: "Run upload tests", review_upload_tests: "Review upload tests",
};
const AGENT_NAMES = {
  knowledge: "Knowledge", sql: "Analytics", sql_analytics: "Analytics", analytics: "Analytics", auto: "Auto", agentic: "Auto (planner)",
  hybrid: "Knowledge + analytics", dashboard: "Dashboard", report: "Report", general: "General chat",
};
const RETRIEVAL_NAMES = {
  translated_hybrid_rerank: "Bilingual search + rerank", translated_hybrid: "Bilingual search", hybrid: "Hybrid search",
  dense: "Semantic search", bm25: "Keyword search", parent: "Parent passages", "-": "—", "": "—",
};
const CLAIM_CHECK_NAMES = { supported: "Passed", insufficient: "Withheld", contradicted: "Withheld", unavailable: "Not checked" };
function displayName(names, key) {
  if (key == null) return "—";
  return names[key] ?? String(key).replace(/_/g, " ").replace(/^\w/, (letter) => letter.toUpperCase());
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

// The verified seal: a stamped ring with a check that draws itself in.
const SEAL_MARK = '<span class="answer-seal" aria-hidden="true"><svg viewBox="0 0 100 100"><circle class="seal-outer" cx="50" cy="50" r="46"/><circle class="seal-inner" cx="50" cy="50" r="38"/><path class="seal-check" d="M35 51 l10 10 l20 -22"/></svg></span>';

function renderAnswerBody(answer) {
  const lines = String(answer || "").split(/\r?\n/);
  const blocks = [];
  let paragraph = [];
  const inline = (value) => escapeHtml(value)
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\s*\[(S\d+)\]([.,;:!?)]?)/g, '<span class="cite-glue"><a class="cite-ref" href="#" data-cite="$1" aria-label="Source $1">$1</a>$2</span>');
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

// How an answer measured up: verified (the seal), withheld by the claim check, not covered, or partial.
// Withholding is the product keeping its promise, so it reads as amber information, never as an error.
function answerOutcome(data, citations) {
  const check = data.claim_verification;
  const pill = (kind, text) => `<p class="answer-status ${kind}">${escapeHtml(text)}</p>`;
  const rephrase = '<div class="answer-next"><button type="button" class="secondary-button answer-rephrase">Rephrase the question</button></div>';
  if (check?.status === "supported" && citations.length) {
    return { badge: `<p class="answer-verified">${SEAL_MARK}Every claim checked against its cited source${check.claim_count ? ` · ${formatNumber(check.claim_count)} claims` : ""}</p>`, next: "" };
  }
  if (data.citation_validation_failed || (check && check.status !== "supported")) {
    const reason = VERIFICATION_REASONS[check?.reason] || "the answer could not be matched to its sources";
    return { title: "Answer withheld", gap: true, badge: pill("is-withheld", `Withheld: ${reason}`), next: rephrase };
  }
  if (data.insufficient_context) {
    return { title: "Not in your documents", gap: true, badge: pill("is-gap", "Not covered by the documents you can access"), next: rephrase };
  }
  if (data.status === "partial") return { gap: true, badge: pill("is-gap", "Partial answer: some parts are not covered"), next: "" };
  return { badge: "", next: "" };
}

// Source cards show two lines of their passage until opened, so the answer outweighs its sources.
// The toggle only stays where the two-line clamp actually hides text (measured once the card is visible).
function pruneCitationToggles(root) {
  root?.querySelectorAll?.(".citation:not(.is-open) .citation-toggle").forEach((toggle) => {
    const passage = toggle.closest(".citation").querySelector(":scope > p");
    if (!passage || !passage.offsetParent) return;
    if (passage.scrollHeight <= passage.clientHeight + 1) toggle.remove();
  });
}

function setCitationOpen(card, open) {
  card.classList.toggle("is-open", open);
  const toggle = card.querySelector(".citation-toggle");
  if (!toggle) return;
  toggle.setAttribute("aria-expanded", String(open));
  toggle.textContent = open ? "Show less" : "Show full passage";
}

// A broken knowledge base is said plainly in the conversation, with Retry, not only in the sidebar footer.
async function loadCorpusStats() {
  try {
    renderCorpus(await api("/api/dashboard"));
    $("#service-notice").hidden = true;
  } catch (error) {
    $("#connection-status").textContent = "Search unavailable";
    $("#connection-status").title = error.message;
    $("#service-notice").hidden = false;
  }
}
$("#service-retry").addEventListener("click", async (event) => {
  event.currentTarget.disabled = true;
  await loadCorpusStats();
  event.currentTarget.disabled = false;
});

function renderAnswer(data, panel = $("#answer-panel"), shouldScroll = true) {
  panel.hidden = false;
  const citations = Array.isArray(data.citations) ? data.citations : [];
  const usedEvidenceFallback = Boolean(data.answer_fallback_reason || data.fallback);
  const outcome = answerOutcome(data, citations);
  const responseTitle = data.failure_code === "sql_timeout" ? "The data query took too long"
    : outcome.title
    || ({partial: "Partial answer", clarification_required: "Clarification needed", failed: "Could not complete"})[data.status]
    || (data.ok === false ? "Answer unavailable" : usedEvidenceFallback ? "Evidence only" : "Answer");
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
  const fallbackNotice = usedEvidenceFallback && !data.limitations?.length
    ? '<p class="analysis-caveat answer-provenance-note" role="note"><strong>Evidence fallback.</strong> This is not successful model synthesis.</p>'
    : "";
  const sqlScope = data.context_used
    ? (() => {
      const scope = data.semantic_interpretation || {};
      const time = scope.time || {};
      const snapshot = time.start || (data.snapshot_dates || []).join(", ") || time.mode || "not reported";
      const filters = (scope.filters || []).map((item) => `${item.field} ${item.operator} ${Array.isArray(item.value) ? item.value.join(", ") : item.value}`);
      const snapshotLabel = data.historical_inventory ? "Historical snapshot" : "Snapshot";
      return `<p class="analysis-caveat answer-provenance-note" role="status"><strong>Continuing the previous SQL scope.</strong> ${snapshotLabel}: ${escapeHtml(snapshot)}${filters.length ? ` · Filters: ${filters.map(escapeHtml).join("; ")}` : ""}</p>`;
    })()
    : "";
  const routeDetails = renderRunDetails(data);
  panel.innerHTML = `
    <div class="answer-header-wrap">
      <div class="answer-heading${outcome.gap || data.status === "partial" || data.limitations?.length ? " is-partial" : ""}">
        <span class="answer-mark">${usedEvidenceFallback ? "EV" : "AI"}</span>
        <div><span class="eyebrow">${escapeHtml(({knowledge:"Knowledge agent",analytics:"Analytics agent",sql_analytics:"Analytics agent",dashboard:"Inventory agent",report:"Report agent",agentic:"Automatic router",hybrid:"Knowledge + analytics"})[data.agent] || "Agent response")}</span><h3>${escapeHtml(responseTitle)}</h3></div>
      </div>
    </div>
    ${outcome.badge}
    ${domainNote}
    ${decisionModeNote}
    ${referenceRetrievalNote}
    ${questionSqlFallbackNote}
    ${limitations}
    ${fallbackNotice}
    ${sqlScope}
    <div class="answer-text">${renderAnswerBody(data.answer)}</div>
    ${outcome.next}
    ${renderAgentRows(data.data)}
    ${renderDashboardVisualization(data.data?.visualization)}
    ${data.citation_validation_failed ? (data.decision_validation_failure ? `<details class="answer-diagnostic"><summary>Admin diagnostic</summary><code>${escapeHtml(data.decision_validation_failure)}</code>${data.decision_validation_numeric_tokens?.length ? `<p>Unsupported numeric claims: ${data.decision_validation_numeric_tokens.map(escapeHtml).join(", ")}</p>` : ""}</details>` : "") : citations.length ? `
      <div class="citations">
        <div class="citation-header-row">
          <h4>Sources (${citations.length})</h4>
          <span class="citation-count-badge">${citations.length} source${citations.length === 1 ? "" : "s"}</span>
        </div>
        ${citations.map((source) => {
          const href = uploadedSourcePageUrl(source.document_id, source.page_number)
            || syntheticPolicySourcePageUrl(source)
            || validSourceUrl(source.source_url);
          const link = href ? `<a href="${escapeHtml(href)}" target="_blank" rel="noopener noreferrer">View original</a>` : "";
          const chunk = Number.isInteger(source.chunk_index) ? ` · passage ${source.chunk_index}` : "";
          const location = source.page_number ? `Page ${source.page_number}${chunk}`
            : source.source_type === "commerce_sql" ? `SQL aggregate · ${(source.source_tables || []).join(", ")}`
              : source.source_type === "commerce_schema" ? `Schema coverage · ${(source.source_tables || []).join(", ")}`
              : Number.isInteger(source.chunk_index) ? `Passage ${source.chunk_index + 1}` : "Reference";
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
          const publisher = source.source_publisher || source.company || "";
          return `
            <article class="citation" data-cite-id="${escapeHtml(source.id)}">
              <div class="citation-title">
                <span class="citation-id">${escapeHtml(source.id)}</span>
                <strong>${escapeHtml(source.title)}</strong>
                <span>${escapeHtml(location)}</span>
              </div>
              ${referenceScope}
              ${ocrNote}
              ${sourceExcerpt}
              ${observationTrace}
              ${sqlTrace}
              <div class="citation-foot">
                ${publisher || source.evidence_class ? `<span>${escapeHtml([publisher, source.evidence_class?.replaceAll("_", " ")].filter(Boolean).join(" · "))}</span>` : ""}
                ${sourceExcerpt ? `<button type="button" class="citation-toggle" aria-expanded="false">Show full passage</button>` : ""}
                ${link}
              </div>
            </article>`;
        }).join("")}
      </div>` : ""}
    ${routeDetails}
    ${tokenUsage}
    <div class="answer-actions-bar">
      ${outcome.next ? "" : `<button type="button" class="action-btn copy-answer-btn" title="Copy response text" aria-label="Copy response">${ICONS.copy}<span class="action-label">Copy</span></button>`}
    </div>`;

  // Inline [S1] chips scroll to and highlight their source card.
  panel.querySelectorAll(".cite-ref").forEach((ref) => ref.addEventListener("click", (event) => {
    event.preventDefault();
    const card = panel.querySelector(`.citation[data-cite-id="${CSS.escape(ref.dataset.cite)}"]`);
    if (!card || card.hidden) return;
    setCitationOpen(card, true);
    card.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "nearest" });
    card.classList.remove("is-highlighted");
    void card.offsetWidth;
    card.classList.add("is-highlighted");
    setTimeout(() => card.classList.remove("is-highlighted"), 1600);
  }));
  requestAnimationFrame(() => pruneCitationToggles(panel));
  panel.querySelectorAll(".citation-toggle").forEach((toggle) => toggle.addEventListener("click", () => {
    const card = toggle.closest(".citation");
    setCitationOpen(card, !card.classList.contains("is-open"));
  }));
  const copyBtn = panel.querySelector(".copy-answer-btn");
  if (copyBtn) {
    copyBtn.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(data.answer);
        copyBtn.innerHTML = `${ICONS.check}<span class="action-label">Copied</span>`;
        copyBtn.classList.add("copied");
        setTimeout(() => {
          copyBtn.innerHTML = `${ICONS.copy}<span class="action-label">Copy</span>`;
          copyBtn.classList.remove("copied");
        }, 2000);
      } catch {
        alert("Unable to copy automatically. Please select the text and press Ctrl+C.");
      }
    });
  }

  if (shouldScroll) panel.scrollIntoView({ behavior: "smooth", block: "start" });
}

function renderAgentRows(data) {
  const groups = Object.entries(data || {}).filter(([, value]) => value && !Array.isArray(value) && typeof value === "object");
  if (Array.isArray(data?.rows)) groups.unshift(["Results", data]);
  return groups.map(([label, value]) => {
    const rows = value?.rows;
    if (!Array.isArray(rows) && !value?.attempted_sql) return "";
    const validRows = (rows || []).filter((row) => row && typeof row === "object" && !Array.isArray(row));
    const columns = validRows.length ? Object.keys(validRows[0]).slice(0, 12) : [];
    const executed = value.query_status === "executed";
    const statusLabel = executed ? "Đã chạy" : value.query_status === "error"
      ? (value.failure_code === "analytics_not_configured" ? "Thiếu cấu hình" : value.failure_code === "sql_timeout" ? "Dừng do timeout" : "Lỗi khi chạy")
      : value.query_status === "rejected" ? "Bị chặn trước khi chạy"
        : value.query_status === "clarification_required" ? "Chờ bạn làm rõ" : value.query_status;
    const queryStatus = value.query_status
      ? `<span class="query-status ${executed ? "is-executed" : "is-not-executed"}">${escapeHtml(statusLabel)}</span>`
      : "";
    const canShowRows = value.query_status == null || executed;
    const table = canShowRows && validRows.length
      ? `<div class="commerce-table-wrap"><table><thead><tr>${columns.map((key) => `<th scope="col">${escapeHtml(key.replaceAll("_", " "))}</th>`).join("")}</tr></thead><tbody>${validRows.slice(0, 50).map((row) => `<tr>${columns.map((key) => `<td>${escapeHtml(row[key] ?? "—")}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`
      : executed && Array.isArray(rows) ? '<p class="no-citations">The query ran and returned no rows.</p>' : "";
    const diagnosticSql = value.attempted_sql || value.sql;
    const parameters = Array.isArray(value.parameters) && value.parameters.length
      ? `<p>Parameters: <code>${escapeHtml(JSON.stringify(value.parameters))}</code></p>`
      : "";
    const diagnostics = diagnosticSql || parameters
      ? `<details><summary>${value.query_status === "error" ? "Show the failed query" : value.query_status === "rejected" ? "Show the blocked query" : executed ? "Show the SQL that ran" : "Query details"}</summary>${diagnosticSql ? `<pre>${escapeHtml(diagnosticSql)}</pre>` : ""}${parameters}</details>`
      : "";
    const jev = value.jev;
    const jevNote = jev?.probabilities ? `<p class="jev-note">JEV · rõ ${Math.round((jev.probabilities.clear || 0) * 100)}% · mơ hồ ${Math.round((jev.probabilities.ambiguous || 0) * 100)}% · độ rõ tối thiểu để chạy ${Math.round((jev.threshold || 0) * 100)}%</p>` : "";
    return `<section class="agent-data-result"><h4>${escapeHtml(label.replace(/^task:/, "Task "))} ${queryStatus}</h4>${table}${jevNote}${diagnostics}</section>`;
  }).join("");
}

function renderAgentResult(result, panel = $("#answer-panel"), shouldScroll = true) {
  const citations = (result.evidence || []).map((item) => {
    const metadata = item.metadata || {};
    return { ...metadata, id: item.citation_id, title: item.source, source_type: item.source_type,
      excerpt: item.content || "", content: item.content, score: metadata.similarity_score };
  });
  renderAnswer({ ...result, ...result.metadata, metadata: result.metadata, citations }, panel, shouldScroll);
}

// "9.4 s" reads the same in every locale; "9.420 ms" looks like 9 ms where "." groups thousands.
const formatSeconds = (ms) => `${(Number(ms) / 1000).toFixed(1)} s`;

function selectMonitorTab(name, focus = false) {
  document.querySelectorAll("[data-monitor-tab]").forEach((tab) => {
    const selected = tab.dataset.monitorTab === name;
    tab.setAttribute("aria-selected", String(selected));
    tab.tabIndex = selected ? 0 : -1;
    if (selected && focus) tab.focus();
  });
  document.querySelectorAll("[data-monitor-panel]").forEach((panel) => { panel.hidden = panel.dataset.monitorPanel !== name; });
}
document.querySelector(".monitoring-tabs")?.addEventListener("click", (event) => {
  const tab = event.target.closest("[data-monitor-tab]");
  if (tab) selectMonitorTab(tab.dataset.monitorTab);
});
document.querySelector(".monitoring-tabs")?.addEventListener("keydown", (event) => {
  if (!["ArrowLeft", "ArrowRight"].includes(event.key)) return;
  const tabs = [...document.querySelectorAll("[data-monitor-tab]")];
  const index = tabs.findIndex((tab) => tab.getAttribute("aria-selected") === "true");
  const next = tabs[(index + (event.key === "ArrowRight" ? 1 : tabs.length - 1)) % tabs.length];
  selectMonitorTab(next.dataset.monitorTab, true);
});

function renderAgentMonitoring(data) {
  const summary = data.summary || {};
  const cards = [
    ["Runs, last 24 h", summary.total_runs ?? 0],
    ["Success rate", summary.success_rate == null ? "—" : `${summary.success_rate}%`],
    ["Average latency", summary.average_elapsed_ms == null ? "—" : formatSeconds(summary.average_elapsed_ms)],
    ["P95 latency", summary.p95_elapsed_ms == null ? "—" : formatSeconds(summary.p95_elapsed_ms)],
    ["Runs, last hour", summary.last_hour_runs ?? 0],
  ];
  $("#monitoring-summary").innerHTML = cards.map(([label, value]) => `<article class="monitoring-stat"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></article>`).join("");
  $("#monitoring-summary").querySelectorAll("strong").forEach(countUp);
  const agents = data.by_agent || [];
  const maxRuns = Math.max(1, ...agents.map((agent) => Number(agent.total_runs) || 0));
  $("#monitoring-agents").innerHTML = agents.length ? agents.map((agent) => `
    <div class="monitoring-agent"><div><strong>${escapeHtml(displayName(AGENT_NAMES, agent.agent_name))}</strong><span>${formatNumber(agent.completed_runs)} of ${formatNumber(agent.total_runs)} completed, ${agent.average_elapsed_ms == null ? "no timing" : `${formatSeconds(agent.average_elapsed_ms)} average`}</span></div><i role="img" aria-label="${formatNumber(agent.completed_runs)} completed and ${formatNumber(Math.max(0, agent.total_runs - agent.completed_runs))} failed or unfinished, out of ${formatNumber(agent.total_runs)} runs"><span class="bar-fill" style="width:${Math.max(3, Number(agent.total_runs) / maxRuns * 100)}%"><b class="is-done" style="width:${agent.total_runs ? Number(agent.completed_runs) / Number(agent.total_runs) * 100 : 0}%"></b><b class="is-other"></b></span></i></div>
  `).join("") : '<p class="analysis-empty">No agent runs have been recorded in the last 24 hours.</p>';
  const runs = data.recent_runs || [];
  $("#monitor-count-runs").textContent = runs.length ? formatNumber(runs.length) : "";
  $("#monitoring-runs").innerHTML = runs.length ? `<div class="monitoring-table-wrap"><table class="monitoring-table"><thead><tr><th>Time</th><th>Role</th><th>Agent</th><th>Retrieval</th><th>Result</th><th>Latency</th><th>Sources</th></tr></thead><tbody>${runs.map((run) => `<tr><td>${escapeHtml(formatDateTime(run.created_at))}</td><td>${escapeHtml(displayName(ROLE_NAMES, run.actor_role))}</td><td>${escapeHtml(displayName(AGENT_NAMES, run.agent_name))}</td><td>${escapeHtml(displayName(RETRIEVAL_NAMES, run.retrieval_method))}</td><td><span class="run-status ${escapeHtml(run.status)}">${escapeHtml(run.status.replaceAll("_", " "))}</span>${run.error_type ? `<small>${escapeHtml(run.error_type)}</small>` : ""}</td><td>${formatSeconds(run.elapsed_ms)}</td><td>${formatNumber(run.citation_count)}</td></tr>`).join("")}</tbody></table></div>` : '<p class="analysis-empty">No requests recorded yet.</p>';
}

async function refreshAgentMonitoring() {
  const button = $("#monitoring-refresh");
  button.disabled = true;
  try {
    renderAgentMonitoring(await api("/api/admin/agent-monitoring"));
  } catch (error) {
    $("#monitoring-runs").innerHTML = `<p class="error-message">${escapeHtml(error.message)}</p>`;
  }
  try {
    renderAnswerFeedback(await api("/api/admin/answer-feedback"));
  } catch (error) {
    $("#monitoring-feedback").innerHTML = `<p class="error-message">${escapeHtml(error.message)}</p>`;
  } finally {
    button.disabled = false;
  }
}

// Source files (links and PDF previews) are fetched like invoice sources: through backendFetch, so they follow
// the fallback and carry the ngrok header (a plain link or iframe cannot), then shown from a blob URL.
async function loadApiFile(path) {
  const [url, hash = ""] = path.split("#");
  const response = await backendFetch(url, { credentials: "same-origin", headers: { "ngrok-skip-browser-warning": "1" } });
  if (response.status === 401) {
    clearExpiredSession();
    throw new Error("Sign in to continue");
  }
  if (!response.ok) throw new Error(`Could not open the source (HTTP ${response.status})`);
  // shortcut: blob URLs are not revoked, so each opened source stays in memory until the page reloads.
  return URL.createObjectURL(await response.blob()) + (hash ? `#${hash}` : "");
}

document.addEventListener("click", async (event) => {
  const link = event.target.closest?.('a[href^="/api/"]');
  if (!link || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
  event.preventDefault();
  const tab = link.target === "_blank" ? window.open("about:blank", "_blank") : null;  // opened now, while the click still counts
  if (tab) tab.opener = null;
  try {
    const url = await loadApiFile(link.getAttribute("href"));
    if (tab) tab.location.replace(url); else location.assign(url);
  } catch (error) {
    if (tab) tab.document.body.textContent = error.message;
  }
});

new MutationObserver((records) => records.forEach((record) => record.addedNodes.forEach((node) => {
  const frames = node.nodeType === 1 ? [...(node.matches("iframe[data-api-src]") ? [node] : []), ...node.querySelectorAll("iframe[data-api-src]")] : [];
  frames.forEach((frame) => {
    const path = frame.dataset.apiSrc;
    frame.removeAttribute("data-api-src");
    if (path) loadApiFile(path).then((url) => { frame.src = url; }).catch(() => {});
  });
}))).observe(document.documentElement, { childList: true, subtree: true });

// Two backends behind Vercel: /api is the primary (NGROK_URL), /api-fallback the second one (FALLBACK_URL).
// Signed in, the page times a real database round trip on both every few minutes and uses the faster one,
// preferring the primary unless the other is clearly faster. A request that cannot reach its backend at all
// (the proxy or tunnel answers instead of the app, which always answers JSON) moves once to the other backend.
const API_BASES = ["/api", "/api-fallback"];
let apiBase = "/api";
let backendTimer = null;

function backendUnreachable(response, method) {
  const type = response.headers.get("content-type") || "";
  if (type.includes("json") || type.includes("event-stream")) return false;
  // 502/530 and ngrok's offline 404 mean the request never reached the app; 503/504 might have, so only GETs move.
  return [502, 530, 404].includes(response.status) || (method === "GET" && [503, 504].includes(response.status));
}

async function backendFetch(path, init = {}) {
  const method = (init.method || "GET").toUpperCase();
  const at = (base) => fetch(path.replace(/^\/api(?=\/)/, base), init);
  const other = () => API_BASES.find((base) => base !== apiBase);
  try {
    const response = await at(apiBase);
    if (!path.startsWith("/api/") || !backendUnreachable(response, method)) return response;
  } catch (error) {
    if (error.name === "AbortError" || error.name === "TimeoutError" || method !== "GET" || !path.startsWith("/api/")) throw error;
  }
  apiBase = other();
  return at(apiBase);
}

async function chooseBackend() {
  const time = async (base) => {
    const started = performance.now();
    try {
      const response = await fetch(`${base}/health/db`, { credentials: "same-origin", cache: "no-store",
        headers: { "ngrok-skip-browser-warning": "1" }, signal: AbortSignal.timeout(10_000) });
      return response.ok ? performance.now() - started : Infinity;
    } catch {
      return Infinity;
    }
  };
  const [primary, fallback] = await Promise.all(API_BASES.map(time));
  if (primary === Infinity && fallback === Infinity) return;
  // shortcut: one sample per check; switches only when the other is >40% faster, upgrade to a rolling median if it flaps.
  apiBase = fallback < primary * 0.6 ? "/api-fallback" : "/api";
}

async function api(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (!(options.body instanceof FormData)) headers["Content-Type"] = "application/json";
  headers["ngrok-skip-browser-warning"] = "1";
  const response = await backendFetch(path, { credentials: "same-origin", ...options, headers });
  if (response.status === 401 && path !== "/api/auth/login") {
    clearExpiredSession();
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

// Thumbs up/down next to Copy. A rating sends the question and the shown answer (see answer_feedback).
const ICONS = {
  copy: '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="8" y="8" width="12" height="12" rx="2.5"/><path d="M16 8V6.5A2.5 2.5 0 0 0 13.5 4h-7A2.5 2.5 0 0 0 4 6.5v7A2.5 2.5 0 0 0 6.5 16H8"/></svg>',
  check: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m5 12.5 4.5 4.5L19 7.5"/></svg>',
  up: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 10v10H4.5A1.5 1.5 0 0 1 3 18.5v-7A1.5 1.5 0 0 1 4.5 10H7Zm0 0 4-7a2.5 2.5 0 0 1 2.5 2.5V9h5.2a2 2 0 0 1 2 2.4l-1.4 7A2 2 0 0 1 17.3 20H7"/></svg>',
  down: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M17 14V4h2.5A1.5 1.5 0 0 1 21 5.5v7a1.5 1.5 0 0 1-1.5 1.5H17Zm0 0-4 7a2.5 2.5 0 0 1-2.5-2.5V15H5.3a2 2 0 0 1-2-2.4l1.4-7A2 2 0 0 1 6.7 4H17"/></svg>',
};
const FEEDBACK_REASONS = ["Wrong information", "Missing details", "Wrong or weak source", "Hard to understand"];

function attachFeedback(panel, turn) {
  const bar = panel.querySelector(".answer-actions-bar");
  if (!bar || !turn.result?.answer) return;
  const box = document.createElement("span");
  box.className = "feedback-buttons";
  box.innerHTML = ["up", "down"].map((rating) => `<button type="button" class="action-btn feedback-btn" data-rating="${rating}" aria-pressed="false" aria-label="${rating === "up" ? "Helpful" : "Not helpful"}" title="${rating === "up" ? "Helpful" : "Not helpful"}: sends this question and answer to the team for review">${ICONS[rating]}</button>`).join("")
    + '<span class="feedback-status" role="status" aria-live="polite"></span>';
  bar.append(box);
  const status = box.querySelector(".feedback-status");
  const say = (text, tone = "") => {
    status.textContent = text;
    status.dataset.tone = tone;
    status.classList.remove("show");
    void status.offsetWidth;
    status.classList.add("show");
  };
  const mark = (rating) => box.querySelectorAll(".feedback-btn").forEach((button) => {
    const chosen = button.dataset.rating === rating;
    button.setAttribute("aria-pressed", String(chosen));
    button.classList.toggle("chosen", chosen);
    button.disabled = true;
  });
  if (turn.feedback) mark(turn.feedback);
  const unmark = () => box.querySelectorAll(".feedback-btn").forEach((button) => {
    button.setAttribute("aria-pressed", "false");
    button.classList.remove("chosen");
    button.disabled = false;
  });
  // Optimistic: the choice shows at once and the database write happens in the background;
  // if the write fails the choice is undone and the reason is shown, so nothing looks saved that isn't.
  const send = async (rating, comment) => {
    turn.feedback = rating;
    mark(rating);
    say("Thanks for the feedback", "ok");
    try {
      await api("/api/agents/feedback", { method: "POST", body: JSON.stringify({
        rating, question: turn.question, answer: turn.result.answer, agent: turn.result.agent || "unknown",
        comment: comment || null, claim_status: turn.result.metadata?.claim_verification?.status ?? null,
      }) });
    } catch (error) {
      turn.feedback = null;
      unmark();
      say(`Not saved: ${error.message}. Try again.`, "error");
      throw error;
    }
  };

  // Inline card for 👎: reason chips and an optional note; it opens and closes with a height animation.
  const card = document.createElement("div");
  card.className = "feedback-card";
  card.hidden = true;
  card.innerHTML = `<div class="feedback-card-inner"><form class="feedback-form">
      <p class="feedback-title">What went wrong?</p>
      <div class="feedback-reasons" role="group" aria-label="Reasons">${FEEDBACK_REASONS.map((reason) =>
        `<button type="button" class="feedback-reason" aria-pressed="false">${escapeHtml(reason)}</button>`).join("")}</div>
      <label class="visually-hidden" for="fb-${turn.id ?? Date.now()}">Details (optional)</label>
      <textarea id="fb-${turn.id ?? Date.now()}" maxlength="900" rows="2" placeholder="Tell us what the answer should have said (optional)"></textarea>
      <div class="feedback-form-actions">
        <button type="button" class="secondary-button feedback-cancel">Cancel</button>
        <button type="submit" class="primary-button feedback-send">Send feedback</button>
      </div>
    </form></div>`;
  bar.after(card);
  const open = (show) => {
    if (show) {
      card.hidden = false;
      requestAnimationFrame(() => card.classList.add("open"));
      card.querySelector("textarea").focus({ preventScroll: true });
    } else {
      card.classList.remove("open");
      const done = () => { card.hidden = true; };
      window.matchMedia("(prefers-reduced-motion: reduce)").matches ? done() : card.addEventListener("transitionend", done, { once: true });
    }
  };
  card.querySelector(".feedback-reasons").addEventListener("click", (event) => {
    const chip = event.target.closest(".feedback-reason");
    if (chip) chip.setAttribute("aria-pressed", String(chip.getAttribute("aria-pressed") !== "true"));
  });
  card.querySelector(".feedback-cancel").addEventListener("click", () => {
    open(false);
    box.querySelector('[data-rating="down"]').focus();
  });
  card.querySelector(".feedback-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const reasons = [...card.querySelectorAll('.feedback-reason[aria-pressed="true"]')].map((chip) => chip.textContent);
    const note = card.querySelector("textarea").value.trim();
    open(false);
    try {
      await send("down", [reasons.join(", "), note].filter(Boolean).join(" — ").slice(0, 1000));
    } catch {
      open(true);  // keep the typed note so the reader can resend
    }
  });

  box.addEventListener("click", async (event) => {
    const button = event.target.closest(".feedback-btn");
    if (!button || turn.feedback) return;
    if (button.dataset.rating === "down") {
      const opening = card.hidden;
      button.setAttribute("aria-expanded", String(opening));
      open(opening);
      return;
    }
    send("up", null).catch(() => {});
  });
}

function renderAnswerFeedback(data) {
  const summary = data.summary || {};
  const items = data.recent || [];
  $("#monitor-count-feedback").textContent = formatNumber((summary.up ?? 0) + (summary.down ?? 0));
  $("#monitoring-feedback").innerHTML = `<p class="rating-totals"><span>Last 30 days</span><span class="rating-pill up">${ICONS.up}${formatNumber(summary.up ?? 0)} helpful</span><span class="rating-pill down">${ICONS.down}${formatNumber(summary.down ?? 0)} not helpful</span></p>${items.length ? `<div class="monitoring-table-wrap"><table class="monitoring-table"><thead><tr><th>Time</th><th>Rating</th><th>Role</th><th>Agent</th><th>Question</th><th>Comment</th><th>Claim check</th></tr></thead><tbody>${items.map((item) => `<tr><td>${escapeHtml(formatDateTime(item.created_at))}</td><td><span class="rating-icon ${item.rating === "up" ? "up" : "down"}" title="${item.rating === "up" ? "Helpful" : "Not helpful"}">${ICONS[item.rating === "up" ? "up" : "down"]}<span class="visually-hidden">${item.rating === "up" ? "Helpful" : "Not helpful"}</span></span></td><td>${escapeHtml(displayName(ROLE_NAMES, item.actor_role))}</td><td>${escapeHtml(displayName(AGENT_NAMES, item.agent_name))}</td><td><details><summary>${escapeHtml(item.question.slice(0, 80))}</summary><p>${escapeHtml(item.answer)}</p></details></td><td>${escapeHtml(item.comment || "")}</td><td>${escapeHtml(item.claim_status ? displayName(CLAIM_CHECK_NAMES, item.claim_status) : "")}</td></tr>`).join("")}</tbody></table></div>` : '<p class="analysis-empty">No feedback yet.</p>'}`;
}

// Fades the old stage message out and the new one in; a newer stage cancels a fade still running.
function swapStageText(heading, text) {
  if (heading.textContent === text) return;
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    heading.textContent = text;
    return;
  }
  heading.getAnimations().filter((animation) => animation.id === "stage-swap").forEach((animation) => animation.cancel());
  const out = heading.animate([{ opacity: 1, transform: "translateY(0)" }, { opacity: 0, transform: "translateY(-4px)" }],
    { duration: 180, easing: "ease-in", fill: "forwards", id: "stage-swap" });
  out.finished.then(() => {
    heading.textContent = text;
    out.cancel();
    heading.animate([{ opacity: 0, transform: "translateY(4px)" }, { opacity: 1, transform: "translateY(0)" }],
      { duration: 260, easing: "ease-out", id: "stage-swap" });
  }).catch(() => { heading.textContent = text; });
}

const RUN_STAGE_LABELS = {
  routing: "Routing", knowledge_search_planning: "Search planning", query_translation: "Translation",
  embedding: "Query embedding", database_retrieval: "Database search", reranking: "Reranking",
  answer_generation: "Answer writing", claim_verification: "Claim check", sql_planning: "SQL planning",
  sql_execution: "SQL execution", answer_synthesis: "Synthesis",
};
const VERIFICATION_REASONS = {
  all_claims_supported: "every claim is supported by its cited passage",
  insufficient: "a claim is not supported by the cited passages",
  contradicted: "a claim contradicts a cited passage",
  unsupported_arithmetic: "a calculation does not match the sources",
  unverified_arithmetic: "a calculation could not be checked",
  uncited_or_oversized_draft: "the draft was too long or not cited, so it could not be checked",
  uncited_answer: "the draft cited no source",
  unknown_citation: "the draft cited a passage that was not retrieved",
};

// What the system actually did for this answer: route, search queries, passages, claim check, time.
function renderRunDetails(data) {
  const rows = [];
  if (data.selected_route) rows.push(`<p><strong>Route:</strong> ${escapeHtml(data.selected_route)}</p>`);
  if (Array.isArray(data.task_trace) && data.task_trace.length) {
    rows.push(`<ul>${data.task_trace.map((task) => `<li>${escapeHtml(task.agent)} · ${escapeHtml(task.status)} · ${formatNumber(task.elapsed_ms)} ms${task.error_type ? ` · ${escapeHtml(task.error_type)}` : ""}</li>`).join("")}</ul>`);
  }
  const search = data.search;
  if (search) {
    const queries = search.lexical_queries || {};
    const lines = [["Vietnamese", queries.vn], ["English", queries.en]].filter(([, text]) => text);
    if (lines.length) {
      rows.push(`<p><strong>Searched as:</strong></p><ul>${lines.map(([label, text]) => `<li>${label}: “${escapeHtml(text)}”</li>`).join("")}</ul>`);
    }
    const counts = [
      search.candidate_count ? `${formatNumber(search.candidate_count)} candidates reranked` : "",
      `${formatNumber(search.passages_to_model)} passages given to the model${search.context_radius ? " (with neighbouring text)" : ""}`,
      `${formatNumber((data.citations || []).length)} cited`,
    ].filter(Boolean);
    rows.push(`<p><strong>Passages:</strong> ${counts.join(" → ")}${search.reranker_model ? ` · reranker ${escapeHtml(String(search.reranker_model).split("/").pop())}` : ""}</p>`);
  }
  const check = data.claim_verification;
  if (check) {
    const verdict = check.status === "supported" ? "Passed" : "Answer withheld";
    const reason = VERIFICATION_REASONS[check.reason] || check.reason || "";
    const counted = [check.claim_count ? `${formatNumber(check.claim_count)} claims checked` : "",
      check.arithmetic_checked ? `${formatNumber(check.arithmetic_checked)} calculations checked` : ""].filter(Boolean);
    rows.push(`<p><strong>Claim check:</strong> ${verdict}${reason ? `: ${escapeHtml(reason)}` : ""}${counted.length ? ` (${counted.join(", ")})` : ""}</p>`);
  }
  const latency = data.latency || {};
  const stages = Object.entries(latency.stages_ms || {})
    .filter(([stage, ms]) => ms != null && RUN_STAGE_LABELS[stage])
    .sort((a, b) => b[1] - a[1]);
  if (stages.length || latency.request_total_ms) {
    const seconds = (ms) => `${(ms / 1000).toFixed(1)} s`;
    rows.push(`<p><strong>Time:</strong> ${latency.request_total_ms ? `${seconds(latency.request_total_ms)} on the server` : ""}</p>${stages.length ? `<ul>${stages.map(([stage, ms]) => `<li>${RUN_STAGE_LABELS[stage]}: ${seconds(ms)}</li>`).join("")}</ul><small>Some stages overlap, so they do not add up to the total.</small>` : ""}`);
  }
  return rows.length ? `<details class="agent-diagnostics"><summary>Run details</summary>${rows.join("")}</details>` : "";
}

// Reveals an already verified, fully rendered answer; markup and citation links stay intact
// because only the text nodes are filled in. About 60 characters a second, 3–10 s in total;
// `revealAfter` (the source panel, then each card) appears one by one after the text is complete.
// Skipped for reduced motion.
function typeOutText(element, revealAfter = []) {
  if (!element || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
  const nodes = [];
  while (walker.nextNode()) nodes.push([walker.currentNode, walker.currentNode.nodeValue]);
  const total = nodes.reduce((sum, [, text]) => sum + text.length, 0);
  if (!total) return;
  for (const [node] of nodes) node.nodeValue = "";
  for (const item of revealAfter) item.hidden = true;
  element.setAttribute("aria-busy", "true");
  const seconds = Math.min(10, Math.max(3, total / 60));
  const perFrame = Math.max(1, Math.ceil(total / (seconds * 60)));
  let index = 0;
  let shown = 0;
  const step = () => {
    let budget = perFrame;
    while (budget > 0 && index < nodes.length) {
      const [node, text] = nodes[index];
      const take = Math.min(budget, text.length - shown);
      node.nodeValue = text.slice(0, shown + take);
      shown += take;
      budget -= take;
      if (shown >= text.length) { index += 1; shown = 0; }
    }
    if (index < nodes.length && element.isConnected) requestAnimationFrame(step);
    else {
      for (const [node, text] of nodes) node.nodeValue = text;
      element.removeAttribute("aria-busy");
      revealAfter.forEach((item, position) => setTimeout(() => { item.hidden = false; requestAnimationFrame(() => pruneCitationToggles(item.closest(".answer-panel") || item)); }, 500 + position * 400));
    }
  };
  requestAnimationFrame(step);
}

const STAGE_STATUS = {
  routing: "Đang chọn agent phù hợp",
  knowledge_search_planning: "Đang chuẩn bị tìm tài liệu",
  query_translation: "Đang chuyển câu hỏi để tìm kiếm song ngữ",
  embedding: "Đang tìm tài liệu liên quan",
  database_retrieval: "Đang truy xuất dữ liệu",
  retrieval_fusion: "Đang hợp nhất kết quả tìm kiếm",
  reranking: "Đang xếp hạng nguồn phù hợp",
  answer_generation: "Đang soạn câu trả lời có trích dẫn",
  claim_verification: "Đang kiểm tra câu trả lời với nguồn",
  sql_ambiguity_check: "Đang kiểm tra câu hỏi có mơ hồ không",
  sql_planning: "Đang lập truy vấn SQL",
  sql_execution: "Đang chạy truy vấn SQL",
  answer_synthesis: "Đang tổng hợp kết quả",
};

// Streams stage progress; the answer arrives only after the claim verifier, never as draft tokens.
// Throws { streamUnavailable: true } before any answer is received so the caller can retry on /chat.
async function askAgentStream(body, signal, onStatus) {
  const unavailable = (message) => Object.assign(new Error(message), { streamUnavailable: true });
  let response;
  try {
    response = await backendFetch("/api/agents/chat/stream", {
      method: "POST", credentials: "same-origin", body, signal,
      headers: { "Content-Type": "application/json", "ngrok-skip-browser-warning": "1" },
    });
  } catch (error) {
    if (error.name === "TimeoutError" || error.name === "AbortError") throw error;
    throw unavailable(error.message);
  }
  if (response.status === 401) {
    clearExpiredSession();
    throw new Error("Sign in to continue");
  }
  if (!response.ok || !response.body || !(response.headers.get("content-type") || "").includes("text/event-stream")) {
    throw unavailable(`Streaming unavailable (HTTP ${response.status})`);
  }
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  for (;;) {
    let chunk;
    try { chunk = await reader.read(); }
    catch (error) {
      if (error.name === "TimeoutError" || error.name === "AbortError") throw error;
      throw unavailable(error.message);
    }
    if (chunk.done) throw unavailable("The stream ended before the answer");
    buffer += chunk.value;
    let end;
    while ((end = buffer.indexOf("\n\n")) >= 0) {
      const block = buffer.slice(0, end);
      buffer = buffer.slice(end + 2);
      const kind = /^event: (.*)$/m.exec(block)?.[1];
      const data = /^data: (.*)$/m.exec(block)?.[1];
      if (!kind || data === undefined) continue;
      const payload = JSON.parse(data);
      if (kind === "stage") {
        if (STAGE_STATUS[payload.stage]) onStatus(payload.stage, payload.state);
      } else if (kind === "result") {
        reader.cancel().catch(() => {});
        return payload;
      } else if (kind === "error") {
        throw Object.assign(new Error(payload.detail || "Request failed"), { status: payload.status });
      }
    }
  }
}

function resetConversationState() {
  agentConversationId = crypto.randomUUID();
  reportConversationId = crypto.randomUUID();
  sessionTurns = [];
  generalConversationId = crypto.randomUUID();
  generalTurns = [];
  $("#answer-panel").replaceChildren();
  $("#answer-panel").hidden = true;
  $("#general-chat-transcript").replaceChildren();
  $("#general-chat-transcript").hidden = true;
  $("#general-chat-welcome").hidden = false;
  $("#report-agent-question").value = "";
  $("#report-agent-template").value = "";
  updateReportFormatVisibility();
  $("#report-agent-status").textContent = "";
  delete $("#report-agent-status").dataset.state;
  $("#question").value = "";
}

function clearExpiredSession() {
  sessionGeneration += 1;
  sessionSubject = null;
  currentUser = null;
  clearInvoiceReviewCaches();
  resetConversationState();
  $("#login-view").hidden = false;
  $("#workspace").hidden = true;
  $("#login-brand-sidebar").hidden = false;
  $("#user-badge").hidden = true;
  $("#logout-button").hidden = true;
}

async function loadWorkspace(user) {
  chooseBackend();
  backendTimer ||= setInterval(chooseBackend, 180_000);
  if (sessionSubject !== user.username) {
    sessionGeneration += 1;
    clearInvoiceReviewCaches();
    sessionSubject = user.username;
    resetConversationState();
  }
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
  if (["admin", "document_uploader", "document_processing_owner"].includes(user.role)) {
    const roles = Object.keys(UPLOAD_ROLE_LABELS);
    $("#upload-role-options").innerHTML = roles.map((role) => {
      const [label, description] = UPLOAD_ROLE_LABELS[role];
      return `<label class="upload-role-option"><input type="checkbox" name="allowed_roles" value="${escapeHtml(role)}"><span><strong>${escapeHtml(label)}</strong><small>${escapeHtml(description)}</small></span></label>`;
    }).join("");
    $("#upload-role-options").querySelectorAll('input[name="allowed_roles"]').forEach((input) => {
      input.addEventListener("change", updateUploadRoleSelection);
    });
    updateUploadRoleSelection();
    $("#upload-section").hidden = false;
    $("#upload-button").disabled = false;
    const canSaveParserOutput = user.role === "document_processing_owner";
    $("#parser-handoff-button").hidden = !canSaveParserOutput;
    $("#parser-handoff-button").disabled = !canSaveParserOutput;
  }
  if (user.role === "admin") {
    void refreshKnowledgeDocuments().catch((error) => {
      $("#knowledge-documents-status").textContent = `Could not load knowledge-base files: ${error.message}`;
    });
  }
  if (["admin", "document_uploader", "document_processing_owner"].includes(user.role)) {
    void refreshInvoiceReview().catch((error) => {
      $("#invoice-review-status").textContent = `Could not load invoices: ${error.message}`;
    });
  }
  $("#access-matrix").replaceChildren();
  $("#connection-status").textContent = "Knowledge base connected";
  $("#user-badge").textContent = `${user.username} (${user.role})`;
  $("#account-initial").textContent = (user.username || "?").charAt(0).toUpperCase();
  $("#user-badge").hidden = false;
  $("#logout-button").hidden = false;
  $(".intro").hidden = user.role === "document_processing_owner";
  $(".agent-overview").hidden = ["document_processing_owner", "document_uploader"].includes(user.role);
  $(".stats").hidden = user.role === "document_processing_owner";
  const canUseAnalytics = ["admin", "finance_analyst", "sustainability_analyst", "operations", "executive"].includes(user.role);
  ["#analytics-agent-card", "#inventory-agent-card", "#report-agent-card", "#report-agent-form-section"].forEach((selector) => {
    $(selector).hidden = !canUseAnalytics;
  });
  ["sql"].forEach((mode) => {
    $("#agent-mode option[value='" + mode + "']").hidden = !canUseAnalytics;
  });
  if (!canUseAnalytics && $("#agent-mode").value === "sql") {
    $("#agent-mode").value = "knowledge";
  }
  if (user.role !== "document_processing_owner") {
    await loadCorpusStats();
  }
  try {
    if (user.role === "admin") {
      const access = await api("/api/admin/access-matrix");
      const permissions = [...new Set(access.roles.flatMap((role) => role.permissions))];
      const yes = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 12.5 4 4 8-9"/></svg>';
      $("#access-matrix").innerHTML = `<div class="access-table-wrap"><table class="access-table">
        <caption class="visually-hidden">Workspace permissions by role</caption>
        <thead><tr><th scope="col">Role</th>${permissions.map((permission) => `<th scope="col">${escapeHtml(displayName(PERMISSION_NAMES, permission))}</th>`).join("")}</tr></thead>
        <tbody>${access.roles.map((role) => `<tr><th scope="row">${escapeHtml(displayName(ROLE_NAMES, role.role))}</th>${permissions.map((permission) => role.permissions.includes(permission)
          ? `<td class="is-allowed">${yes}<span class="visually-hidden">Allowed</span></td>`
          : '<td class="is-denied"><span aria-hidden="true">–</span><span class="visually-hidden">Not allowed</span></td>').join("")}</tr>`).join("")}</tbody>
      </table></div>`;
      $("#admin-section").hidden = false;
      $("#monitoring-section").hidden = false;
      await refreshAgentMonitoring();
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
  const deleteButton = event.target.closest("[data-knowledge-delete]");
  if (deleteButton) {
    const documentId = deleteButton.dataset.knowledgeDelete;
    const title = deleteButton.dataset.title;
    if (!(await confirmDialog({ title: `Delete “${title}” permanently?`, message: "This removes the original file, its parser output and its indexed passages. It cannot be undone.", confirmLabel: "Delete permanently", danger: true }))) return;
    deleteButton.disabled = true;
    try {
      const result = await api(`/api/admin/knowledge-documents/${encodeURIComponent(documentId)}`, { method: "DELETE" });
      await refreshKnowledgeDocuments();
      $("#knowledge-documents-status").textContent = result.source_file_removed
        ? `Permanently deleted “${title}” and its source file.`
        : `Deleted “${title}” from the knowledge base, but private-file cleanup failed. Check application logs.`;
    } catch (error) {
      $("#knowledge-documents-status").textContent = error.message;
      deleteButton.disabled = false;
    }
    return;
  }
  if (event.target.closest("[data-close-knowledge-review]")) {
    activeKnowledgeReview = null;
    renderKnowledgeDocuments();
    return;
  }
  const reviewButton = event.target.closest("[data-review-elements]");
  if (reviewButton) {
    const documentId = reviewButton.dataset.reviewElements;
    if (activeKnowledgeReview?.document_id === documentId) {
      activeKnowledgeReview = null;
      renderKnowledgeDocuments();
      return;
    }
    activeKnowledgeReview = { document_id: documentId, status: "loading" };
    renderKnowledgeDocuments();
    try {
      const output = await api(`/api/admin/knowledge-documents/${encodeURIComponent(documentId)}/processing-output`);
      if (activeKnowledgeReview?.document_id === documentId) {
        activeKnowledgeReview = { document_id: documentId, output };
        renderKnowledgeDocuments();
      }
    } catch (error) {
      if (activeKnowledgeReview?.document_id === documentId) {
        activeKnowledgeReview = { document_id: documentId, error: error.message };
        renderKnowledgeDocuments();
      }
    }
    return;
  }
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
  const confirmed = await confirmDialog(active
    ? { title: "Remove this source from AI retrieval?", message: "Answers will stop using it. The original file and its parser output are kept, so you can restore it later.", confirmLabel: "Remove from AI retrieval", danger: true }
    : { title: "Restore this source to AI retrieval?", message: "Answers can use it again for the roles allowed to read it.", confirmLabel: "Restore" });
  if (!confirmed) return;
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
  const intent = form.elements.namedItem("intent").value;
  const parserLabel = intent === "document" ? "Docling" : intent === "invoice" ? "Docling OCR + Qwen invoice extraction" : "Vintern image caption";
  $("#ocr-test-status").textContent = `Running ${parserLabel}…`;
  try {
    let result = await api("/api/upload-tests", {method:"POST", body:new FormData(form)});
    if (result.status === "processing") {
      const runId = result.run_id;
      const startedAt = Date.now();
      while (result.status === "processing") {
        await new Promise((resolve) => window.setTimeout(resolve, 3000));
        result = await api(`/api/upload-tests/${encodeURIComponent(runId)}`);
        if (result.status === "processing") {
          const elapsedSeconds = Math.floor((Date.now() - startedAt) / 1000);
          const runningLabel = intent === "invoice"
            ? "Docling OCR + Qwen invoice extraction"
            : intent === "image_caption" ? "Vintern image caption" : "Docling";
          $("#ocr-test-status").textContent = `${runningLabel} is still processing (${formatDuration(elapsedSeconds * 1000)})…`;
        } else if (result.status === "failed") {
          throw new Error(result.error || "Vintern processing failed");
        }
      }
    }
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
  clearExpiredSession();
  await api("/api/auth/logout", { method: "POST" }).catch(() => {});
  $("#workspace").hidden = true;
  $("#login-view").hidden = false;
  $("#login-brand-sidebar").hidden = false;
  $("#user-badge").hidden = true;
  $("#logout-button").hidden = true;
  activeTab = "general-chat";
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

// The fixed pipeline a user sees while waiting. Raw server stages map onto these steps, so the list
// keeps its shape from the first second instead of growing line by line.
const PROGRESS_PHASES = [
  { label: "Choosing the right agent", stages: ["routing"], modes: ["auto"] },
  { label: "Searching your documents in Vietnamese and English",
    stages: ["knowledge_search_planning", "query_translation", "embedding", "database_retrieval", "retrieval_fusion"],
    modes: ["auto", "knowledge"] },
  { label: "Ranking the best passages", stages: ["reranking"], modes: ["auto", "knowledge"] },
  { label: "Querying the sales data", stages: ["sql_ambiguity_check", "sql_planning", "sql_execution"], modes: ["sql"], whenSeen: true },
  { label: "Writing a cited answer", stages: ["answer_generation", "answer_synthesis"], modes: ["auto", "knowledge", "sql"] },
  { label: "Checking every claim against its source", stages: ["claim_verification"], modes: ["auto", "knowledge"] },
];
const PHASE_STATE_TEXT = { done: "done", active: "in progress", failed: "failed", skipped: "skipped", pending: "waiting" };

function progressPhases(progress = [], mode = "auto") {
  const flow = ["auto", "knowledge", "sql"].includes(mode) ? mode : "auto";
  const seen = new Map(progress.map((item) => [item.stage, item.state]));
  const phases = PROGRESS_PHASES.filter((phase) => phase.modes.includes(flow)
    || (phase.whenSeen && phase.stages.some((stage) => seen.has(stage))));
  const reached = phases.map((phase) => phase.stages.filter((stage) => seen.has(stage)).map((stage) => seen.get(stage)));
  const furthest = reached.reduce((last, states, index) => (states.length ? index : last), -1);
  return phases.map((phase, index) => {
    const states = reached[index];
    let state = "pending";
    if (states.includes("failed")) state = "failed";
    else if (index < furthest) state = states.length ? "done" : "skipped";
    else if (index === furthest) state = states.every((value) => value === "completed") ? "done" : "active";
    return { label: phase.label, state };
  });
}

// The visible headline stays steady (the list already shows the step); the live text names the step.
function progressHeadline(phases, note) {
  if (note) return note;
  if (phases.some((phase) => phase.state === "failed")) return "A step failed; finishing what it can";
  if (phases.length && phases.every((phase) => phase.state === "done" || phase.state === "skipped")) return "Finishing the answer";
  return phases.some((phase) => phase.state !== "pending") ? "Working on your answer" : "Sending your question";
}

function progressAnnouncement(phases, note) {
  return phases.find((phase) => phase.state === "active")?.label || progressHeadline(phases, note);
}

function elapsedNote(startedAt) {
  const seconds = Math.max(0, Math.floor((Date.now() - (startedAt || Date.now())) / 1000));
  return `${seconds} s · ${seconds > 25 ? "taking longer than usual" : "usually 10–20 s"}`;
}

// The headline is the only live text; the step list and the per-second clock stay silent for screen readers.
function renderSkeletonAnswer(panel, turn) {
  const phases = progressPhases(turn.progress, turn.mode);
  panel.hidden = false;
  panel.innerHTML = `
    <section class="agent-progress" aria-busy="true">
      <div class="agent-progress-head">
        <strong class="stage-status">${escapeHtml(progressHeadline(phases, turn.note))}</strong>
        <span class="visually-hidden agent-progress-live" role="status">${escapeHtml(progressAnnouncement(phases, turn.note))}</span>
        <span class="agent-progress-time" aria-hidden="true">${escapeHtml(elapsedNote(turn.startedAt))}</span>
        ${turn.abort ? '<button type="button" class="secondary-button agent-progress-stop">Stop</button>' : ""}
      </div>
      <ol class="agent-progress-steps" aria-live="off" aria-label="Answer progress">${renderProgressSteps(phases)}</ol>
    </section>
  `;
}

function renderProgressSteps(phases) {
  return phases.map((phase) => `
    <li class="agent-progress-step is-${phase.state}"${phase.state === "active" ? ' aria-current="step"' : ""}>
      <span class="agent-progress-marker" aria-hidden="true"></span>
      <span class="agent-progress-label">${escapeHtml(phase.label)}<span class="visually-hidden">, ${PHASE_STATE_TEXT[phase.state]}</span></span>
    </li>`).join("");
}

// Steps change state in place, so a finished step's tick animates once rather than on every event.
function updatePendingProgress(turn) {
  const entry = document.querySelector(`[data-turn-id="${turn.id}"]`);
  if (!entry) return;
  const phases = progressPhases(turn.progress, turn.mode);
  const heading = entry.querySelector(".stage-status");
  const steps = entry.querySelector(".agent-progress-steps");
  const live = entry.querySelector(".agent-progress-live");
  if (heading) swapStageText(heading, progressHeadline(phases, turn.note));
  if (live && live.textContent !== progressAnnouncement(phases, turn.note)) live.textContent = progressAnnouncement(phases, turn.note);
  if (!steps) return;
  if (steps.children.length !== phases.length) {
    steps.innerHTML = renderProgressSteps(phases);
    return;
  }
  phases.forEach((phase, index) => {
    const item = steps.children[index];
    const className = `agent-progress-step is-${phase.state}`;
    if (item.className === className) return;
    item.className = className;
    item.toggleAttribute("aria-current", phase.state === "active");
    if (phase.state === "active") item.setAttribute("aria-current", "step");
    const hint = item.querySelector(".visually-hidden");
    if (hint) hint.textContent = `, ${PHASE_STATE_TEXT[phase.state]}`;
  });
}

function updatePendingElapsed(turn) {
  const clock = document.querySelector(`[data-turn-id="${turn.id}"] .agent-progress-time`);
  if (clock) clock.textContent = elapsedNote(turn.startedAt);
}

// Stop ends the wait in the browser; a request the server already accepted may still finish there.
document.addEventListener("click", (event) => {
  const stop = event.target.closest(".agent-progress-stop");
  if (!stop) return;
  const id = stop.closest("[data-turn-id]")?.dataset.turnId;
  const turn = [...sessionTurns, ...generalTurns].find((item) => item.id === id);
  if (!turn?.abort) return;
  turn.stopped = true;
  stop.disabled = true;
  turn.abort.abort(new DOMException("Stopped by the user", "AbortError"));
});

// A withheld or uncovered answer offers the next step: the same question back in the box to narrow it.
document.addEventListener("click", (event) => {
  const button = event.target.closest(".answer-rephrase");
  if (!button) return;
  const id = button.closest("[data-turn-id]")?.dataset.turnId;
  const turn = [...sessionTurns, ...generalTurns].find((item) => item.id === id);
  const inChat = Boolean(button.closest("#general-chat-transcript"));
  const input = inChat ? $("#general-chat-question") : $("#question");
  if (!input) return;
  if (turn?.question) input.value = turn.question;
  if (inChat) resizeGeneralChatComposer();
  input.scrollIntoView({ behavior: "smooth", block: "center" });
  input.focus({ preventScroll: true });
  input.setSelectionRange(input.value.length, input.value.length);
});

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
    $("#report-fold").open = true;
    $("#report-agent-question").focus();
  }
});

function renderSessionTranscript(shouldScroll = false) {
  renderChatTranscript($("#answer-panel"), sessionTurns, shouldScroll);
}

function renderGeneralChatTranscript(shouldScroll = false) {
  renderChatTranscript($("#general-chat-transcript"), generalTurns, shouldScroll);
  $("#general-chat-welcome").hidden = generalTurns.length > 0;
}

// Pointing at a citation marks the sentence of its source passage that best matches the claim.
const citeWords = (text) => text.toLowerCase().normalize("NFC").match(/[\p{L}\p{N}]+/gu) || [];
function citedClaim(ref) {
  let text = "";
  let node = ref.closest(".cite-glue") || ref;
  for (node = node.previousSibling; node && node.nodeName !== "BR" && !node.classList?.contains("cite-glue"); node = node.previousSibling) {
    text = (node.textContent || "") + text;
  }
  return text;
}
function clearCitedSentence(turn) {
  turn.querySelectorAll(".citation.is-cited").forEach((card) => {
    card.classList.remove("is-cited");
    const passage = card.querySelector(":scope > p");
    if (passage?.dataset.plain !== undefined) { passage.textContent = passage.dataset.plain; delete passage.dataset.plain; }
  });
  turn.querySelectorAll(".cite-ref.is-pointed").forEach((ref) => ref.classList.remove("is-pointed"));
}
function markCitedSentence(ref) {
  const turn = ref.closest(".chat-turn");
  const card = turn?.querySelector(`.citation[data-cite-id="${CSS.escape(ref.dataset.cite)}"]`);
  const passage = card?.querySelector(":scope > p");
  if (!passage || card.closest("[hidden]")) return;
  clearCitedSentence(turn);
  const plain = passage.textContent;
  const sentences = plain.match(/[^.;!?]+[.;!?]*\s*/g) || [plain];
  const claim = new Set(citeWords(citedClaim(ref)));
  let best = 0;
  let bestScore = 0;
  sentences.forEach((sentence, index) => {
    const words = citeWords(sentence);
    const score = words.filter((word) => claim.has(word)).length / Math.sqrt(words.length || 1);
    if (score > bestScore) { bestScore = score; best = index; }
  });
  if (!bestScore) return;
  passage.dataset.plain = plain;
  passage.innerHTML = sentences.map((sentence, index) => index === best ? `<mark class="cited-sentence">${escapeHtml(sentence)}</mark>` : escapeHtml(sentence)).join("");
  card.classList.add("is-cited");
  ref.classList.add("is-pointed");
}
for (const [on, off] of [["mouseover", "mouseout"], ["focusin", "focusout"]]) {
  $("#general-chat-transcript").addEventListener(on, (event) => {
    const ref = event.target.closest(".cite-ref");
    if (ref) markCitedSentence(ref);
  });
  $("#general-chat-transcript").addEventListener(off, (event) => {
    const ref = event.target.closest(".cite-ref");
    if (ref && !ref.contains(event.relatedTarget)) clearCitedSentence(ref.closest(".chat-turn"));
  });
}

function renderChatTranscript(root, turns, shouldScroll) {
  root.replaceChildren();
  root.hidden = turns.length === 0;
  for (const turn of turns) {
    const entry = document.createElement("article");
    entry.className = "chat-turn";
    entry.dataset.turnId = turn.id;
    entry.innerHTML = `<div class="chat-turn-question"><span>${escapeHtml(displayName({ auto: "Auto", knowledge: "Knowledge", sql: "Analytics" }, turn.mode))}</span><p>${escapeHtml(turn.question)}</p></div>`;
    const response = document.createElement("div");
    response.className = "answer-panel chat-turn-response";
    entry.append(response);
    root.append(entry);
    if (turn.state === "pending") renderSkeletonAnswer(response, turn);
    else if (turn.state === "stopped") response.innerHTML = '<p class="answer-stopped">You stopped this answer. Ask again whenever you are ready.</p>';
    else if (turn.state === "error") response.innerHTML = `<p class="error-message" role="alert">${escapeHtml(turn.error)}. Please check service configuration or connection.</p>`;
    else if (turn.result) {
      renderAgentResult(turn.result, response, false);
      attachFeedback(response, turn);
      if (turn.typeOut) {
        turn.typeOut = false;
        typeOutText(response.querySelector(".answer-text"),
          [...response.querySelectorAll(".citations, .citations .citation")]);
      }
    }
  }
  if (shouldScroll) root.lastElementChild?.scrollIntoView({ behavior: "smooth", block: "start" });
}

$("#new-conversation").addEventListener("click", () => {
  agentConversationId = crypto.randomUUID();
  sessionTurns = [];
  $("#answer-panel").replaceChildren();
  $("#answer-panel").hidden = true;
  $("#question").value = "";
});

let clearedChat = null;
let clearedChatTimer = null;
$("#chat-undo-button").addEventListener("click", () => {
  if (!clearedChat) return;
  ({ id: generalConversationId, turns: generalTurns } = clearedChat);
  clearedChat = null;
  clearTimeout(clearedChatTimer);
  $("#chat-undo").hidden = true;
  renderGeneralChatTranscript();
});
$("#new-general-chat").addEventListener("click", () => {
  if (generalTurns.length && !generalTurns.some((turn) => turn.state === "pending")) {
    clearedChat = { id: generalConversationId, turns: generalTurns };
    $("#chat-undo").hidden = false;
    clearTimeout(clearedChatTimer);
    clearedChatTimer = setTimeout(() => { clearedChat = null; $("#chat-undo").hidden = true; }, 8000);
  }
  generalConversationId = crypto.randomUUID();
  generalTurns = [];
  $("#general-chat-question").value = "";
  resizeGeneralChatComposer();
  renderGeneralChatTranscript();
  $("#general-chat-question").focus();
});

async function sendChatMessage({ question, mode, button, input, state, render }) {
  const requestConversationId = state.getId();
  const requestGeneration = sessionGeneration;
  const requestSubject = sessionSubject;
  if (!question) return;
  const turn = { id: crypto.randomUUID(), mode, question, state: "pending", startedAt: Date.now(), abort: new AbortController() };
  state.turns.push(turn);
  state.turns = state.turns.slice(-20);
  input.value = "";
  if (input.id === "general-chat-question") resizeGeneralChatComposer();
  render(true);
  const initialButton = button.innerHTML;
  button.disabled = true;
  if (button.id === "general-chat-send") {
    button.setAttribute("aria-busy", "true");
    button.setAttribute("aria-label", "Sending…");
  } else {
    button.innerHTML = "<span>Working…</span>";
  }
  const timeout = setTimeout(() => turn.abort?.abort(new DOMException("The request timed out", "TimeoutError")), 135_000);
  const ticker = setInterval(() => updatePendingElapsed(turn), 1000);
  try {
    const body = JSON.stringify({
      question, agent_mode: mode, retrieval_method: "translated_hybrid_rerank",
      conversation_id: requestConversationId,
    });
    const signal = turn.abort.signal;
    const showStage = (stage, state) => {
      turn.progress ||= [];
      const step = turn.progress.find((item) => item.stage === stage);
      if (step) step.state = state;
      else turn.progress.push({ stage, state });
      updatePendingProgress(turn);
    };
    let data;
    try {
      data = await askAgentStream(body, signal, showStage);
    } catch (error) {
      if (!error.streamUnavailable) throw error;
      turn.note = "Waiting for the agent to finish";
      updatePendingProgress(turn);
      data = await api("/api/agents/chat", { method: "POST", body, signal });
    }
    if (state.getId() !== requestConversationId || sessionGeneration !== requestGeneration || sessionSubject !== requestSubject) return;
    $("#connection-status").textContent = "Services connected";
    $(".status-dot").classList.add("connected");
    turn.result = data;
    turn.state = "complete";
    turn.typeOut = true;
  } catch (error) {
    if (state.getId() !== requestConversationId || sessionGeneration !== requestGeneration || sessionSubject !== requestSubject) return;
    if (turn.stopped) turn.state = "stopped";
    else {
      turn.error = error.name === "TimeoutError" ? "The request timed out. No answer was received; try again or choose a specialist" : error.message;
      turn.state = "error";
    }
  } finally {
    clearTimeout(timeout);
    clearInterval(ticker);
    turn.abort = null;
    button.disabled = false;
    if (button.id === "general-chat-send") {
      button.removeAttribute("aria-busy");
      button.setAttribute("aria-label", "Send message");
    } else button.innerHTML = initialButton;
    if (state.turns.includes(turn)) render(false);
    // A reply that arrived after the conversation was reset stays pending and is never announced.
    if (state.turns.includes(turn) && turn.state !== "pending") announceTurn(turn);
  }
}

// One short status line per answer (the panel itself is not a live region, so sources are not read out in bulk).
function announceTurn(turn) {
  const announcer = $("#answer-announcer");
  if (!announcer) return;
  const entry = document.querySelector(`[data-turn-id="${turn.id}"]`);
  const outcome = entry?.querySelector(".answer-verified, .answer-status")?.textContent;
  const sources = entry?.querySelectorAll(".citation").length || 0;
  announcer.textContent = turn.state === "stopped" ? "Answer stopped"
    : turn.state === "error" ? "The answer could not be completed"
      : `Answer ready${outcome ? `. ${outcome}` : ""}${sources ? `. ${sources} source${sources === 1 ? "" : "s"}` : ""}`;
}

// Enter sends, as in a chat; Shift + Enter keeps a new line, and IME composition is left alone.
$("#question").addEventListener("keydown", (event) => {
  if (event.key !== "Enter" || event.shiftKey || event.isComposing) return;
  event.preventDefault();
  if (!$("#ask-button").disabled) $("#ask-form").requestSubmit();
});

$("#ask-form").addEventListener("submit", (event) => {
  event.preventDefault();
  return sendChatMessage({
    question: $("#question").value.trim(), mode: $("#agent-mode").value,
    button: $("#ask-button"), input: $("#question"),
    state: { getId: () => agentConversationId, get turns() { return sessionTurns; }, set turns(value) { sessionTurns = value; } }, render: renderSessionTranscript,
  });
});

$("#general-chat-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const input = $("#general-chat-question");
  sendChatMessage({
    question: input.value.trim(), mode: $("#general-chat-mode").value, button: $("#general-chat-send"), input,
    state: { getId: () => generalConversationId, get turns() { return generalTurns; }, set turns(value) { generalTurns = value; } },
    render: renderGeneralChatTranscript,
  });
});

function resizeGeneralChatComposer() {
  const input = $("#general-chat-question");
  input.style.height = "auto";
  input.style.height = `${Math.min(input.scrollHeight, 180)}px`;
}

$("#general-chat-question").addEventListener("input", resizeGeneralChatComposer);
$("#general-chat-prompts").addEventListener("click", (event) => {
  const prompt = event.target.closest("[data-general-chat-prompt]");
  if (!prompt) return;
  $("#general-chat-question").value = prompt.dataset.generalChatPrompt;
  resizeGeneralChatComposer();
  $("#general-chat-form").requestSubmit();
});

$("#general-chat-question").addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing && event.keyCode !== 229) {
    event.preventDefault();
    $("#general-chat-form").requestSubmit();
  }
});

function updateReportFormatVisibility() {
  const hasTemplate = Boolean($("#report-agent-template").files[0]);
  $("#report-agent-format-field").hidden = hasTemplate;
}

$("#report-agent-template").addEventListener("change", updateReportFormatVisibility);
updateReportFormatVisibility();

function confirmReportPlan(detail) {
  return new Promise((resolve) => {
    const dialog = document.createElement("dialog");
    dialog.className = "report-plan-dialog";
    dialog.setAttribute("aria-labelledby", "report-plan-title");
    const title = document.createElement("h2");
    title.id = "report-plan-title";
    title.textContent = "Review report scope and structure";
    dialog.append(title);
    for (const reason of [...(detail.mismatch_reasons || []), ...(detail.unsupported_requirements || [])]) {
      const paragraph = document.createElement("p");
      paragraph.textContent = reason;
      dialog.append(paragraph);
    }
    if (detail.suggested_structure?.length) {
      const paragraph = document.createElement("p");
      paragraph.textContent = "Suggested sections: " + detail.suggested_structure.map((section) => section.heading).join("; ");
      dialog.append(paragraph);
    }
    const finish = (choice) => { dialog.close(); dialog.remove(); resolve(choice); };
    const choices = detail.template_decision_required
      ? [["Use suggested structure", "suggested"], ["Continue with uploaded template", "uploaded"]]
      : [["Generate supported report", null]];
    for (const [label, templateChoice] of choices) {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = detail.scope_decision_required && templateChoice ? label + " (supported scope only)" : label;
      button.addEventListener("click", () => finish({ templateChoice, acceptSupportedScope: Boolean(detail.scope_decision_required) }));
      dialog.append(button);
    }
    const cancel = document.createElement("button");
    cancel.type = "button";
    cancel.textContent = "Cancel";
    cancel.addEventListener("click", () => finish(null));
    dialog.addEventListener("cancel", (event) => { event.preventDefault(); finish(null); });
    dialog.append(cancel);
    document.body.append(dialog);
    dialog.showModal();
  });
}

$("#report-agent-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const requestConversationId = reportConversationId;
  const requestGeneration = sessionGeneration;
  const requestSubject = sessionSubject;
  const button = $("#report-agent-submit");
  const status = $("#report-agent-status");
  const template = $("#report-agent-template").files[0];
  const formData = new FormData();
  formData.append("question", $("#report-agent-question").value.trim());
  formData.append("source_mode", $("#report-agent-source-mode").value);
  if (template) formData.append("template", template);
  else formData.append("output_format", $("#report-agent-output-format").value);
  formData.set('conversation_id', requestConversationId);
  button.disabled = true;
  delete status.dataset.state;
  status.textContent = "Generating report from authorized sources...";
  try {
    let response;
    for (let attempt = 0; attempt < 3; attempt++) {
      response = await backendFetch("/api/agents/report", {
        method: "POST", body: formData, credentials: "same-origin",
        headers: { "ngrok-skip-browser-warning": "1" },
      });
      if (reportConversationId !== requestConversationId || sessionGeneration !== requestGeneration || sessionSubject !== requestSubject) return;
      if (response.status === 401) {
        clearExpiredSession();
        throw new Error("Sign in to continue");
      }
      if (response.status !== 409) break;
      const payload = await response.json();
      if (!payload.detail?.confirmation_required) throw new Error("Unexpected report confirmation response.");
      const choice = await confirmReportPlan(payload.detail);
      if (reportConversationId !== requestConversationId || sessionGeneration !== requestGeneration || sessionSubject !== requestSubject) return;
      if (!choice) { status.textContent = "Report generation cancelled."; return; }
      if (choice.templateChoice) formData.set("template_choice", choice.templateChoice);
      if (choice.acceptSupportedScope) formData.set("accept_supported_scope", "true");
      if (attempt === 2) throw new Error("The report plan changed repeatedly. Refine the request and try again.");
    }
    if (reportConversationId !== requestConversationId || sessionGeneration !== requestGeneration || sessionSubject !== requestSubject) return;
    if (!response.ok) {
      let detail = "Report request failed (HTTP " + response.status + ")";
      try {
        const payload = await response.json();
        const reportError = typeof payload.detail === "object" ? payload.detail : null;
        if (reportError?.status === "unsupported") {
          status.dataset.state = "warning";
          status.textContent = (reportError.limitations || []).join("; ");
          return;
        }
        if (reportError?.status === "clarification_required") {
          status.dataset.state = "warning";
          status.textContent = `Clarification needed: ${reportError.clarification || reportError.detail || "Please refine the decision question."}`;
          return;
        }
        const message = reportError?.detail || reportError?.message || payload.detail;
        if (message) detail = typeof message === "string" ? message : JSON.stringify(message);
        if (reportError?.limitations?.length) detail += ` Limitations: ${reportError.limitations.join("; ")}`;
      } catch {}
      throw new Error(detail);
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    const disposition = response.headers.get("Content-Disposition") || "";
    const filename = disposition.match(/filename="?([^";]+)"?/i)?.[1];
    const extension = $("#report-agent-output-format").value === "docx" ? ".docx" : ".md";
    link.download = filename || `report${extension}`;
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    const reportStatus = response.headers.get("X-Report-Status");
    status.dataset.state = reportStatus === "partial" ? "warning" : "success";
    status.textContent = reportStatus === "partial"
      ? "Partial report downloaded. Review its limitations before using it."
      : "Report generated and downloaded.";
    try {
      const summary = JSON.parse(response.headers.get("X-Report-Summary") || "null");
      if (summary) {
        status.textContent += ` Sections: ${summary.complete} complete, ${summary.unavailable} unavailable, ${summary.failed} failed. `
          + `${summary.omitted_from_narrative} evidence items omitted from narrative; review detail tables and coverage.`;
        if (summary.reasons?.length) status.textContent += " Reasons: " + summary.reasons.join("; ") + ".";
      }
    } catch {}
  } catch (error) {
    if (reportConversationId !== requestConversationId || sessionGeneration !== requestGeneration || sessionSubject !== requestSubject) return;
    status.dataset.state = "error";
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
const INVOICE_UPLOAD_EXTENSIONS = new Set([".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff"]);

function validateUploadFile(file, invoiceMode = false) {
  if (!file) return "Choose a document to upload.";
  const extension = "." + file.name.split(".").pop().toLocaleLowerCase();
  const supported = invoiceMode ? INVOICE_UPLOAD_EXTENSIONS : SUPPORTED_UPLOAD_EXTENSIONS;
  if (!supported.has(extension)) return invoiceMode
    ? "Invoice extraction supports PDF, PNG, JPG and TIF files."
    : "This file type is not supported. Choose PDF, DOCX, PPTX, XLSX, CSV, TXT, MD, PNG, JPG or TIF.";
  if (file.size > MAX_UPLOAD_BYTES) return "The file is larger than the 50 MiB upload limit.";
  return "";
}

function updateUploadKind() {
  const invoiceMode = $("#upload-kind").value === "invoice";
  $("#upload-access-step").hidden = invoiceMode;
  $("#invoice-model-field").hidden = !invoiceMode;
  $("#upload-title").required = !invoiceMode;
  $("#upload-title").closest(".upload-field").hidden = invoiceMode;
  $("#upload-file-label").textContent = invoiceMode ? "Invoice file" : "Document file";
  $("#upload-file").accept = invoiceMode
    ? ".pdf,.png,.jpg,.jpeg,.tif,.tiff"
    : ".pdf,.docx,.pptx,.xlsx,.csv,.txt,.md,.png,.jpg,.jpeg,.tif,.tiff";
  $("#upload-kind-help").textContent = invoiceMode
    ? "Upload an invoice for extraction and review in the invoice table."
    : "Knowledge documents are indexed for document Q&A.";
  const file = $("#upload-file").files[0];
  if (file) $("#upload-file-info").textContent = validateUploadFile(file, invoiceMode)
    || `${file.name} · ${(file.size / 1024 / 1024).toFixed(1)} MiB.`;
}

$("#upload-kind").addEventListener("change", updateUploadKind);

$("#upload-file").addEventListener("change", (event) => {
  const file = event.currentTarget.files[0];
  const title = $("#upload-title");
  if (file && title.dataset.userEdited !== "true") {
    title.value = file.name.replace(/\.[^.]+$/, "").replace(/[_-]+/g, " ").trim();
  }
  const invoiceMode = $("#upload-kind").value === "invoice";
  const error = validateUploadFile(file, invoiceMode);
  $("#upload-file-info").textContent = error || file.name + " · " + (file.size / 1024 / 1024).toFixed(1) + " MiB. "
    + (invoiceMode ? "The source stays private and is available in the invoice table after processing." : "The original stays private; review OCR output in Document Processing.");
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
  const invoiceMode = $("#upload-kind").value === "invoice";
  const file = $("#upload-file").files[0];
  const roles = [...form.querySelectorAll('input[name="allowed_roles"]:checked')].map((input) => input.value);
  const fileError = validateUploadFile(file, invoiceMode);
  if (fileError || (!invoiceMode && !roles.length)) {
    const status = $("#upload-status");
    $("#upload-status-wrap").hidden = false;
    $("#upload-progress").hidden = true;
    status.dataset.state = "error";
    status.textContent = fileError || "Select at least one role authorized to retrieve this document.";
    return;
  }
  const body = new FormData();
  body.append("file", file);
  if (invoiceMode) {
    body.append("model_provider", $("#invoice-model").value);
  } else {
    for (const name of ["title"]) {
      const value = form.elements[name].value.trim();
      if (value) body.append(name, value);
    }
    body.append("document_type", "knowledge_document");
    body.append("domain", "general_knowledge");
    roles.forEach((role) => body.append("allowed_roles", role));
  }
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
  status.textContent = invoiceMode
    ? "Uploading invoice and running OCR and extraction. Keep this tab open."
    : parserHandoff
    ? "Uploading, extracting and saving parser output. Chunking and indexing run downstream. Keep this tab open."
    : "Uploading, extracting text/OCR, chunking and indexing. Keep this tab open.";
  updateProcessingTime();
  const processingTimer = window.setInterval(updateProcessingTime, 1000);
  let result;
  try {
    result = await api(invoiceMode ? "/api/invoices/upload" : parserHandoff ? "/api/documents/parser-handoff" : "/api/documents/upload", { method: "POST", body, headers: {} });
    if (invoiceMode) {
      while (result.processing_status === "processing") {
        const elapsedSeconds = Math.floor((Date.now() - processingStartedAt) / 1000);
        status.textContent = `Invoice ${result.invoice_id} is running OCR and extraction (${formatDuration(elapsedSeconds * 1000)}). You can leave this tab open; the saved invoice remains available if you return later.`;
        await new Promise((resolve) => window.setTimeout(resolve, 3000));
        result = await api(`/api/invoices/${encodeURIComponent(result.invoice_id)}`);
      }
      if (result.processing_status === "failed") {
        throw new Error(`Invoice ${result.invoice_id} was saved, but extraction failed: ${result.error_message || "check backend logs"}`);
      }
      status.dataset.state = "success";
      progress.hidden = true;
      elapsedLabel.hidden = true;
      status.textContent = `Invoice ${result.invoice_id} saved for review in the invoice table. Model: ${result.extraction_model || "unknown"}.`;
      form.reset();
      $("#upload-kind").value = "invoice";
      updateUploadKind();
      updateUploadRoleSelection();
      $("#upload-file-info").textContent = "Choose another invoice to process.";
      try {
        await refreshInvoiceReview(result.invoice_id);
        selectWorkspaceTab("invoice-review");
      } catch (error) {
        $("#invoice-review-status").textContent = `Invoice was saved, but the review queue could not refresh: ${error.message}`;
      }
      return;
    }
    const referenceStatus = parserHandoff
      ? " Parser output is saved in public for the chunking worker; this document is not searchable yet."
      : " Indexed for document Q&A.";
    const pageSummary = result.page_count ? `${formatNumber(result.page_count)} pages` : "File processed";
    const extractionSummary = parserHandoff
      ? `${formatNumber(result.element_count)} parser elements · ${formatNumber(result.table_count)} tables · queued for chunking`
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
    if (invoiceMode) {
      const invoiceId = result?.invoice_id;
      status.dataset.state = invoiceId ? "warning" : "error";
      status.textContent = result?.processing_status === "failed"
        ? `Invoice ${invoiceId} was saved, but extraction failed: ${result.error_message || error.message}`
        : invoiceId
        ? `Invoice ${invoiceId} was saved, but its processing status could not be refreshed: ${error.message}`
        : error.message;
    } else {
      status.dataset.state = result ? "warning" : "error";
      status.textContent = result
        ? `The file was processed successfully as ${result.document_id}, but the workspace could not refresh: ${error.message}`
        : error.message;
    }
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
    const apply = () => {
      if (nextTheme === "dark") {
        document.documentElement.setAttribute("data-theme", "dark");
      } else {
        document.documentElement.removeAttribute("data-theme");
      }
    };
    // The new theme spreads out in a circle from the toggle; plain swap without View Transitions or with reduced motion.
    if (document.startViewTransition && !window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      const box = button.getBoundingClientRect();
      document.documentElement.style.setProperty("--reveal-x", `${box.left + box.width / 2}px`);
      document.documentElement.style.setProperty("--reveal-y", `${box.top + box.height / 2}px`);
      document.startViewTransition(apply);
    } else apply();
    try {
      localStorage.setItem("app_theme", nextTheme);
    } catch {}
  });
}

setupThemeToggle();
setupQuickPrompts();
loadCorpus();

// Confirmations use the app's own dialog instead of the browser's "localhost says" box.
function confirmDialog({ title, message, confirmLabel = "Confirm", danger = false }) {
  const dialog = $("#app-dialog");
  $("#app-dialog-title").textContent = title;
  $("#app-dialog-message").textContent = message;
  const confirm = $("#app-dialog-confirm");
  confirm.textContent = confirmLabel;
  confirm.className = danger ? "danger-button" : "primary-button";
  dialog.returnValue = "";
  return new Promise((resolve) => {
    dialog.addEventListener("close", () => resolve(dialog.returnValue === "confirm"), { once: true });
    dialog.showModal();
    // A destructive choice never sits under the default focus.
    (danger ? dialog.querySelector('[value="cancel"]') : confirm).focus();
  });
}
$("#app-dialog").addEventListener("click", (event) => {
  if (event.target === event.currentTarget) event.currentTarget.close("cancel");
});

// Sidebar width: drag the edge (or use arrow keys on it); double-click resets. Kept per browser.
const SIDEBAR_WIDTH = { min: 220, max: 420, default: 272 };
function setSidebarWidth(width, save = false) {
  const value = Math.round(Math.min(SIDEBAR_WIDTH.max, Math.max(SIDEBAR_WIDTH.min, width)));
  $("#workspace").style.setProperty("--sidebar-w", `${value}px`);
  $("#sidebar-resizer").setAttribute("aria-valuenow", String(value));
  if (save) try { localStorage.setItem("sidebar_width", String(value)); } catch {}
  return value;
}
try { setSidebarWidth(Number(localStorage.getItem("sidebar_width")) || SIDEBAR_WIDTH.default); } catch { setSidebarWidth(SIDEBAR_WIDTH.default); }
$("#sidebar-resizer").setAttribute("aria-valuemin", String(SIDEBAR_WIDTH.min));
$("#sidebar-resizer").setAttribute("aria-valuemax", String(SIDEBAR_WIDTH.max));
$("#sidebar-resizer").addEventListener("pointerdown", (event) => {
  if ($("#workspace").classList.contains("sidebar-collapsed")) return;
  event.preventDefault();
  const handle = event.currentTarget;
  handle.setPointerCapture(event.pointerId);
  $("#workspace").classList.add("is-resizing");
  const move = (e) => setSidebarWidth(e.clientX - $("#workspace").getBoundingClientRect().left);
  const stop = (e) => {
    handle.removeEventListener("pointermove", move);
    $("#workspace").classList.remove("is-resizing");
    setSidebarWidth(e.clientX - $("#workspace").getBoundingClientRect().left, true);
  };
  handle.addEventListener("pointermove", move);
  handle.addEventListener("pointerup", stop, { once: true });
  handle.addEventListener("pointercancel", stop, { once: true });
});
$("#sidebar-resizer").addEventListener("dblclick", () => setSidebarWidth(SIDEBAR_WIDTH.default, true));
$("#sidebar-resizer").addEventListener("keydown", (event) => {
  const step = event.shiftKey ? 40 : 12;
  const now = Number($("#sidebar-resizer").getAttribute("aria-valuenow"));
  const next = { ArrowLeft: now - step, ArrowRight: now + step, Home: SIDEBAR_WIDTH.min, End: SIDEBAR_WIDTH.max }[event.key];
  if (next === undefined) return;
  event.preventDefault();
  setSidebarWidth(next, true);
});

// Keep this preference local to the browser; storage may be disabled.
function setSidebarCollapsed(collapsed) {
  $("#workspace").classList.toggle("sidebar-collapsed", collapsed);
  const toggle = $("#sidebar-toggle");
  toggle.setAttribute("aria-expanded", String(!collapsed));
  toggle.setAttribute("aria-label", collapsed ? "Expand sidebar" : "Collapse sidebar");
  toggle.title = collapsed ? "Expand sidebar" : "Collapse sidebar";
  toggle.firstElementChild.textContent = collapsed ? "›" : "‹";
}
try { setSidebarCollapsed(localStorage.getItem("sidebar_collapsed") === "true"); } catch {}
$("#sidebar-toggle").addEventListener("click", () => {
  const collapsed = !$("#workspace").classList.contains("sidebar-collapsed");
  setSidebarCollapsed(collapsed);
  try { localStorage.setItem("sidebar_collapsed", String(collapsed)); } catch {}
});
