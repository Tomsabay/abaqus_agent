/* workbench_chat.js — the chat panel: message rendering, the streaming
   generation flow (SSE), and the design-sheet confirmation card.

   Split out of workbench.html along the panel seam its size exemption
   promised. Classic script sharing the page's global scope: $, state, api,
   apiStream, t, esc, renderAll, toast, switchTab, setLed, refreshSessions
   are defined by the page (or its other scripts) before any of this runs. */

function renderChat() {
  const wrap = $('chat-scroll');
  // In-progress sheet edits survive re-renders (a run finishing or a language
  // switch repaints the chat): carry the textarea's value over — but only for
  // the same session, which is what the data-sid attribute is for.
  const prevEdit = document.getElementById('plan-edit');
  const editVal = (prevEdit && prevEdit.dataset.sid === state.sid)
    ? prevEdit.value : null;
  wrap.innerHTML = '';
  const pending = state.session.pending;
  for (const m of state.session.messages || []) {
    const div = document.createElement('div');
    div.className = 'msg ' + (m.role === 'user' ? 'user' : 'assistant');
    let inner = `<div class="who">${m.role === 'user' ? esc(t('chat.you')) : 'Agent'}</div>
      <div class="bubble${m.error ? ' err' : ''}">${esc(m.text)}</div>`;
    if (m.refs && m.refs.length) {
      inner += '<div class="bubble-refs">' + m.refs.map(r =>
        '<span class="chat-ref">@' + esc(String(r)) + '</span>').join('') + '</div>';
    }
    if (m.proposal_id && pending && pending.proposal_id === m.proposal_id) {
      inner += proposalCardHtml(pending);
    }
    div.innerHTML = inner;
    wrap.appendChild(div);
  }
  const pp = state.session.pending_plan;
  if (pp) {
    const busy = state.planBusy ? ' disabled' : '';
    const div = document.createElement('div');
    div.className = 'msg assistant';
    div.innerHTML = `<div class="who">Agent</div>
      <div class="plan-card">
        <div class="ph">▸ ${esc(t('plan.head'))}</div>
        <textarea id="plan-edit" spellcheck="false" data-sid="${esc(state.sid)}">${esc(editVal != null ? editVal : pp.plan)}</textarea>
        <div class="hint">${esc(t('plan.hint'))}</div>
        <div class="proposal-actions">
          <button class="primary" onclick="confirmPlan()"${busy}>${esc(t('plan.confirm'))} ▶</button>
          <button class="danger" onclick="cancelPlan()"${busy}>${esc(t('plan.cancel'))}</button>
        </div>
      </div>`;
    wrap.appendChild(div);
  }
  // A live stream belongs at the bottom: re-renders from unrelated flows must
  // not orphan its nodes — streamed deltas keep writing into them for minutes.
  const ls = state.liveStream;
  if (ls && ls.sid === state.sid) {
    if (ls.userNode) wrap.appendChild(ls.userNode);
    wrap.appendChild(ls.node);
  }
  wrap.scrollTop = wrap.scrollHeight;
}

function proposalCardHtml(p) {
  const adds = (p.diff.match(/^\+(?!\+\+)/gm) || []).length;
  const dels = (p.diff.match(/^-(?!--)/gm) || []).length;
  const backendLabel = p.backend === 'claude_cli' ? 'claude' : p.backend;
  return `<div class="proposal-card">
    <div class="ph">▸ ${esc(t('proposal.head'))} <span class="backend-tag">${esc(backendLabel)}</span></div>
    <div class="stats"><span class="add">+${adds}</span> / <span class="del">−${dels}</span> ${esc(t('proposal.lines'))}
      · ${esc(t('proposal.seeFullDiff'))}</div>
    <div class="proposal-actions">
      <button class="primary" onclick="acceptProposal()">${esc(t('diff.accept'))} ▶</button>
      <button class="danger" onclick="rejectProposal()">${esc(t('diff.reject'))}</button>
      <button onclick="switchTab('diff')">${esc(t('proposal.viewDiff'))}</button>
    </div>
  </div>`;
}

