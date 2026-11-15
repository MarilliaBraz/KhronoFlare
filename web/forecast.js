/* Next-month fire outlook for civil protection managers (forecast.html).
   Reads forecast.json (web/tools/build_forecast.py) and the state outlines from data.json.
   Map: squares of the outlook grid coloured by level, a ring on squares burning now.
   List: municipalities in priority order with the reason for each, filter by state and level, CSV export. */
(() => {
  'use strict';
  const t = (k, v) => I18N.t(k, v);
  const $ = id => document.getElementById(id);
  const PAGE = 60;                                    // municipalities shown before "Show more"
  const ACTIVE_RING = 3;                              // same threshold the outlook uses to raise a level
  const S = { fc: null, states: [], names: {}, uf: '', cls: 'all', shown: PAGE, selected: null };

  const esc = s => String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const num = (n, d = 0) => Number(n).toLocaleString(I18N.locale(), { maximumFractionDigits: d, minimumFractionDigits: 0 });
  const css = name => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  const monthName = () => {
    const [y, m] = S.fc.meta.target.split('-').map(Number);
    return new Date(Date.UTC(y, m - 1, 1)).toLocaleDateString(I18N.locale(), { month: 'long', timeZone: 'UTC' });
  };
  const monthYear = () => {
    const [y, m] = S.fc.meta.target.split('-').map(Number);
    return new Date(Date.UTC(y, m - 1, 1)).toLocaleDateString(I18N.locale(), { month: 'long', year: 'numeric', timeZone: 'UTC' });
  };
  const when = iso => new Date(iso).toLocaleString(I18N.locale(), { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });

  /* ---------- map ---------- */
  const BRAZIL = L.latLngBounds([-34, -74.5], [5.5, -33]);
  const FALLBACK_BOUNDS = [[-61.6064, -101.25], [31.9522, 0]];
  const GIBS = 'https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/BlueMarble_ShadedRelief_Bathymetry/default/2004-08-01/GoogleMapsCompatible_Level8/{z}/{y}/{x}.jpeg';
  const map = L.map('map', { zoomControl: false, minZoom: 3, maxZoom: 11, zoomSnap: 0.25, maxBounds: BRAZIL.pad(0.6) });
  map.attributionControl.setPrefix('<a href="https://leafletjs.com" target="_blank" rel="noopener">Leaflet</a>');
  L.control.zoom({ position: 'bottomright' }).addTo(map);
  map.createPane('fallback'); map.getPane('fallback').style.zIndex = 150;
  L.imageOverlay('fallback-relief.jpg', FALLBACK_BOUNDS, { pane: 'fallback', interactive: false }).addTo(map);
  let tileLoads = 0, tileErrors = 0;
  L.tileLayer(GIBS, { maxNativeZoom: 8, maxZoom: 11, bounds: BRAZIL.pad(0.6),
    attribution: '<a href="https://earthdata.nasa.gov/gibs" target="_blank" rel="noopener">NASA GIBS</a> Blue Marble · IBGE · NASA FIRMS' })
    .on('tileload', () => { if (++tileLoads === 1) $('mapnote').hidden = true; })
    .on('tileerror', () => { if (++tileErrors >= 6 && tileLoads === 0) $('mapnote').hidden = false; })
    .addTo(map);
  map.fitBounds(BRAZIL, { animate: false });
  const renderer = L.canvas({ padding: 0.3 });
  const lStates = L.layerGroup().addTo(map), lCells = L.layerGroup().addTo(map), lSel = L.layerGroup().addTo(map);
  const ll = ring => ring.map(([x, y]) => [y, x]);
  const cellBounds = (cy, cx, res) => [[cy * res, cx * res], [(cy + 1) * res, (cx + 1) * res]];

  function drawStates() {
    lStates.clearLayers();
    S.states.forEach(s => L.polygon(s.g.map(p => p.map(ll)), { color: '#ffffff', opacity: 0.6, weight: 1, fill: false, interactive: false }).addTo(lStates));
  }

  function drawCells() {
    lCells.clearLayers();
    const { res } = S.fc.meta;
    const fill = { high: css('--f3'), medium: css('--f1') };
    const ring = css('--ink') || '#000';
    const minProb = S.fc.meta.model ? S.fc.meta.model.min_prob : Infinity;
    const accent = css('--accent');
    S.fc.cells.forEach(([cy, cx, cls, , , active, prob]) => {
      if (cls === 'low') return;
      L.rectangle(cellBounds(cy, cx, res), { renderer, stroke: active >= ACTIVE_RING, color: ring, weight: 1.5,
        fillColor: fill[cls], fillOpacity: cls === 'high' ? 0.62 : 0.45, interactive: false }).addTo(lCells);
      if (prob != null && prob >= minProb) {
        const [[s, w], [n, e]] = cellBounds(cy, cx, res), pad = res * 0.12;
        L.rectangle([[s + pad, w + pad], [n - pad, e - pad]], { renderer, color: accent, weight: 2, dashArray: '4 3',
          fill: false, interactive: false }).addTo(lCells);
      }
    });
  }

  function select(m) {
    S.selected = m.id;
    lSel.clearLayers();
    const city = S.cities[m.id];
    if (city) {
      const { res } = S.fc.meta;
      const [cy, cx] = [Math.floor(city.lat / res), Math.floor(city.lon / res)];
      L.rectangle(cellBounds(cy, cx, res), { color: css('--accent'), weight: 3, fill: false, interactive: false }).addTo(lSel);
      L.circleMarker([city.lat, city.lon], { radius: 5, color: '#fff', weight: 2, fillColor: css('--accent'), fillOpacity: 1, interactive: false }).addTo(lSel);
      map.flyTo([city.lat, city.lon], Math.max(map.getZoom(), 7), { animate: !matchMedia('(prefers-reduced-motion: reduce)').matches });
    }
    $('fc-maptitle').textContent = `${m.name} (${m.uf})`;
    document.querySelectorAll('.fc-item').forEach(li => li.setAttribute('aria-current', String(li.dataset.id === m.id)));
  }

  function zoomToState() {
    lSel.clearLayers(); S.selected = null;
    const st = S.states.find(s => s.uf === S.uf);
    if (st) map.fitBounds(L.polygon(st.g.map(p => p.map(ll))).getBounds(), { padding: [12, 12] });
    else map.fitBounds(BRAZIL);
    $('fc-maptitle').textContent = S.uf ? (S.names[S.uf] || S.uf) : t('fc.brazil');
  }

  /* ---------- list ---------- */
  const filtered = () => S.fc.municipalities.filter(m => (!S.uf || m.uf === S.uf) && (S.cls === 'all' || m.cls === S.cls));

  function reason(m) {
    const [from, to] = S.fc.meta.history_years;
    const parts = [m.years > 0
      ? t('fc.reason.hist', { y: m.years, n: m.n_years, month: monthName(), m: num(m.mean, 1) })
      : t('fc.reason.nohist', { month: monthName(), from, to })];
    if (m.active_mun > 0) parts.push(t('fc.reason.now', { a: num(m.active_mun) }));
    else if (m.active_cell >= ACTIVE_RING) parts.push(t('fc.reason.near', { a: num(m.active_cell) }));
    const mod = S.fc.meta.model;
    if (mod && m.prob != null && m.prob >= mod.min_prob)
      parts.push(t('fc.reason.model', { p: Math.round(m.prob * 100), b: Math.round(mod.base_rate * 100), month: monthName() }));
    return parts.join(' · ');
  }

  function renderList() {
    const inState = S.fc.municipalities.filter(m => !S.uf || m.uf === S.uf);
    const counts = { all: inState.length, high: inState.filter(m => m.cls === 'high').length, medium: inState.filter(m => m.cls === 'medium').length };
    document.querySelectorAll('[data-c]').forEach(b => {
      b.setAttribute('aria-pressed', String(b.dataset.c === S.cls));
      b.querySelector('.n').textContent = num(counts[b.dataset.c]);
    });
    const rows = filtered();
    $('fc-list').innerHTML = rows.slice(0, S.shown).map((m, i) => `
      <li class="fc-item" data-id="${esc(m.id)}" aria-current="${m.id === S.selected}">
        <button class="fc-row" data-id="${esc(m.id)}">
          <span class="fc-rank num">${i + 1}</span>
          <span class="fc-body"><span class="fc-name">${esc(m.name)} <span class="fc-uf">${esc(m.uf)}</span></span>
            <span class="fc-why">${esc(reason(m))}</span></span>
          <span class="fc-chip" data-cls="${m.cls}">${t('fc.cls.' + m.cls)}</span>
        </button></li>`).join('') || `<li class="empty">${t('fc.empty')}</li>`;
    const rest = rows.length - S.shown;
    $('fc-more').hidden = rest <= 0;
    if (rest > 0) $('fc-more').textContent = t('fc.more', { n: num(Math.min(rest, PAGE)) });
  }

  function renderHeader() {
    const { meta } = S.fc;
    const [from, to] = meta.history_years;
    const vars = { month: monthYear(), from, to, when: when(meta.generated) };
    $('fc-kind').textContent = t(meta.active_counted ? 'fc.kind' : 'fc.kind.noactive', vars) +
      (meta.model ? t('fc.kind.model', { d: new Date(meta.model.data_until + 'T12:00:00Z').toLocaleDateString(I18N.locale(), { day: 'numeric', month: 'short', timeZone: 'UTC' }) }) : '');
    $('fc-sw-model').hidden = !meta.model;
    $('fc-banner').dataset.state = meta.active_counted ? 'ok' : 'warn';
    const r = meta.rule;
    $('fc-rule').innerHTML = t('fc.rule', { res: meta.res, from, to, month: monthName(),
      hs: Math.round(r.high_share * 100), hm: r.high_mean, ms: Math.round(r.medium_share * 100), mm: r.medium_mean, am: r.active_min }) +
      (meta.model ? t('fc.rule.model', { p: Math.round(meta.model.min_prob * 100), b: Math.round(meta.model.base_rate * 100),
        month: monthName(), auc: num(meta.model.roc_auc_temporal, 2), from: meta.model.train_years[0], to: meta.model.train_years[1],
        until: meta.model.data_until }) : t('fc.rule.nomodel'));
    const all = S.fc.municipalities;
    $('fc-stats').textContent = t('fc.stats', { h: num(all.filter(m => m.cls === 'high').length),
      m: num(all.filter(m => m.cls === 'medium').length), c: num(S.fc.cells.filter(c => c[2] !== 'low').length) });
    const sel = $('fc-uf');
    sel.innerHTML = `<option value="">${esc(t('fc.allstates'))}</option>` +
      Object.keys(S.names).sort((a, b) => S.names[a].localeCompare(S.names[b], I18N.locale()))
        .map(uf => `<option value="${uf}" ${uf === S.uf ? 'selected' : ''}>${esc(S.names[uf])} (${uf})</option>`).join('');
    if (!S.selected) $('fc-maptitle').textContent = S.uf ? (S.names[S.uf] || S.uf) : t('fc.brazil');
  }

  function downloadCsv() {
    const head = ['rank', 'ibge', 'municipality', 'uf', 'level', 'years_with_fire', 'years', 'mean_hotspots',
      'active_hotspots_municipality', 'active_hotspots_square', 'model_probability_worse_than_normal', 'target_month', 'generated'];
    const q = v => /[",\n;]/.test(String(v)) ? `"${String(v).replace(/"/g, '""')}"` : String(v);
    const lines = filtered().map((m, i) => [i + 1, m.id, m.name, m.uf, m.cls, m.years, m.n_years, m.mean,
      m.active_mun, m.active_cell, m.prob ?? '', S.fc.meta.target, S.fc.meta.generated].map(q).join(','));
    const blob = new Blob(['﻿' + [head.join(','), ...lines].join('\n')], { type: 'text/csv;charset=utf-8' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `fire-outlook-${S.fc.meta.target}${S.uf ? '-' + S.uf : ''}.csv`;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }

  /* ---------- events ---------- */
  $('fc-list').addEventListener('click', e => {
    const b = e.target.closest('.fc-row'); if (!b) return;
    const m = S.fc.municipalities.find(x => x.id === b.dataset.id); if (m) select(m);
  });
  $('fc-more').addEventListener('click', () => { S.shown += PAGE; renderList(); });
  $('fc-uf').addEventListener('change', e => { S.uf = e.target.value; S.shown = PAGE; zoomToState(); renderList(); });
  document.querySelectorAll('[data-c]').forEach(b => b.addEventListener('click', () => { S.cls = b.dataset.c; S.shown = PAGE; renderList(); }));
  $('zoom-out').addEventListener('click', () => { S.uf = ''; $('fc-uf').value = ''; S.shown = PAGE; zoomToState(); renderList(); });
  $('fc-csv').addEventListener('click', downloadCsv);
  I18N.onChange(() => { if (S.fc) { renderHeader(); renderList(); } });
  $('contrast').addEventListener('click', () => setTimeout(() => S.fc && drawCells(), 0));
  window.addEventListener('resize', () => map.invalidateSize());

  /* ---------- load ---------- */
  const getJson = url => fetch(url, { cache: 'no-cache' }).then(r => { if (!r.ok) throw new Error(`${url}: HTTP ${r.status}`); return r.json(); });
  Promise.all([getJson('forecast.json'), getJson('cities.json'), getJson('data.json').catch(() => getJson('data-sample.json'))])
    .then(([fc, cities, data]) => {
      S.fc = fc;
      S.states = data.states || [];
      S.names = Object.fromEntries(cities.states.map(s => [s.uf, s.name]));
      S.cities = Object.fromEntries(cities.cities.map(([id, , , lat, lon]) => [id, { lat, lon }]));
      drawStates(); drawCells(); renderHeader(); renderList();
    })
    .catch(err => {
      console.error('forecast: load failed', err);
      $('fc-kind').textContent = t('fc.fail');
      $('fc-banner').dataset.state = 'bad';
    });
})();
