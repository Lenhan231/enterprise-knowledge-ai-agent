const $ = (selector) => document.querySelector(selector);
let analyticsSnapshot = null;
let activeTab = "knowledge";
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

function selectWorkspaceTab(name) {
  const button = $(`[data-tab-target="${name}"]`);
  if (!button || button.hidden) return;
  activeTab = name;
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

function syncWorkspaceTabs() {
  const available = {
    knowledge: true,
    analytics: !$("#analytics-section").hidden,
    processing: !$("#upload-section").hidden,
    access: !$("#admin-section").hidden,
    monitoring: !$("#monitoring-section").hidden,
  };
  document.querySelectorAll(".workspace-tab").forEach((button) => {
    button.hidden = !available[button.dataset.tabTarget];
  });
  if (!available[activeTab]) activeTab = "knowledge";
  selectWorkspaceTab(activeTab);
}

function renderCorpus(data) {
  const companies = new Set(data.documents.map((doc) => doc.company).filter(Boolean));
  $("#company-name").textContent = companies.size || 0;
  $("#document-count").textContent = data.document_count;
  $("#chunk-count").textContent = data.chunk_count.toLocaleString();
  const inFlight = data.documents.filter((doc) => doc.processing_status !== "ready").length;
  $("#processing-count").textContent = inFlight;
  $("#source-count").textContent = `${data.document_count} registered source${data.document_count === 1 ? "" : "s"}`;
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
      <div class="company-card-head"><div><span class="company-kicker">${escapeHtml(docs[0].domain.replaceAll("_", " "))}</span><h3>${escapeHtml(company)}</h3></div><span class="doc-total">${docs.length} doc${docs.length === 1 ? "" : "s"}</span></div>
      <div class="document-list">${docs.map((doc) => {
        const href = validSourceUrl(doc.official_url);
        const link = href
          ? `<a class="document-link" href="${escapeHtml(href)}" target="_blank" rel="noopener noreferrer">Open official source <span aria-hidden="true">↗</span></a>`
          : "";
        const status = doc.processing_status || (doc.chunks ? "ready" : "uploaded");
        return `<article class="document-row"><div class="file-mark">${escapeHtml(doc.format)}</div><div class="document-info"><strong>${escapeHtml(doc.title)}</strong><span>${escapeHtml(doc.fiscal_year || "No fiscal year")} · ${doc.chunks.toLocaleString()} passages · ${escapeHtml(status)} · access: ${escapeHtml((doc.allowed_roles || []).join(", "))}</span>${link}</div></article>`;
      }).join("")}</div>
    </article>`).join("") || '<div class="loading-card">No company documents are indexed yet.</div>';
}

function renderParsedChunkInspector(data) {
  const uploads = data.documents.filter((doc) => doc.document_id.startsWith("UPLOAD-"));
  const section = $("#parsed-chunk-inspector");
  section.hidden = uploads.length === 0;
  $("#parsed-document").innerHTML = uploads.map((doc) =>
    `<option value="${escapeHtml(doc.document_id)}">${escapeHtml(doc.title)} · ${escapeHtml(doc.processing_status || "unknown")}</option>`
  ).join("");
}

function renderParsedChunks(chunks) {
  $("#parsed-chunk-list").innerHTML = chunks.map((chunk) => `
    <article class="candidate-row">
      <div class="candidate-heading"><strong>Passage ${formatNumber(chunk.chunk_index + 1)}</strong><span>${escapeHtml(chunk.processing_status || "extracted")} · ${escapeHtml(chunk.metadata?.text_extraction_method || "parser output")}</span></div>
      ${chunk.processing_error ? `<p class="corpus-note">Processing error: ${escapeHtml(chunk.processing_error)}</p>` : ""}
      <blockquote>${escapeHtml(chunk.content)}</blockquote>
      <details class="candidate-source"><summary>Parser metadata</summary><pre>${escapeHtml(JSON.stringify(chunk.metadata, null, 2))}</pre></details>
    </article>`
  ).join("") || '<p class="loading-card">No parsed passages at this offset.</p>';
}

function formatNumber(value) {
  return new Intl.NumberFormat("en-US").format(value);
}

function renderAnalytics(data) {
  analyticsSnapshot = data;
  const companySelect = $("#analytics-company");
  const yearSelect = $("#analytics-year");
  const selectedCompany = companySelect.value;
  const selectedYear = yearSelect.value;
  const companies = [...new Set(data.documents.map((item) => item.company).filter(Boolean))].sort();
  const years = [...new Set(data.documents.map((item) => item.fiscal_year).filter(Boolean).map(String))].sort();
  companySelect.innerHTML = '<option value="">All companies</option>' + companies.map((name) => `<option value="${escapeHtml(name)}">${escapeHtml(name)}</option>`).join("");
  yearSelect.innerHTML = '<option value="">All years</option>' + years.map((year) => `<option value="${escapeHtml(year)}">${escapeHtml(year)}</option>`).join("");
  companySelect.value = companies.includes(selectedCompany) ? selectedCompany : "";
  yearSelect.value = years.includes(selectedYear) ? selectedYear : "";
  companySelect.onchange = yearSelect.onchange = applyAnalyticsFilters;
  applyAnalyticsFilters();
}

function applyAnalyticsFilters() {
  if (!analyticsSnapshot) return;
  const company = $("#analytics-company").value;
  const year = $("#analytics-year").value;
  const matches = (item) => (!company || item.company === company) && (!year || String(item.fiscal_year ?? "") === year);
  const data = {
    ...analyticsSnapshot,
    documents: analyticsSnapshot.documents.filter(matches),
    domains: analyticsSnapshot.domains.filter(matches),
    processing: analyticsSnapshot.processing.filter(matches),
    financial: analyticsSnapshot.financial.filter(matches),
    candidates: analyticsSnapshot.candidates.filter(matches),
    quality: analyticsSnapshot.quality.filter(matches),
  };
  const metricGroups = data.financial.reduce((groups, item) => {
    const key = `${item.company}:${item.metric_name}`;
    (groups[key] ??= []).push(item);
    return groups;
  }, {});
  const metrics = Object.values(metricGroups).map((series) =>
    series.sort((a, b) => Number(a.fiscal_year) - Number(b.fiscal_year))
  );
  const reports = data.documents.filter((item) => item.document_type === "annual_report");
  const reportYears = [...new Set(reports.map((item) => String(item.fiscal_year || "")).filter(Boolean))].sort();
  const verifiedYears = [...new Set(data.financial.map((item) => String(item.fiscal_year)))].sort();
  $("#analysis-summary").innerHTML = [
    ["Annual reports in scope", reports.length, reportYears.join(" · ") || "No fiscal year recorded"],
    ["Verified indicators", metrics.length, data.financial.length ? `${data.financial.length} source-backed observations` : "No published values for this selection"],
    ["Verified reporting periods", verifiedYears.length, verifiedYears.join(" · ") || "Admin review required before comparison"],
  ].map(([label, value, note]) => `<article class="analysis-stat"><span>${escapeHtml(label)}</span><strong>${formatNumber(value)}</strong><small>${escapeHtml(note)}</small></article>`).join("");
  $("#analysis-coverage-note").textContent = `${formatNumber(data.documents.length)} source documents · ${formatNumber(data.documents.reduce((sum, item) => sum + item.chunks, 0))} indexed passages`;

  $("#financial-kpis").innerHTML = metrics.length ? metrics.map((series) => {
    const latest = series.at(-1);
    const previous = series.length > 1 ? series.at(-2) : null;
    const href = validSourceUrl(latest.source_url);
    const comparison = previous && previous.unit === latest.unit
      ? `Change vs ${escapeHtml(previous.fiscal_year)}: ${formatNumber(Number(latest.metric_value) - Number(previous.metric_value))} ${escapeHtml(latest.unit)}${Number(previous.metric_value) ? ` (${formatNumber((Number(latest.metric_value) - Number(previous.metric_value)) / Math.abs(Number(previous.metric_value)) * 100)}%)` : ""}`
      : "One verified reporting period";
    return `<article class="financial-card"><span>${escapeHtml(latest.metric_label)}</span><strong>${formatNumber(latest.metric_value)} <small>${escapeHtml(latest.unit)}</small></strong><em>FY ${escapeHtml(latest.fiscal_year)} · ${comparison}</em>${href ? `<a href="${escapeHtml(href)}" target="_blank" rel="noopener noreferrer">Source · page ${escapeHtml(latest.page_number)} ↗</a>` : `<span>Source · page ${escapeHtml(latest.page_number)}</span>`}</article>`;
  }).join("") : '<p class="analysis-empty"><strong>No verified financial results for this selection</strong><span>Unreviewed extraction candidates are excluded. Admins can validate source evidence in Document processing.</span></p>';

  const comparisons = metrics.flatMap((series) => {
    if (series.length < 2) return [];
    const latest = series.at(-1);
    const previous = series.at(-2);
    if (previous.unit !== latest.unit) return [];
    const change = Number(latest.metric_value) - Number(previous.metric_value);
    const percent = Number(previous.metric_value) ? change / Math.abs(Number(previous.metric_value)) * 100 : null;
    const href = validSourceUrl(latest.source_url);
    const source = href ? `<a href="${escapeHtml(href)}" target="_blank" rel="noopener noreferrer">Source, page ${escapeHtml(latest.page_number)} ↗</a>` : "Source link unavailable";
    return [`<article class="insight-row"><span class="insight-mark" aria-hidden="true">↗</span><div><strong>${escapeHtml(latest.metric_label)} ${change >= 0 ? "increased" : "decreased"} by ${formatNumber(Math.abs(change))} ${escapeHtml(latest.unit)}${percent === null ? "" : ` (${formatNumber(Math.abs(percent))}%)`}</strong><span>Reported change from FY ${escapeHtml(previous.fiscal_year)} to FY ${escapeHtml(latest.fiscal_year)} · ${source}</span></div></article>`];
  });
  if (comparisons.length) {
    $("#financial-insights").innerHTML = `<div class="insight-list">${comparisons.join("")}</div><p class="analysis-caveat">These are reported period-to-period changes. They describe the figures and do not establish why they changed.</p>`;
  } else {
    const pending = (data.candidates || []).length;
    const reportScope = reportYears.length ? `Annual reports in this selection: ${reportYears.join(", ")}. ` : "No annual report is available in this selection. ";
    const reviewScope = pending ? `${formatNumber(pending)} extracted evidence item${pending === 1 ? "" : "s"} await admin review; they are not treated as reported results.` : data.financial.length ? "A year-over-year comparison needs at least two verified periods for the same indicator." : "Ask an administrator to review extracted source evidence before interpreting financial results.";
    $("#financial-insights").innerHTML = `<div class="insight-empty"><span class="eyebrow">ANALYSIS STATUS</span><h4>No verified period comparison yet</h4><p>${escapeHtml(reportScope + reviewScope)}</p>${pending ? '<button type="button" class="inline-tab-link" data-open-tab="processing">Review source evidence <span aria-hidden="true">→</span></button>' : ""}</div>`;
  }
  $("#financial-trends").innerHTML = metrics.map((series) => {
    const max = Math.max(1, ...series.map((item) => Math.abs(Number(item.metric_value))));
    return `<article class="trend-card"><h4>${escapeHtml(series[0].metric_label)} · ${escapeHtml(series[0].unit)}</h4><div class="trend-bars">${series.map((item) => { const href = validSourceUrl(item.source_url); const source = href ? `<a href="${escapeHtml(href)}" target="_blank" rel="noopener noreferrer" aria-label="Open source page ${item.page_number}">Source ↗</a>` : ""; const ratio = Math.abs(Number(item.metric_value)) / max; return `<div class="trend-point"><strong>${formatNumber(item.metric_value)}</strong><i style="--bar-ratio:${ratio}" role="img" aria-label="${escapeHtml(item.fiscal_year)} value ${formatNumber(item.metric_value)} ${escapeHtml(item.unit)}"></i><span>FY ${escapeHtml(item.fiscal_year)}</span>${source}</div>`; }).join("")}</div></article>`;
  }).join("");
  const maxDocs = Math.max(1, ...(data.domains || []).map((item) => item.documents));
  $("#domain-chart").innerHTML = (data.domains || []).map((item) => `
    <div class="bar-row"><div><span>${escapeHtml(item.company)} · ${escapeHtml(item.domain.replaceAll("_", " "))} · FY ${escapeHtml(item.fiscal_year || "No year")}</span><strong>${item.documents} docs · ${item.chunks} passages</strong></div><span class="bar-track"><i style="width:${Math.max(5, item.documents / maxDocs * 100)}%"></i></span></div>
  `).join("");
  const statusCounts = (data.processing || []).map((item) => `<div class="bar-row"><div><span>${escapeHtml(item.company)} · ${escapeHtml(item.fiscal_year || "No year")}</span><strong>${item.documents} · ${escapeHtml(item.processing_status || "unknown")}</strong></div><span class="bar-track"><i style="width:${Math.max(5, item.documents / Math.max(1, ...data.processing.map((row) => row.documents)) * 100)}%"></i></span></div>`);
  $("#processing-chart").innerHTML = statusCounts.join("") || '<p class="loading-card">No processing records yet.</p>';
  $("#quality-chart").innerHTML = (data.quality || []).map((item) => `
    <div class="quality-row"><div><strong>${escapeHtml(item.document_id)}</strong><span>${formatNumber(item.chunks)} passages · avg ${formatNumber(item.avg_chunk_chars)} chars</span></div><span class="quality-pill ${item.empty_chunks ? "warning" : "ok"}">${item.empty_chunks ? `${item.empty_chunks} empty` : "No empty passages"}</span></div>
  `).join("");
  const candidates = data.candidates || [];
  $("#candidate-review").hidden = !candidates.length;
  $("#candidate-list").innerHTML = candidates.map((item) => {
    const href = validSourceUrl(item.official_url);
    const figures = Array.isArray(item.candidate_values)
      ? item.candidate_values.map(String).filter(Boolean)
      : [];
    const extraction = item.text_extraction_method || "pymupdf.get_text";
    const evidenceCount = Math.max(1, Number(item.evidence_count) || 1);
    const extractionLabel = extraction.includes("tesseract") ? "OCR assisted" : "PDF text";
    const figuresMarkup = figures.length
      ? figures.map((figure) => `<span>${escapeHtml(figure)}</span>`).join("")
      : "<span>No numeric token detected</span>";
    return `<article class="candidate-row">
      <div class="candidate-evidence">
        <div class="candidate-heading"><div><strong>${escapeHtml(item.metric_label)}</strong><span>${escapeHtml(item.company)} · ${escapeHtml(item.title)}</span></div><span class="candidate-status">Admin review${evidenceCount > 1 ? ` · ${formatNumber(evidenceCount)} excerpts` : ""}</span></div>
        <div class="candidate-facts"><span><small>Reporting year</small><strong>${escapeHtml(item.fiscal_year || "Needs review")}</strong></span><span><small>Source page</small><strong>${escapeHtml(item.page_number)}</strong></span><span><small>Document</small><strong>${escapeHtml(item.document_id)}</strong></span><span><small>Extraction</small><strong>${escapeHtml(extractionLabel)}</strong></span></div>
        <div class="candidate-value"><small>${figures.length > 1 ? "Figures in excerpt · select the reporting-year value from the source" : "Figure found in excerpt · verify against the source"}</small><div class="candidate-figures">${figuresMarkup}</div><small>Check the reporting year and scale on the source. Use one consistent dashboard unit across periods (for example, billion VND).${evidenceCount > 1 ? " Rejecting this excerpt will show the next pending source excerpt." : ""}</small></div>
        <details class="candidate-source"><summary>Check source excerpt${href ? ` · <a href="${escapeHtml(href)}" target="_blank" rel="noopener noreferrer">Open original ↗</a>` : ""}</summary><blockquote>${escapeHtml(item.source_quote)}</blockquote></details>
      </div>
      <form data-candidate-id="${item.id}" class="review-form">
        <label>Normalized numeric value<input name="normalized_value" type="number" step="any" required placeholder="Digits, no thousands separators"></label>
        <label>Dashboard unit<input name="unit" required placeholder="e.g. billion VND"></label>
        <div class="review-actions"><button type="submit">Verify and publish</button><button type="button" data-reject>Reject</button></div>
      </form>
    </article>`;
  }).join("");
}

function renderAnswer(data, panel = $("#answer-panel")) {
  panel.hidden = false;
  panel.innerHTML = `
    <div class="answer-heading"><span class="answer-mark">AI</span><div><span class="eyebrow">GROUNDED RESPONSE</span><h3>Answer</h3></div></div>
    <p class="answer-text">${escapeHtml(data.answer)}</p>
    ${data.citation_validation_failed ? '<p class="error-message">Sources were retrieved, but the generated citations could not be verified. No answer was published.</p>' : data.citations.length ? `<div class="citations"><h4>Retrieved sources</h4>${data.citations.map((source) => {
      const href = validSourceUrl(source.official_url);
      const link = href ? `<a href="${escapeHtml(href)}" target="_blank" rel="noopener noreferrer">View original ↗</a>` : "";
      const location = source.page_number ? `Page ${source.page_number}` : `Passage ${source.chunk_index + 1}`;
      const relevance = Number.isFinite(source.score) ? ` · Relevance ${(source.score * 100).toFixed(1)}%` : "";
      return `<article class="citation"><div class="citation-title"><span class="citation-id">[${escapeHtml(source.id)}]</span><strong>${escapeHtml(source.title)}</strong><span>${escapeHtml(location)}</span></div><p>${escapeHtml(source.excerpt)}</p><div class="citation-foot"><span>${escapeHtml(source.company || "Source evidence")}${relevance}</span>${link}</div></article>`;
    }).join("")}</div>` : `<p class="no-citations">No matching passages were found in the indexed documents.</p>`}`;
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
  if (!response.ok) throw new Error(data.detail || "Request failed");
  return data;
}

async function loadWorkspace(user) {
  $("#login-view").hidden = true;
  $("#workspace").hidden = false;
  $("#analytics-section").hidden = true;
  $("#upload-section").hidden = true;
  $("#admin-section").hidden = true;
  $("#monitoring-section").hidden = true;
  syncWorkspaceTabs();
  $("#access-matrix").replaceChildren();
  $("#connection-status").textContent = "Knowledge base connected";
  $("#user-badge").textContent = `${user.username} · ${user.role}`;
  $("#user-badge").hidden = false;
  $("#logout-button").hidden = false;
  try {
    const data = await api("/api/dashboard");
    renderCorpus(data);
    if (user.role === "admin") renderParsedChunkInspector(data);
    try {
      const capability = await api("/api/documents/upload-capability");
      $("#upload-section").hidden = !capability.can_upload;
      if (capability.can_upload) {
        const { roles } = await api("/api/documents/roles");
        $("#upload-role-options").innerHTML = roles.map((role) => `<label><input type="checkbox" name="allowed_roles" value="${escapeHtml(role)}"> ${escapeHtml(role.replaceAll("_", " "))}</label>`).join("");
      }
    } catch {
      $("#upload-section").hidden = true;
    }
    if (["finance_analyst", "sustainability_analyst", "executive", "admin"].includes(user.role)) {
      const analytics = await api("/api/analytics");
      renderAnalytics(analytics);
      $("#analytics-section").hidden = false;
    }
    if (user.role === "admin") {
      const access = await api("/api/admin/access-matrix");
      $("#access-matrix").innerHTML = access.roles.map((role) => `<article><strong>${escapeHtml(role.role)}</strong><span>${role.permissions.map(escapeHtml).join(" · ")}</span></article>`).join("");
      $("#admin-section").hidden = false;
      $("#monitoring-section").hidden = false;
      await refreshAgentMonitoring();
    }
    syncWorkspaceTabs();
    $("#login-error").hidden = true;
  } catch (error) {
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

$("#parsed-chunk-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const documentId = $("#parsed-document").value;
  const offset = Math.max(0, Number.parseInt($("#parsed-offset").value || "0", 10));
  $("#parsed-chunk-list").innerHTML = '<p class="loading-card">Loading saved parser output…</p>';
  try {
    const result = await api(`/api/admin/processing/${encodeURIComponent(documentId)}/chunks?offset=${offset}&limit=25`);
    renderParsedChunks(result.chunks);
  } catch (error) {
    $("#parsed-chunk-list").innerHTML = `<p class="loading-card">${escapeHtml(error.message)}</p>`;
  }
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

$("#ask-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = $("#ask-button");
  const question = $("#question").value.trim();
  if (!question) return;
  button.disabled = true;
  button.textContent = "Searching sources…";
  const panel = $("#answer-panel");
  panel.hidden = false;
  panel.innerHTML = '<p class="loading-answer">Retrieving relevant passages and preparing a cited answer…</p>';
  try {
    const payload = { question, retrieval_method: $("#retrieval-method").value };
    let data;
    try {
      data = await askOverWebSocket(payload, () => { button.textContent = "Preparing cited answer…"; });
    } catch (error) {
      if (!error.safeToFallback) throw error;
      data = await api("/api/ask", { method: "POST", body: JSON.stringify(payload) });
    }
    renderAnswer(data);
  } catch (error) {
    panel.innerHTML = `<p class="error-message">${escapeHtml(error.message)}. Check the app logs and service configuration.</p>`;
  } finally {
    button.disabled = false;
    button.innerHTML = 'Ask the documents <span aria-hidden="true">↗</span>';
  }
});

$("#business-question-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = $("#business-question-button");
  const question = $("#business-question").value.trim();
  const panel = $("#business-answer-panel");
  if (!question) return;
  button.disabled = true;
  button.textContent = "Analyzing authorized sources…";
  panel.hidden = false;
  panel.innerHTML = '<p class="loading-answer">Retrieving source passages and preparing a cited analysis…</p>';
  try {
    const result = await api("/api/ask", { method: "POST", body: JSON.stringify({ question }) });
    renderAnswer(result, panel);
  } catch (error) {
    panel.innerHTML = `<p class="error-message">${escapeHtml(error.message)}</p>`;
  } finally {
    button.disabled = false;
    button.innerHTML = 'Analyze sources <span aria-hidden="true">↗</span>';
  }
});

$("#analytics-section").addEventListener("click", (event) => {
  const link = event.target.closest("[data-open-tab]");
  if (link) selectWorkspaceTab(link.dataset.openTab);
});

$("#monitoring-refresh").addEventListener("click", refreshAgentMonitoring);

$("#upload-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const button = $("#upload-button");
  const file = $("#upload-file").files[0];
  const roles = [...form.querySelectorAll('input[name="allowed_roles"]:checked')].map((input) => input.value);
  if (!file || !roles.length) {
    $("#upload-status").textContent = "Select a supported document and at least one access role.";
    return;
  }
  const body = new FormData();
  body.append("file", file);
  for (const name of ["title", "document_type", "domain", "fiscal_year"]) {
    const value = form.elements[name].value.trim();
    if (value) body.append(name, value);
  }
  roles.forEach((role) => body.append("allowed_roles", role));
  button.disabled = true;
  $("#upload-status").textContent = "Uploading and processing the document…";
  try {
    const result = await api("/api/documents/upload", { method: "POST", body, headers: {} });
    $("#upload-status").textContent = `Processed ${result.document_id}; status: ${result.processing_status}; passages indexed: ${result.searchable}.`;
    form.reset();
    await loadWorkspace(await api("/api/auth/me"));
  } catch (error) {
    $("#upload-status").textContent = error.message;
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
    await api(`/api/analytics/candidates/${form.dataset.candidateId}/review`, {method:"POST", body:JSON.stringify({status:"verified", normalized_value:Number(values.normalized_value), unit:values.unit})});
    await loadWorkspace(await api("/api/auth/me"));
  } catch (error) { alert(error.message); }
});

$("#candidate-list").addEventListener("click", async (event) => {
  if (!event.target.matches("[data-reject]")) return;
  const form = event.target.closest("form[data-candidate-id]");
  try {
    await api(`/api/analytics/candidates/${form.dataset.candidateId}/review`, {method:"POST", body:JSON.stringify({status:"rejected"})});
    await loadWorkspace(await api("/api/auth/me"));
  } catch (error) { alert(error.message); }
});

loadCorpus();