async function sendMessage() {
  const input = $('chat-input');
  const text = input.value.trim();
  if (!text || !state.sid || state.liveStream) return;
  input.value = '';
  setComposer(false);
  showTyping(true);
  let live = null;
  try {
    const backend = $('backend-select').value;
    const selection = state.chatRefs.map(r => r.kind === 'selector'
      ? { kind: 'selector', selector: r.selector, note: r.note, label: r.label }
      : { ref: r.ref, label: r.label });
    // Optimistic echo + a live bubble: the user watches the model write
    // instead of staring at a spinner. Terminal events carry the server's
    // session, and renderAll() replaces both temporary nodes with it.
    const userNode = appendChatNode(`<div class="msg user"><div class="who">${esc(t('chat.you'))}</div>
      <div class="bubble">${esc(text)}</div></div>`);
    live = startLiveBubble();
    live.userNode = userNode;
    // lang: the assistant answers in the language the UI is in, not the one
    // the browser reports — those differ the moment a user switches.
    await apiStream(`/api/workbench/sessions/${state.sid}/chat/stream`,
      { text, backend, lang: I18N.lang, selection },
      { onEvent: (ev, data) => handleGenEvent(ev, data, live) });
    // Cleared only on success: a 400 (e.g. a mention the spec no longer has)
    // keeps the chips so the user can fix the selection instead of retyping.
    state.chatRefs = [];
    renderChatRefs();
    await refreshSessions();
  } catch (e) {
    toast(t('toast.chatFailed', { msg: e.message }), true);
  } finally {
    // Stream died without a terminal event (network drop, HTTP error):
    // unregister it and re-render from state, dropping the optimistic nodes.
    // After a terminal event this is a no-op — handleGenEvent already
    // unregistered, and streamed text stays visible when nothing persisted.
    if (live && state.liveStream === live) {
      state.liveStream = null;
      disposeLiveGeom();
      renderChat();
    }
    showTyping(false);
    setComposer(true);
  }
}

function appendChatNode(html) {
  const wrap = $('chat-scroll');
  const div = document.createElement('div');
  div.innerHTML = html;
  const node = div.firstElementChild;
  wrap.appendChild(node);
  wrap.scrollTop = wrap.scrollHeight;
  return node;
}

function startLiveBubble() {
  const node = appendChatNode(`<div class="msg assistant"><div class="who">Agent</div>
    <div class="bubble stream-live"><div class="stream-stage"></div>
      <pre class="stream-think"></pre><pre class="stream-text"></pre></div></div>`);
  const live = { sid: state.sid, node, userNode: null,
                 pre: node.querySelector('.stream-text'),
                 think: node.querySelector('.stream-think'),
                 stageEl: node.querySelector('.stream-stage') };
  state.liveStream = live;
  return live;
}

function handleGenEvent(ev, data, live) {
  const wrap = $('chat-scroll');
  if (ev === 'stage') {
    state.lastStage = data.stage;
    live.stageEl.textContent = '▸ ' + stageLabel(data.stage);
    // A stage change mid-stream (draft after plan, each repair round) gets a
    // divider so the buffers don't read as one continuous document.
    if (live.pre.textContent) live.pre.textContent += `\n── ${stageLabel(data.stage)} ──\n`;
    wrap.scrollTop = wrap.scrollHeight;
  } else if (ev === 'think') {
    // The reasoning, which is what the first minutes actually consist of
    // (measured: 176 thinking deltas over 170s before the first written word).
    live.think.textContent += data.text;
    live.think.scrollTop = live.think.scrollHeight;
    if (!live.pre.textContent) live.stageEl.textContent = '▸ ' + t('chat.stage.think');
    wrap.scrollTop = wrap.scrollHeight;
  } else if (ev === 'text') {
    // The answer has started: the reasoning shrinks out of the way instead of
    // disappearing — it stays inspectable, it just stops being the headline.
    if (!live.pre.textContent && live.think.textContent) {
      live.think.classList.add('done');
      live.stageEl.textContent = '▸ ' + stageLabel(state.lastStage || 'draft');
    }
    live.pre.textContent += data.text;
    live.pre.scrollTop = live.pre.scrollHeight;
    wrap.scrollTop = wrap.scrollHeight;
  } else if (ev === 'geom') {
    showLiveGeom(data);
  } else if (ev === 'plan' || ev === 'proposal' || ev === 'error') {
    disposeLiveGeom();
    if (state.liveStream === live) state.liveStream = null;
    // A stream that outlives a session switch must not clobber the session
    // now on screen — the server already persisted this outcome.
    if (live.sid !== state.sid) return;
    // error can arrive with session:null (worker crashed before persisting);
    // keep the streamed text on screen and just surface the toast.
    if (data.session) {
      state.session = data.session;
      renderAll();
    }
    if (ev === 'proposal' && data.pending) {
      if (data.pending.backend === 'claude_cli') setLed('led-claude', true);
      switchTab('diff');
    }
    if (ev === 'error') toast(data.message, true);
  }
}

