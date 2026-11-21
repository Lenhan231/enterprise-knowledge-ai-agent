// Screenshot driver (demo only): ?shot=answer asks a question, ?shot=monitor opens monitoring, ?theme=dark forces dark.
(() => {
  const q = new URLSearchParams(location.search);
  if (q.get("theme")) { try { localStorage.setItem("app_theme", q.get("theme")); } catch {} document.documentElement.dataset.theme = q.get("theme"); }
  try { localStorage.setItem("sidebar_collapsed", "false"); } catch {}
  const wait = (fn) => new Promise((ok) => { const t = setInterval(() => { if (fn()) { clearInterval(t); ok(); } }, 100); });
  window.addEventListener("load", async () => {
    await wait(() => !document.querySelector("#workspace")?.hidden);
    if (q.get("shot") === "answer") {
      document.querySelector("#tab-button-general-chat").click();
      document.querySelector("#general-chat-question").value = "Khi nghỉ việc tôi cần bàn giao những gì?";
      document.querySelector("#general-chat-form").requestSubmit();
    }
    if (q.get("shot") === "chat-empty") document.querySelector("#tab-button-general-chat").click();
    if (q.get("shot") === "chat") {
      document.querySelector("#tab-button-general-chat").click();
      document.querySelector("#general-chat-question").value = "Khi nghỉ việc tôi cần bàn giao những gì?";
      document.querySelector("#general-chat-form").requestSubmit();
    }
    if (q.get("shot") === "access") document.querySelector("#tab-button-access").click();
    if (q.get("shot") === "collapsed") document.querySelector("#sidebar-toggle").click();
    if (q.get("shot") === "home") document.querySelector("#tab-button-general-chat").click();
    if (q.get("shot") === "feedback") {
      document.querySelector("#tab-button-general-chat").click();
      document.querySelector("#general-chat-question").value = "Khi nghỉ việc tôi cần bàn giao những gì?";
      document.querySelector("#general-chat-form").requestSubmit();
      await wait(() => document.querySelector('.feedback-btn[data-rating="down"]'));
      document.querySelector('.feedback-btn[data-rating="down"]').click();
      document.querySelectorAll(".feedback-reason")[1].click();
    }
    if (q.get("shot") === "fbtest") {
      document.querySelector("#tab-button-general-chat").click();
      document.querySelector("#general-chat-question").value = "Khi nghỉ việc tôi cần bàn giao những gì?";
      document.querySelector("#general-chat-form").requestSubmit();
      await wait(() => document.querySelector('.feedback-btn[data-rating="up"]'));
      const up = document.querySelector('.feedback-btn[data-rating="up"]');
      up.click();
      const log = [`right after click: chosen=${up.classList.contains("chosen")}`];
      setTimeout(() => {
        log.push(`after 3 s: chosen=${up.classList.contains("chosen")} status="${document.querySelector(".feedback-status").textContent}"`);
        const pre = document.createElement("pre"); pre.id = "fb-report"; pre.textContent = log.join("\n"); document.body.append(pre);
      }, 3000);
    }
    if (q.get("shot") === "dashboard") { document.querySelector("#tab-button-dashboard").click(); setTimeout(() => document.querySelector("#dw-library button")?.click(), 400); }
    if (q.get("shot") === "reports") { document.querySelector("#tab-button-knowledge").click(); const rf = document.querySelector("#report-fold"); if (rf) rf.open = true; setTimeout(() => document.querySelector("#rw-library button")?.click(), 400); }
    if ((q.get("shot") || "").startsWith("tab:")) document.querySelector("#tab-button-" + q.get("shot").slice(4))?.click();
    if (q.get("shot") === "monitor") document.querySelector("#tab-button-monitoring").click();
    if (q.get("shot") === "ratings") { document.querySelector("#tab-button-monitoring").click(); document.querySelector('[data-monitor-tab="feedback"]')?.click(); }
    if (q.get("shot") === "report") { document.querySelector("#tab-button-knowledge").click(); const f = document.querySelector("#report-fold"); if (f) f.open = true; }
  });
})();
// ?debug=overflow: list elements wider than the viewport into <pre id="overflow-report">.
window.addEventListener("load", () => setTimeout(() => {
  if (new URLSearchParams(location.search).get("debug") !== "overflow") return;
  const w = document.documentElement.clientWidth, rows = [];
  document.querySelectorAll("body *").forEach((el) => {
    const r = el.getBoundingClientRect();
    if (r.width && r.right > w + 1 && el.offsetParent !== null) rows.push(`${el.tagName}.${[...el.classList].join(".")}#${el.id} right=${Math.round(r.right)} w=${Math.round(r.width)} minw=${getComputedStyle(el).minWidth} disp=${getComputedStyle(el).display}`);
  });
  const pre = document.createElement("pre"); pre.id = "overflow-report"; pre.textContent = `viewport=${w} scroll=${document.documentElement.scrollWidth}\n` + rows.slice(0, 25).join("\n");
  document.body.append(pre);
}, 1500));
// ?debug=gap: report boxes between the stats line and the composer
window.addEventListener("load", () => setTimeout(() => {
  if (new URLSearchParams(location.search).get("debug") !== "gap") return;
  const pick = ["section.intro", ".agent-overview", "section.stats", "#tab-knowledge", ".ask-panel", "#ask-form"];
  const pre = document.createElement("pre"); pre.id = "gap-report";
  pre.textContent = pick.map((sel) => { const el = document.querySelector(sel); if (!el) return sel + " missing"; const r = el.getBoundingClientRect(), cs = getComputedStyle(el);
    return `${sel} top=${Math.round(r.top)} h=${Math.round(r.height)} disp=${cs.display} mt=${cs.marginTop} mb=${cs.marginBottom} pt=${cs.paddingTop}`; }).join("\n");
  document.body.append(pre);
}, 2500));
// ?shot=examples: open the composer's Examples menu; ?shot=typing: text in the box
(() => {
  const q = new URLSearchParams(location.search), shot = q.get("shot");
  if (shot !== "examples" && shot !== "typing") return;
  window.addEventListener("load", () => setTimeout(() => {
    document.querySelector("#tab-button-general-chat")?.click();
    const box = document.querySelector("#general-chat-question");
    if (shot === "typing") { box.value = "Khách hàng nào có nhiều đơn hàng nhất?"; box.dispatchEvent(new Event("input", { bubbles: true })); }
    else document.querySelector(".examples-wrap > button")?.click();
  }, 500));
})();
// ?shot=glass: click the theme toggle and record what the glass pane did (appears, theme swaps, pane removed)
(() => {
  if (new URLSearchParams(location.search).get("shot") !== "glass") return;
  window.addEventListener("load", () => setTimeout(() => {
    const log = [], theme = () => document.documentElement.getAttribute("data-theme") || "light";
    log.push(`start theme=${theme()}`);
    document.querySelector("#theme-toggle").click();
    setTimeout(() => log.push(`150ms glass=${!!document.querySelector(".theme-glass")} theme=${theme()}`), 150);
    setTimeout(() => log.push(`600ms glass=${!!document.querySelector(".theme-glass")} theme=${theme()}`), 600);
    setTimeout(() => { log.push(`2500ms glass=${!!document.querySelector(".theme-glass")} theme=${theme()}`); const pre = document.createElement("pre"); pre.id = "glass-log"; pre.textContent = log.join("\n"); document.body.append(pre); }, 2500);
  }, 500));
})();
// ?shot=rects: report geometry of the composer pieces into <pre id="rects">
(() => {
  if (new URLSearchParams(location.search).get("shot") !== "rects") return;
  window.addEventListener("load", () => setTimeout(() => {
    document.querySelector("#tab-button-general-chat")?.click();
    setTimeout(() => {
      const r = (sel) => { const e = document.querySelector(sel); if (!e) return sel + ": none"; const b = e.getBoundingClientRect(), c = getComputedStyle(e); return `${sel}: x=${b.x.toFixed(1)} y=${b.y.toFixed(1)} w=${b.width.toFixed(1)} h=${b.height.toFixed(1)} ml=${c.marginLeft} mr=${c.marginRight}`; };
      const pre = document.createElement("pre"); pre.id = "rects";
      pre.textContent = ["#general-chat-question", ".composer-actions", ".examples-wrap > button", ".composer-clear", ".route-pill", "#general-chat-send"].map(r).join("\n");
      document.body.append(pre);
    }, 300);
  }, 400));
})();
