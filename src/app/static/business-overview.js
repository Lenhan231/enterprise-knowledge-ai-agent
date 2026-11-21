/* The landing page shares the authorized overview endpoint and sandboxed renderer. */
(() => {
  const el = id => document.getElementById(id);
  let overviewRequest = 0;
  let canRead = false;
  const CACHE_MS = 5 * 60 * 1000;
  let cachedAt = null, owner = null, generation = null, pending = null;
  // While refreshing, the skeleton takes the overview's place; the success and error paths below decide what shows next.
  const skeleton = on => { const node = document.getElementById('home-overview-skeleton'); if (!node) return; node.hidden = !on; if (on) el('home-overview-preview').hidden = true; };
  async function overview(valid) {
    skeleton(true);
    el('home-overview-status').textContent='Refreshing authorized source data…';
    el('home-overview-status').dataset.error='false';
    try {
      const data=await api('/api/dashboards/overview');
      if (!valid()) return;
      el('home-overview-preview')._raw=data.html; el('home-overview-preview').srcdoc=window.themedDoc?window.themedDoc(data.html):data.html;
      el('home-overview-preview').hidden=false;
      cachedAt = data.dashboard.status === 'failed' ? null : Date.now();
      el('home-overview-status').textContent=`Data refreshed ${DashboardFormatting.datetime(data.dashboard.data_updated_at)} · ${data.dashboard.status==='complete' ? 'Live source data' : 'Some sources are unavailable; review the chart notes.'}`;
    } catch(error) {
      if (!valid()) return;
      el('home-overview-preview').removeAttribute('srcdoc');
      el('home-overview-preview').hidden=true;
      el('home-overview-status').textContent=error.message || 'The overview is temporarily unavailable. Your saved dashboards remain available.';
      el('home-overview-status').dataset.error='true';
    } finally { skeleton(false); }
  }
  function refreshOverview() {
    cachedAt = null;
    const request = ++overviewRequest, session = sessionGeneration, user = currentUser;
    pending = overview(() => request === overviewRequest && session === sessionGeneration && user === currentUser && !!currentUser)
      .finally(() => { if (request === overviewRequest) pending = null; });
    return pending;
  }
  function clear() {
    overviewRequest++;
    canRead = false;
    cachedAt = owner = generation = pending = null;
    el('home-overview-preview').removeAttribute('srcdoc');
    el('home-overview-preview').hidden = true;
    el('home-overview-status').textContent = '';
    el('home-overview-status').dataset.error = 'false';
  }
  function show(allowed) {
    if (owner !== currentUser || generation !== sessionGeneration || !allowed) clear();
    owner = currentUser;
    generation = sessionGeneration;
    canRead = allowed;
    el('home-overview-refresh').hidden = !allowed;
    if (!allowed) {
      el('home-overview-status').textContent = 'The business overview requires analytics access. Use your available workspace tabs to continue.';
      return Promise.resolve();
    }
    if (cachedAt !== null && Date.now() - cachedAt < CACHE_MS) return Promise.resolve();
    return pending || refreshOverview();
  }
  el('home-overview-refresh').addEventListener('click', () => { if (canRead) return refreshOverview(); });
  window.businessOverview = {show, clear};
})();
