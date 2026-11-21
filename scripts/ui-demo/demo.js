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
// ?shot=btnbox: where the label sits inside each composer action button
(() => {
  if (new URLSearchParams(location.search).get("shot") !== "btnbox") return;
  window.addEventListener("load", () => setTimeout(() => {
    document.querySelector("#tab-button-general-chat")?.click();
    const box = document.querySelector("#general-chat-question"); box.value = "x"; box.dispatchEvent(new Event("input", { bubbles: true }));
    setTimeout(() => {
      const rows = [...document.querySelectorAll(".composer-action")].map((b) => {
        const range = document.createRange(); range.selectNodeContents(b.querySelector("span")); const t = range.getBoundingClientRect(), r = b.getBoundingClientRect();
        return `${b.textContent.trim()}: button y=${r.y.toFixed(1)} h=${r.height.toFixed(1)} centre=${(r.y + r.height / 2).toFixed(1)} | label centre=${(t.y + t.height / 2).toFixed(1)}`;
      });
      const pre = document.createElement("pre"); pre.id = "btnbox"; pre.textContent = rows.join("\n"); document.body.append(pre);
    }, 300);
  }, 400));
})();
// ?shot=hoverex: show the Examples button in its hover look (class stands in for :hover)
(() => {
  if (new URLSearchParams(location.search).get("shot") !== "hoverex") return;
  window.addEventListener("load", () => setTimeout(() => {
    document.querySelector("#tab-button-general-chat")?.click();
    const box = document.querySelector("#general-chat-question"); box.value = "Khách hàng nào có nhiều đơn hàng nhất?"; box.dispatchEvent(new Event("input", { bubbles: true }));
    const b = document.querySelector(".examples-wrap > button"); b.style.background = "var(--aic-pill-hover)"; b.style.color = "var(--ink)";
  }, 400));
})();
// ?shot=glassmid&phase=in|out&r=45: freeze the theme glass part-way (in = closing circle, out = opening hole)
(() => {
  const q = new URLSearchParams(location.search);
  if (q.get("shot") !== "glassmid") return;
  window.addEventListener("load", () => setTimeout(() => {
    const g = document.createElement("div"); g.className = "theme-glass " + (q.get("phase") === "out" ? "out" : "in");
    g.style.animation = "none"; g.style.setProperty("--r", (q.get("r") || "45") + "%"); document.body.append(g);
  }, 600));
})();
// ?shot=skeleton: unhide the home skeleton; ?shot=toast: raise sample toasts
(() => {
  const q = new URLSearchParams(location.search), shot = q.get("shot");
  if (shot !== "skeleton" && shot !== "toast") return;
  window.addEventListener("load", () => setTimeout(() => {
    if (shot === "skeleton") { document.getElementById("home-overview-preview").hidden = true; document.getElementById("home-overview-skeleton").hidden = false; }
    else { window.toast("Report saved."); window.toast("Copied to clipboard"); window.toast("The report could not be saved.", "error"); }
  }, 900));
})();
// ?shot=autohide (sidebar hidden) / ?shot=autohide-peek (pointer on the edge)
(() => {
  const shot = new URLSearchParams(location.search).get("shot");
  if (shot !== "autohide" && shot !== "autohide-peek") return;
  window.addEventListener("load", () => setTimeout(() => {
    const ws = document.querySelector("#workspace");
    if (!ws.classList.contains("sidebar-autohide")) document.querySelector("#sidebar-autohide").click();
    ws.classList.toggle("is-peek", shot === "autohide-peek");
    if (shot === "autohide") document.activeElement?.blur();
  }, 700));
})();
// ?shot=autohide-logic: drive the edge/sidebar pointer events and log is-peek
(() => {
  if (new URLSearchParams(location.search).get("shot") !== "autohide-logic") return;
  window.addEventListener("load", () => setTimeout(() => {
    const ws = document.querySelector("#workspace"), edge = document.querySelector("#sidebar-edge"), side = document.querySelector("#workspace-sidebar"), log = [];
    const peek = () => ws.classList.contains("is-peek"), fire = (el, type) => el.dispatchEvent(new PointerEvent(type, { bubbles: false }));
    if (!ws.classList.contains("sidebar-autohide")) document.querySelector("#sidebar-autohide").click();
    fire(side, "pointerleave");
    setTimeout(() => { log.push(`after leaving the sidebar (400ms): peek=${peek()}`); fire(edge, "pointerenter"); log.push(`edge enter: peek=${peek()}`);
      fire(edge, "pointerleave"); fire(side, "pointerenter"); log.push(`edge leave then sidebar enter immediately: peek=${peek()}`);
      setTimeout(() => { log.push(`300ms later, pointer still on sidebar: peek=${peek()}`); fire(side, "pointerleave");
        setTimeout(() => { log.push(`pointer left sidebar, 400ms: peek=${peek()}`);
          document.querySelector("#sidebar-autohide").click(); log.push(`autohide off: class=${ws.classList.contains("sidebar-autohide")} stored=${localStorage.getItem("sidebar_autohide")}`);
          const pre = document.createElement("pre"); pre.id = "ahlog"; pre.textContent = log.join("\n"); document.body.append(pre); }, 400); }, 300); }, 400);
  }, 700));
})();
// ?shot=refreshprobe: press Refresh overview and record what is visible while it loads and after
(() => {
  if (new URLSearchParams(location.search).get("shot") !== "refreshprobe") return;
  window.addEventListener("load", () => setTimeout(() => {
    const frame = document.getElementById("home-overview-preview"), sk = document.getElementById("home-overview-skeleton"), log = [];
    const state = (when) => log.push(`${when}: overview hidden=${frame.hidden} skeleton hidden=${sk.hidden}`);
    state("before");
    document.getElementById("home-overview-refresh").click();
    state("right after click");
    setTimeout(() => { state("after load"); const pre = document.createElement("pre"); pre.id = "rp"; pre.textContent = log.join("\n"); document.body.append(pre); }, 1500);
  }, 1500));
})();
// ?shot=scorebar: measure the score bar and its fill in the first source card
(() => {
  if (new URLSearchParams(location.search).get("shot") !== "scorebar") return;
  window.addEventListener("load", () => setTimeout(() => {
    document.querySelector("#tab-button-general-chat").click();
    document.querySelector("#general-chat-question").value = "Khi nghỉ việc tôi cần bàn giao những gì?";
    document.querySelector("#general-chat-form").requestSubmit();
    setTimeout(() => {
      const bar = document.querySelector(".chat-turn .citation-score-bar"), fill = bar?.firstElementChild;
      const r = (e) => { const b = e.getBoundingClientRect(), c = getComputedStyle(e); return `x=${b.x.toFixed(1)} w=${b.width.toFixed(1)} pos=${c.position} left=${c.left} ml=${c.marginLeft} bg=${c.backgroundColor} style=${e.getAttribute("style")}`; };
      const pre = document.createElement("pre"); pre.id = "sb"; pre.textContent = bar ? `bar: ${r(bar)}\nfill: ${r(fill)}\nparent: ${bar.parentElement.className}` : "no bar"; document.body.append(pre);
    }, 2500);
  }, 600));
})();
