// Real-phone channel.
// When an alert is approved or cancelled in the console, it is published to a channel on ntfy.sh.
// Two ways to receive it on a phone:
//   * "Alert page": phone.html, full screen with siren. It must be served from an address the phone can open
//     (GitHub Pages, for example). localhost only works on this computer.
//   * "ntfy": the ntfy web page or app subscribed to the channel. Works on any phone with internet.
"use strict";
(function () {
  const NTFY = 'https://ntfy.sh';
  const STORE = 'hac-ntfy-topic', STORE_BASE = 'hac-phone-base';
  const $ = id => document.getElementById(id);
  const isLocal = /^(localhost|127\.0\.0\.1|\[::1\])$/.test(location.hostname);
  const get = k => { try { return localStorage.getItem(k); } catch (e) { return null; } };
  const put = (k, v) => { try { v == null ? localStorage.removeItem(k) : localStorage.setItem(k, v); } catch (e) { /* storage blocked */ } };

  function randomTopic() {
    const a = new Uint8Array(10);
    crypto.getRandomValues(a);
    return 'hac-' + Array.from(a, b => (b % 36).toString(36)).join('');
  }
  let topic = get(STORE);
  if (!topic) { topic = randomTopic(); put(STORE, topic); }

  // Where phone.html lives. Default: this page's folder, unless it is localhost.
  let base = get(STORE_BASE) || (isLocal ? '' : new URL('.', location.href).href);
  let mode = base ? 'page' : 'ntfy';

  const KIND = {
    extreme: { label: 'Extreme alert', tags: ['rotating_light', 'extreme'], priority: 5 },
    severe:  { label: 'Severe alert',  tags: ['warning', 'severe'],         priority: 4 },
    cancel:  { label: 'Alert cancelled', tags: ['white_check_mark', 'cancel'], priority: 3 },
    test:    { label: 'Test message',  tags: ['test_tube', 'test'],         priority: 3 }
  };

  function pageUrl() {
    if (!base) return '';
    try { return new URL('phone.html?t=' + encodeURIComponent(topic), base.endsWith('/') ? base : base + '/').href; }
    catch (e) { return ''; }
  }
  function ntfyUrl() { return `${NTFY}/${encodeURIComponent(topic)}`; }
  function target() { return mode === 'page' ? pageUrl() : ntfyUrl(); }

  function drawQr(url) {
    const box = $('rp-qr'); box.innerHTML = '';
    if (!url) { box.textContent = 'Add the page address below'; return; }
    if (window.QRCode) {
      try { new QRCode(box, { text: url, width: 150, height: 150, correctLevel: QRCode.CorrectLevel.M }); return; }
      catch (e) { /* fall through */ }
    }
    box.textContent = 'QR code unavailable';
  }

  function render() {
    document.querySelectorAll('[data-rpmode]').forEach(b => b.setAttribute('aria-pressed', b.dataset.rpmode === mode));
    const url = target();
    drawQr(url);
    const a = $('rp-link'); a.href = url || '#'; a.textContent = url || '(set the page address first)';
    $('rp-topic').textContent = topic; $('rp-app').textContent = topic;
    $('rp-base').value = base;
    $('rp-page-help').hidden = mode !== 'page';
    $('rp-ntfy-help').hidden = mode !== 'ntfy';
    const warn = $('rp-basewarn');
    warn.hidden = !(mode === 'page' && (!base || /\/\/(localhost|127\.0\.0\.1)/.test(base)));
  }

  function status(text, cls) { const s = $('rp-status'); s.textContent = text; s.className = 'rp-status ' + (cls || ''); }

  async function publish(kind, place, message) {
    const k = KIND[kind];
    status('Sending to the phone channel…');
    try {
      // JSON publish to the root URL; a plain-text body keeps it a simple CORS request.
      const r = await fetch(NTFY, {
        method: 'POST',
        body: JSON.stringify({ topic, title: `SIMULATION · ${k.label} · ${place}`, message, priority: k.priority, tags: k.tags })
      });
      if (!r.ok) throw new Error('HTTP ' + r.status);
      status(`${k.label} delivered to the channel at ${new Date().toLocaleTimeString()}`, 'ok');
      return true;
    } catch (e) {
      status(`Could not reach ntfy.sh (${e.message}). The phone preview on this page still works.`, 'bad');
      return false;
    }
  }

  window.realPhone = {
    send(kind, c, message) {
      if (!$('rp-on').checked) return;
      return publish(kind, `${c.name} (${c.uf})`, message);
    }
  };

  document.querySelectorAll('[data-rpmode]').forEach(b => b.addEventListener('click', () => { mode = b.dataset.rpmode; render(); }));
  $('rp-basesave').addEventListener('click', () => {
    let v = $('rp-base').value.trim();
    if (v && !/^https?:\/\//i.test(v)) v = 'https://' + v;
    try { if (v) new URL(v); } catch (e) { status('That address is not valid. Example: https://your-user.github.io/nasa-space-apps-2026/web/', 'bad'); return; }
    base = v; put(STORE_BASE, v || null); render();
    status(v ? 'Page address saved. Scan the new code.' : 'Page address cleared.', v ? 'ok' : '');
  });
  $('rp-test').addEventListener('click', () =>
    publish('test', 'Test', 'Test from the Hotspot Alert Console. If you can read this, the phone is connected.'));
  $('rp-new').addEventListener('click', () => {
    topic = randomTopic(); put(STORE, topic); render();
    status('New channel created. Scan the new code on the phone.');
  });
  $('rp-copy').addEventListener('click', () => {
    const url = target();
    if (!url) { status('Set the page address first.', 'bad'); return; }
    try { navigator.clipboard.writeText(url).then(() => status('Link copied.', 'ok'), () => status('Copy failed. Select the link and copy it.', 'bad')); }
    catch (e) { status('Copy failed. Select the link and copy it.', 'bad'); }
  });
  render();
})();
