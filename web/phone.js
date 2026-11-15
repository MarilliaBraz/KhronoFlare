// Alert receiver: listens to an ntfy.sh channel and shows approved alerts full screen,
// with a siren and vibration. Simulation only.
"use strict";
(function () {
  const NTFY = 'https://ntfy.sh';
  const $ = id => document.getElementById(id);
  const t = (k, v) => I18N.t(k, v);
  const label = kind => t('pop.' + kind);
  // History and connection state keep raw values so they can be redrawn in another language.
  const received = [];
  let stateKey = 'ph.connecting', stateCls = '';

  let es = null, actx = null, siren = null, wakeLock = null;

  const params = new URLSearchParams(location.search);
  $('topic').value = params.get('t') || '';

  function kindOf(tags) {
    tags = tags || [];
    for (const k of ['extreme', 'severe', 'cancel', 'test']) if (tags.includes(k)) return k;
    return 'severe';
  }
  function placeOf(title) {
    const parts = String(title || '').split('·');
    return parts.length > 2 ? parts.slice(2).join('·').trim() : '';
  }

  /* ---------- sound and vibration ---------- */
  function unlockAudio() {
    try { actx = actx || new (window.AudioContext || window.webkitAudioContext)(); if (actx.state === 'suspended') actx.resume(); } catch (e) { actx = null; }
  }
  function stopSiren() {
    if (siren) { try { siren.forEach(n => n.stop()); } catch (e) { /* already stopped */ } siren = null; }
    if (navigator.vibrate) navigator.vibrate(0);
  }
  function playSiren(kind) {
    stopSiren();
    if (!actx) return;
    const t0 = actx.currentTime;
    if (kind === 'extreme') {
      // Rising and falling tone for up to 10 seconds, until OK is tapped.
      const osc = actx.createOscillator(), lfo = actx.createOscillator(), depth = actx.createGain(), vol = actx.createGain();
      osc.type = 'sawtooth'; osc.frequency.value = 820;
      lfo.frequency.value = 1.1; depth.gain.value = 260;
      vol.gain.setValueAtTime(0.0001, t0); vol.gain.exponentialRampToValueAtTime(0.18, t0 + 0.1);
      lfo.connect(depth).connect(osc.frequency); osc.connect(vol).connect(actx.destination);
      osc.start(t0); lfo.start(t0); osc.stop(t0 + 10); lfo.stop(t0 + 10);
      siren = [osc, lfo];
    } else {
      const n = kind === 'severe' ? 3 : 1, nodes = [];
      for (let i = 0; i < n; i++) {
        const o = actx.createOscillator(), g = actx.createGain(), s = t0 + i * 0.35;
        o.type = 'square'; o.frequency.value = 960;
        g.gain.setValueAtTime(0.0001, s); g.gain.exponentialRampToValueAtTime(0.08, s + 0.02); g.gain.exponentialRampToValueAtTime(0.0001, s + 0.25);
        o.connect(g).connect(actx.destination); o.start(s); o.stop(s + 0.26); nodes.push(o);
      }
      siren = nodes;
    }
    if (navigator.vibrate) {
      navigator.vibrate(kind === 'extreme' ? [600, 200, 600, 200, 600, 200, 600, 200, 600] : kind === 'severe' ? [300, 150, 300] : [200]);
    }
  }

  /* ---------- screen wake lock ---------- */
  async function keepAwake() {
    try { if ('wakeLock' in navigator) wakeLock = await navigator.wakeLock.request('screen'); } catch (e) { /* not granted */ }
  }
  document.addEventListener('visibilitychange', () => { if (es && document.visibilityState === 'visible') keepAwake(); });

  /* ---------- alert display ---------- */
  function show(msg) {
    const kind = kindOf(msg.tags);
    const box = $('alert');
    box.className = 'alert ' + (kind === 'extreme' ? '' : kind);
    $('al-title').textContent = label(kind); box.dataset.kind = kind;
    $('al-place').textContent = placeOf(msg.title);
    $('al-msg').textContent = msg.message || '';
    box.hidden = false;
    $('al-ok').focus();
    playSiren(kind);
    addHistory(kind, msg);
  }
  function addHistory(kind, msg) { received.unshift({ kind, msg }); renderHistory(); }
  function renderHistory() {
    const list = $('hist');
    list.replaceChildren();
    if (!received.length) { const li = document.createElement('li'); li.className = 'none'; li.textContent = t('ph.none'); list.append(li); return; }
    received.forEach(({ kind, msg }) => {
      const li = document.createElement('li'); li.className = kind;
      const time = new Date((msg.time || Date.now() / 1000) * 1000).toLocaleTimeString(I18N.locale(), { hour: '2-digit', minute: '2-digit', second: '2-digit' });
      const head = document.createElement('div'); head.className = 't'; head.textContent = `${time}, ${label(kind)}`;
      const p = document.createElement('div'); p.textContent = placeOf(msg.title) || (msg.message || '').slice(0, 80);
      li.append(head, p); list.append(li);
    });
  }
  $('al-ok').addEventListener('click', () => { stopSiren(); $('alert').hidden = true; });

  /* ---------- connection ---------- */
  function setState(key, cls) { stateKey = key; stateCls = cls || ''; $('state').textContent = t(key); $('statebox').className = 'state ' + stateCls; }
  function connect(topic) {
    disconnect();
    es = new EventSource(`${NTFY}/${encodeURIComponent(topic)}/sse`);
    es.onopen = () => setState('ph.connected', 'live');
    es.onerror = () => setState('ph.lost', 'retry');
    es.onmessage = ev => {
      let msg; try { msg = JSON.parse(ev.data); } catch (e) { return; }
      if (msg.event === 'message') show(msg);
    };
  }
  function disconnect() { if (es) { es.close(); es = null; } }

  $('start').addEventListener('click', () => {
    const topic = $('topic').value.trim();
    if (!/^[A-Za-z0-9_-]{1,64}$/.test(topic)) { $('topic').focus(); $('topic').setCustomValidity(t('ph.invalid')); $('topic').reportValidity(); return; }
    $('topic').setCustomValidity('');
    unlockAudio(); keepAwake();
    if (navigator.vibrate) navigator.vibrate(60);
    $('ch').textContent = topic; $('ch2').textContent = topic;
    $('setup').hidden = true; $('live').hidden = false;
    setState('ph.connecting');
    connect(topic);
    try { history.replaceState(null, '', '?t=' + encodeURIComponent(topic)); } catch (e) { /* ignore */ }
  });
  $('stop').addEventListener('click', () => {
    disconnect(); stopSiren();
    if (wakeLock) { wakeLock.release().catch(() => {}); wakeLock = null; }
    $('live').hidden = true; $('setup').hidden = false;
  });
  const channelName = () => $('topic').value.trim() || t('ph.your-channel');
  function renderTexts() {
    setState(stateKey, stateCls);
    renderHistory();
    if (!$('alert').hidden && $('alert').dataset.kind) $('al-title').textContent = label($('alert').dataset.kind);
    if ($('live').hidden) $('ch2').textContent = channelName();
  }
  I18N.onChange(renderTexts);
  renderTexts();
})();
