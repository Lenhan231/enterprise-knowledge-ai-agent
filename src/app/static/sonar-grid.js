/* Sonar Grid (after the 21st.dev component) for the sign-in page: a grid of dots. A ping spreads through it from a point,
   and the dots under the ring grow and brighten as it passes. Pings start on their own and wherever the page is tapped. */
(() => {
  const view = document.getElementById("login-view");
  const canvas = document.getElementById("sonar-grid");
  if (!view || !canvas || !canvas.getContext) return;
  const ctx = canvas.getContext("2d");
  const calm = window.matchMedia("(prefers-reduced-motion: reduce)");
  const GAP = 26, SPEED = 300, BAND = 120, LIFE = 3600, MAX_PINGS = 6;
  let width = 0, height = 0, pings = [], frame = 0, nextAuto = 0;

  const dark = () => document.documentElement.getAttribute("data-theme") === "dark";
  const size = () => {
    const box = view.getBoundingClientRect();
    const ratio = Math.min(2, window.devicePixelRatio || 1);
    width = box.width; height = box.height;
    canvas.width = Math.round(width * ratio); canvas.height = Math.round(height * ratio);
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  };
  const ping = (x, y, now) => { pings.push({ x, y, t: now }); if (pings.length > MAX_PINGS) pings.shift(); };

  const draw = (now) => {
    const light = dark() ? [245, 245, 247] : [29, 29, 31];
    const baseAlpha = dark() ? 0.22 : 0.2;
    pings = pings.filter((p) => now - p.t < LIFE);
    ctx.clearRect(0, 0, width, height);
    for (let y = GAP / 2; y < height; y += GAP) {
      for (let x = GAP / 2; x < width; x += GAP) {
        let level = 0;
        for (const p of pings) {
          const age = now - p.t;
          const gap = (Math.hypot(x - p.x, y - p.y) - (age / 1000) * SPEED) / BAND;
          const fade = 1 - age / LIFE;
          level = Math.max(level, Math.exp(-gap * gap) * fade * fade);
        }
        ctx.fillStyle = `rgba(${light[0]},${light[1]},${light[2]},${Math.min(1, baseAlpha + level * 0.8)})`;
        ctx.beginPath();
        ctx.arc(x, y, 1.15 + level * 3.2, 0, Math.PI * 2);
        ctx.fill();
      }
    }
    canvas.dataset.pings = String(pings.length);
  };

  const still = () => { pings = [{ x: width * 0.5, y: height * 0.46, t: -1500 }]; draw(0); };

  const tick = (now) => {
    if (document.hidden || view.offsetParent === null) { frame = 0; return; }
    if (now >= nextAuto) { ping(width * (0.15 + Math.random() * 0.7), height * (0.15 + Math.random() * 0.7), now); nextAuto = now + 2200 + Math.random() * 1400; }
    draw(now);
    frame = requestAnimationFrame(tick);
  };
  const start = () => {
    if (frame) return;
    size();
    if (calm.matches) { still(); return; } // one still frame: the dots with a single ring frozen mid-spread
    nextAuto = 0;
    ping(width * 0.5, height * 0.46, performance.now());
    frame = requestAnimationFrame(tick);
  };

  view.addEventListener("pointerdown", (event) => {
    if (calm.matches || event.target.closest("form, a, button, input, label")) return;
    const box = view.getBoundingClientRect();
    ping(event.clientX - box.left, event.clientY - box.top, performance.now());
    if (!frame) frame = requestAnimationFrame(tick);
  });
  new ResizeObserver(() => { size(); if (calm.matches) still(); }).observe(view);
  new MutationObserver(() => { if (calm.matches) still(); }).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  new IntersectionObserver((entries) => { if (entries[0].isIntersecting) start(); }).observe(view);
  document.addEventListener("visibilitychange", () => { if (!document.hidden && view.offsetParent !== null) start(); });
})();
