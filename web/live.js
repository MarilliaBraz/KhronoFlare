/* Live fire detections from INPE (BDQueimadas), straight from the browser.
   INPE publishes a CSV with Brazil's fire detections every 10 minutes (GOES-19 every 10 min, plus polar
   satellites as they pass) and allows any page to read it (CORS *). This file lists the folder, reads the
   files of the last WINDOW_MIN minutes, and polls again every POLL_MS. Each CSV row: lat, lon, satelite,
   data (UTC). There is no fire intensity in these files; intensity comes from the FIRMS data.
   LiveFires.start(onUpdate) calls onUpdate(state) after every refresh, also when it fails. */
(() => {
  'use strict';
  const BASE = 'https://dataserver-coids.inpe.br/queimadas/queimadas/focos/csv/10min/';
  const WINDOW_MIN = 180;             // detections shown: last 3 hours
  const POLL_MS = 5 * 60 * 1000;      // INPE writes a file every 10 minutes; check twice as often
  const FILE_RE = /focos_10min_(\d{8})_(\d{4})\.csv/g;
  const cache = new Map();            // file name -> rows, so each file is read once

  const fileTime = name => {          // focos_10min_20261115_0930.csv -> Date (UTC)
    const m = /(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})/.exec(name);
    return new Date(Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4], +m[5]));
  };

  async function listFiles() {
    const r = await fetch(BASE, { cache: 'no-store' });
    if (!r.ok) throw new Error('INPE folder: HTTP ' + r.status);
    const html = await r.text();
    return [...new Set([...html.matchAll(FILE_RE)].map(m => m[0]))].sort();
  }

  function parse(text) {
    return text.trim().split('\n').slice(1).map(line => {
      const [lat, lon, sat, when] = line.split(',').map(s => s.trim());
      return { lat: +lat, lon: +lon, sat, time: new Date(String(when).replace(' ', 'T') + 'Z') };
    }).filter(p => Number.isFinite(p.lat) && Number.isFinite(p.lon) && !isNaN(p.time));
  }

  async function readFile(name) {
    if (cache.has(name)) return cache.get(name);
    const r = await fetch(BASE + name);
    if (!r.ok) throw new Error(name + ': HTTP ' + r.status);
    const rows = parse(await r.text());
    cache.set(name, rows);
    return rows;
  }

  async function refresh() {
    const fetchedAt = new Date();
    const names = await listFiles();
    if (!names.length) throw new Error('INPE folder is empty');
    const newest = names[names.length - 1], latest = fileTime(newest);
    const from = latest.getTime() - WINDOW_MIN * 60e3;
    const wanted = names.filter(n => fileTime(n).getTime() > from);
    const files = await Promise.all(wanted.map(async name => ({ name, url: BASE + name, time: fileTime(name), rows: await readFile(name) })));
    for (const key of cache.keys()) if (!wanted.includes(key)) cache.delete(key);   // forget files out of the window
    const points = files.flatMap(f => f.rows);
    const latestDetection = points.reduce((m, p) => (p.time > m ? p.time : m), new Date(0));
    return {
      status: 'live', source: BASE, windowMin: WINDOW_MIN, fetchedAt,
      latestFile: { name: newest, url: BASE + newest, time: latest },
      latestDetection: points.length ? latestDetection : null,
      files: files.map(f => ({ name: f.name, url: f.url, time: f.time, count: f.rows.length })),
      points,
    };
  }

  window.LiveFires = {
    WINDOW_MIN,
    start(onUpdate) {
      let last = null;
      const run = async () => {
        try { last = await refresh(); }
        catch (err) {
          console.warn('live fires:', err);
          last = { ...(last || { points: [], files: [] }), status: 'error', error: String(err.message || err), fetchedAt: new Date() };
        }
        onUpdate(last);
      };
      run();
      setInterval(run, POLL_MS);
      document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible') run(); });
    },
  };
})();
