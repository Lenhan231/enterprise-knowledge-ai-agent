/* Saved dashboards use a sandboxed HTML document, never privileged innerHTML. */
(() => {
  const root = document.querySelector('#tab-dashboard');
  const el = id => document.getElementById(`dw-${id}`);
  let selected = null;
  let epoch = 0;
  let busy = false;
  let loaded = false;
  let conversationId = null;
  let restartRequired = false;
  let messages = [];
  const kinds = ['kpi', 'bar', 'line', 'donut', 'table', 'summary'];
  const status = (message, error = false) => {
    el('status').textContent = message;
    el('status').dataset.error = String(error);
  };
  const setBusy = value => {
    busy = value;
    root.setAttribute('aria-busy', String(value));
    root.querySelectorAll('button,input,textarea,select').forEach(node => { node.disabled = value || node.matches('[data-remove]') && selected?.tiles.length === 1; });
    el('create-scope').disabled = value || !!conversationId || restartRequired;
    el('prompt').disabled = value || restartRequired;
    el('send').disabled = value || restartRequired;
  };
  async function action(message, work) {
    if (busy) return;
    const token = epoch;
    const generation = sessionGeneration;
    const valid = () => token === epoch && generation === sessionGeneration && !!currentUser;
    setBusy(true);
    status(message);
    try {
      await work(valid);
    } catch (error) {
      if (valid()) status(error.message || 'Dashboard request failed.', true);
    } finally {
      if (valid()) {
        setBusy(false);
        if (!root.hidden && !el('create').hidden && !restartRequired) el('prompt').focus();
      }
    }
  }
  async function library(valid) {
    const data = await api('/api/dashboards');
    if (!valid()) return;
    loaded = true;
    el('library').innerHTML = data.dashboards.length ? data.dashboards.map(doc => `<button type="button" data-id="${escapeHtml(doc.id)}" aria-current="${selected?.id === doc.id}">${escapeHtml(doc.title)}<small>Revision ${DashboardFormatting.number(doc.revision,{unit:'count'})} · ${escapeHtml(DashboardFormatting.datetime(doc.updated_at))}</small></button>`).join('') : '<p class="dw-help">Your saved dashboards will appear here.</p>';
    if (busy) el('library').querySelectorAll('button').forEach(node => { node.disabled = true; });
  }
  function resetEditor() {
    selected = null;
    conversationId = null;
    restartRequired = false;
    messages = [];
    el('editor').hidden = true;
    el('create').hidden = false;
    el('tiles').replaceChildren();
    el('preview').removeAttribute('srcdoc');
    el('open').removeAttribute('href');
    el('download').removeAttribute('href');
    for (const name of ['prompt', 'create-scope', 'title', 'description', 'scope']) el(name).value = '';
    el('transcript').innerHTML = '';
    el('transcript').hidden = true;
    el('welcome').hidden = false;
    el('prompt').placeholder = 'Describe the dashboard you want…';
  }
  function chatMessage(role, message) {
    messages.push({role, message});
    el('welcome').hidden = true;
    el('transcript').hidden = false;
    el('transcript').innerHTML = messages.map(item => `<article class="dw-message dw-message-${item.role}"><strong>${item.role === 'user' ? 'You' : 'Dashboard assistant'}</strong><div>${escapeHtml(item.message)}</div></article>`).join('');
    el('transcript').scrollTop = el('transcript').scrollHeight;
  }
  function resultOrQuestion(data, expectedScope, initialMessage) {
    if (data.dashboard) { display(data, expectedScope); return true; }
    if (!['clarification_required', 'failed'].includes(data.status)) throw new Error('Unexpected dashboard response. Please try again.');
    if (expectedScope !== undefined && data.scope !== expectedScope) throw new Error('The response changed your date/filter scope. Start a new dashboard request.');
    if (selected || initialMessage !== undefined) {
      messages = [];
      chatMessage('user', initialMessage || data.description || selected.description);
    }
    selected = null;
    conversationId = data.conversation_id || null;
    restartRequired = data.can_reply === false;
    el('editor').hidden = true;
    el('create').hidden = false;
    el('preview').removeAttribute('srcdoc');
    el('create-scope').value = data.scope;
    chatMessage('assistant', data.message);
    if (data.status === 'clarification_required') el('prompt').value = '';
    else if (!el('prompt').value) el('prompt').value = data.description || '';
    el('prompt').placeholder = conversationId ? 'Reply to the clarification…' : 'Describe the dashboard you want…';
    let statusMessage = data.message;
    if (restartRequired) statusMessage = 'Start a new dashboard request to continue.';
    else if (data.status === 'clarification_required') statusMessage = 'Please clarify the request to continue.';
    status(statusMessage, data.status === 'failed');
    return false;
  }
  function tileEditors() {
    el('tiles').innerHTML = selected.tiles.map((tile, i) => {
      const result = selected.results.find(item => item.id === tile.query_id);
      const fields = Object.keys(result?.payload?.rows?.[0] || {});
      return `<fieldset class="dw-tile" data-index="${i}"><legend>Tile ${i + 1} · ${escapeHtml(tile.query_id)}</legend><div class="dw-tile-fields"><div><label for="dw-tile-${i}-title">Title</label><input id="dw-tile-${i}-title" data-field="title" maxlength="120" value="${escapeHtml(tile.title)}" required></div><div><label for="dw-tile-${i}-kind">Representation</label><select id="dw-tile-${i}-kind" data-field="kind">${kinds.map(kind => `<option${kind === tile.kind ? ' selected' : ''}>${kind}</option>`).join('')}</select></div><div><label for="dw-tile-${i}-dimension">Dimension (blank = infer)</label><input id="dw-tile-${i}-dimension" data-field="dimension" maxlength="128" value="${escapeHtml(tile.dimension || '')}"></div><div><label for="dw-tile-${i}-measures">Measures (comma separated, blank = infer)</label><input id="dw-tile-${i}-measures" data-field="measures" value="${escapeHtml(tile.measures.join(', '))}"></div><div><label for="dw-tile-${i}-span">Tile width</label><select id="dw-tile-${i}-span" data-field="span"><option value="1"${tile.span === 1 ? ' selected' : ''}>Half width</option><option value="2"${tile.span === 2 ? ' selected' : ''}>Full width</option></select></div></div><small>${escapeHtml(selected.tile_status?.[tile.id]?.message || '')}<br>Returned fields: ${escapeHtml(fields.join(', ') || 'No rows returned')}<br>Dataset status: ${escapeHtml(result?.status || 'unavailable')} · ${escapeHtml(result?.message || '')}</small><div class="dw-tile-actions"><button type="button" data-move="-1"${i === 0 ? ' disabled' : ''}>Move up</button><button type="button" data-move="1"${i === selected.tiles.length - 1 ? ' disabled' : ''}>Move down</button><button type="button" data-remove aria-label="Delete tile ${i + 1}"${selected.tiles.length === 1 ? ' disabled' : ''}>Delete tile</button></div></fieldset>`;
    }).join('');
  }
  function readEdits() {
    return [...el('tiles').querySelectorAll('.dw-tile')].map((node, i) => {
      const value = field => node.querySelector(`[data-field="${field}"]`).value.trim();
      return {...selected.tiles[i], title: value('title'), kind: value('kind'), dimension: value('dimension') || null,
        measures: value('measures').split(',').map(v => v.trim()).filter(Boolean), span: Number(value('span'))};
    });
  }
  function display(data, expectedScope) {
    if (expectedScope !== undefined && data.dashboard.scope !== expectedScope) {
      throw new Error('The response changed your date/filter scope. Reopen the dashboard before making further edits.');
    }
    selected = data.dashboard;
    conversationId = null;
    restartRequired = false;
    el('create').hidden = true;
    el('editor').hidden = false;
    el('title').value = selected.title;
    el('description').value = selected.description;
    el('scope').value = selected.scope;
    el('prompt').value = '';
    el('create-scope').value = '';
    el('meta').textContent = `Revision ${DashboardFormatting.number(selected.revision,{unit:'count'})} · ${selected.status} · Data refreshed ${DashboardFormatting.datetime(selected.data_updated_at)}`;
    el('preview').srcdoc = data.html;
    el('open').href = data.html_url;
    el('download').href = `${data.html_url}?download=true`;
    tileEditors();
    const failed = Object.values(selected.tile_status || {}).filter(item => item.status === 'unavailable').length;
    status(failed ? `Saved with ${failed} unavailable tile(s). Review the tile messages below.` : 'Saved. Edit tiles, refresh data, or open the HTML dashboard.', failed > 0);
  }
  async function load(id, valid) {
    const data = await api(`/api/dashboards/${encodeURIComponent(id)}`);
    if (!valid()) return;
    resultOrQuestion(data, undefined, data.description);
    await library(valid);
  }
  el('library').addEventListener('click', event => {
    const button = event.target.closest('button[data-id]');
    if (button) action('Opening dashboard…', valid => load(button.dataset.id, valid));
  });
  el('tiles').addEventListener('click', event => {
    const button = event.target.closest('button[data-move],button[data-remove]');
    if (!button || busy) return;
    selected.tiles = readEdits();
    const i = Number(button.closest('.dw-tile').dataset.index);
    if (button.hasAttribute('data-remove')) {
      if (selected.tiles.length === 1) { status('Keep at least one tile, or delete the dashboard.'); return; }
      selected.tiles.splice(i, 1);
      tileEditors();
      status('Tile removed from this draft. Save edits to update the dashboard preview.');
      return;
    }
    const j = i + Number(button.dataset.move);
    if (j < 0 || j >= selected.tiles.length) return;
    [selected.tiles[i], selected.tiles[j]] = [selected.tiles[j], selected.tiles[i]];
    tileEditors();
    status('Layout changed. Save edits to update the dashboard.');
  });
  el('new').addEventListener('click', () => { if (!busy) { resetEditor(); setBusy(false); status('Describe a new dashboard.'); el('prompt').focus(); } });
  el('create').addEventListener('submit', event => {
    event.preventDefault();
    if (restartRequired || busy) return;
    const message = el('prompt').value.trim();
    if (!message) return;
    chatMessage('user', message);
    action('Checking your request and querying data…', async valid => {
      const body = {description: el('prompt').value.trim(), scope: el('create-scope').value.trim()};
      if (conversationId) body.conversation_id = conversationId;
      const data = await api('/api/dashboards', {method: 'POST', body: JSON.stringify(body)});
      if (!valid()) return;
      if (resultOrQuestion(data, body.scope)) await library(valid);
    });
  });
  el('prompt').addEventListener('keydown', event => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      if (!busy && !restartRequired) el('create').requestSubmit();
    }
  });
  el('save').addEventListener('click', () => action('Saving edits…', async valid => {
    const body = {revision: selected.revision, title: el('title').value.trim(), scope: el('scope').value.trim(), tiles: readEdits()};
    const data = await api(`/api/dashboards/${selected.id}`, {method: 'PATCH', body: JSON.stringify(body)});
    if (!valid()) return;
    if (resultOrQuestion(data, body.scope, selected.description)) await library(valid);
  }));
  for (const name of ['refresh', 'rebuild']) el(name).addEventListener('click', () => action(name === 'rebuild' ? 'Running updated question and rebuilding tiles…' : 'Refreshing saved dashboard data…', async valid => {
    const body = {revision: selected.revision, scope: el('scope').value.trim()};
    if (name === 'rebuild') body.description = el('description').value.trim();
    const data = await api(`/api/dashboards/${selected.id}/refresh`, {method: 'POST', body: JSON.stringify(body)});
    if (!valid()) return;
    if (resultOrQuestion(data, body.scope, body.description || selected.description)) await library(valid);
  }));
  el('delete').addEventListener('click', () => {
    if (!selected || busy || !window.confirm('Delete this saved dashboard?')) return;
    action('Deleting dashboard…', async valid => {
      await api(`/api/dashboards/${selected.id}?revision=${selected.revision}`, {method: 'DELETE'});
      if (!valid()) return;
      resetEditor();
      await library(valid);
      status('Dashboard deleted.');
    });
  });
  window.dashboardWorkspace = {
    show() {
      if (loaded) return Promise.resolve();
      return action('Loading dashboards...', async valid => {
        await library(valid);
        if (valid()) status(selected ? 'Your dashboard is ready.' : 'Ready to build a dashboard.');
      });
    },
    clear() {
      epoch += 1;
      loaded = false;
      busy = false;
      resetEditor();
      el('library').replaceChildren();
      status('');
      setBusy(false);
    },
  };
})();