async function confirmPlan() {
  if (!state.sid || state.planBusy || state.liveStream) return;
  const el = $('plan-edit');
  const planText = el ? el.value : '';
  state.planBusy = true;
  document.querySelectorAll('.plan-card button').forEach(b => { b.disabled = true; });
  setComposer(false);
  showTyping(true);
  let live = null;
  try {
    live = startLiveBubble();
    await apiStream(`/api/workbench/sessions/${state.sid}/plan/confirm`,
      { plan: planText, lang: I18N.lang },
      { onEvent: (ev, data) => handleGenEvent(ev, data, live) });
    await refreshSessions();
  } catch (e) {
    toast(t('toast.chatFailed', { msg: e.message }), true);
  } finally {
    if (live && state.liveStream === live) {
      state.liveStream = null;
      disposeLiveGeom();
    }
    state.planBusy = false;
    // Unconditional: a failure terminal re-rendered the sheet card while
    // planBusy was still true, leaving its buttons disabled — repaint now
    // that it is false. The edited text survives via the data-sid carry-over.
    renderChat();
    showTyping(false);
    setComposer(true);
  }
}

async function cancelPlan() {
  if (!state.sid) return;
  try {
    const data = await api(`/api/workbench/sessions/${state.sid}/plan/cancel`,
      { method: 'POST', body: '{}' });
    state.session = data.session;
    renderAll();
  } catch (e) {
    toast(t('toast.chatFailed', { msg: e.message }), true);
  }
}

/* The half-written model, drawn in the browser. Lives in the spec pane — the
   tab the user is already on while the draft streams — and gets out of the
   way the moment the real CAE preview has something to show. */
function showLiveGeom(payload) {
  const card = $('live-geom-card');
  const canvas = $('live-geom-canvas');
  if (!card || !canvas || typeof THREE === 'undefined' || !window.WBLiveGeom) return;
  const empty = $('spec-empty');
  if (empty) empty.style.display = 'none';
  card.style.display = 'block';
  if (!state.liveGeom) state.liveGeom = WBLiveGeom.create(canvas);
  if (state.liveGeom.render(payload)) {
    const stats = $('live-geom-stats');
    if (stats) {
      stats.innerHTML = '<span class="vp-stat-item">▤ '
        + esc(t('live.parts', { n: (payload.parts || []).length })) + '</span>';
    }
  }
}

function disposeLiveGeom() {
  if (state.liveGeom) {
    state.liveGeom.dispose();
    state.liveGeom = null;
  }
  const card = $('live-geom-card');
  if (card) card.style.display = 'none';
}

function setComposer(enabled) {
  $('btn-send').disabled = !enabled;
  $('chat-input').disabled = !enabled;
}

function showTyping(on) {
  $('typing').classList.toggle('show', on);
  clearInterval(state.typingTimer);
  if (on) {
    const t0 = Date.now();
    let ticks = 0, stage = '';
    $('typing-elapsed').textContent = '';
    state.typingTimer = setInterval(async () => {
      // A from-scratch claude_cli proposal holds the chat POST for minutes;
      // the polled stage (plan / draft / repair-N) is the only sign of life.
      // Best-effort decoration: the POST itself carries the result.
      if (ticks++ % 3 === 0 && state.sid) {
        try {
          const d = await api(`/api/workbench/sessions/${state.sid}/progress`);
          stage = d.stage ? ` · ${stageLabel(d.stage)}` : '';
        } catch (e) { /* keep the last label */ }
      }
      $('typing-elapsed').textContent = ` ${Math.round((Date.now() - t0) / 1000)}s${stage}`;
    }, 1000);
  }
}

function stageLabel(stage) {
  if (stage.startsWith('repair-')) return t('chat.stage.repair', { n: stage.slice(7) });
  return stage === 'plan' ? t('chat.stage.plan') : t('chat.stage.draft');
}
