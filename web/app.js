// Hotspot Alert Console: front-end logic.
// Loads data.json (fire detections + candidate municipalities) and runs the alert workflow.
"use strict";

function main(D, C) {
  // Live data (build_live.py) sends points as lists in the order of point_fields; rebuild the objects.
  if(D.point_fields) D.points = D.points.map(a => Object.fromEntries(D.point_fields.map((f,i)=>[f, a[i]])));
  const CITIES = C ? C.cities : [];   // [ibge_id, name, uf, lat, lon, capital]; empty if cities.json failed
  const S = {role:'analyst', juris:'PA', filter:'all', sel:null, sound:true, items:{}, log:[], lastCap:null, phone:null, open:{}, phonecap:['phone.none',{}], expanded:new Set(['PA'])};
  const BRT = -3;
  const esc = s => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const t = (k, v) => I18N.t(k, v);
  const fmt1 = n => n.toLocaleString(I18N.locale(),{maximumFractionDigits:1, minimumFractionDigits:1});
  const fmtInt = n => Math.round(n).toLocaleString(I18N.locale());
  const hhmm = t => t.slice(0,2)+':'+t.slice(2);
  const brtFromUtc = t => { let h = (parseInt(t.slice(0,2),10)+24+BRT)%24; return String(h).padStart(2,'0')+':'+t.slice(2); };
  const nowBrt = () => new Date(Date.now()+BRT*3600e3);
  const clock = d => String(d.getUTCHours()).padStart(2,'0')+':'+String(d.getUTCMinutes()).padStart(2,'0');
  const clockS = d => clock(d)+':'+String(d.getUTCSeconds()).padStart(2,'0');

  /* ---------- scoring (provisional) ---------- */
  D.cands.forEach(c => {
    c.score = c.frpMax + 0.5*c.n + 5*c.high;
    c.tier = c.score >= 50 ? 'high' : c.score >= 20 ? 'elev' : 'watch';
    c.bbox = bboxOf(c.geom.flat(2));
  });
  D.cands.sort((a,b) => b.score - a.score);
  const byId = Object.fromEntries(D.cands.map(c => [c.id, c]));
  const tierName = tier => t('tier.'+tier);
  const STATUS_CLASS = {new:'', draft:'draft', pending:'pending', sent:'sent', cancelled:'', dismissed:''};
  const statusChip = s => `<span class="chip ${STATUS_CLASS[s]}">${t('status.'+s)}</span>`;
  function item(id){ return S.items[id] ||= {status:'new', level:'severe', lang:'en', event:'wildfire', action:'avoid', hours:6, areaMode:'hull', msg:'', edited:false, ack:false}; }
  function bboxOf(pts){ let x0=1e9,y0=1e9,x1=-1e9,y1=-1e9; for(const [x,y] of pts){ if(x<x0)x0=x; if(x>x1)x1=x; if(y<y0)y0=y; if(y>y1)y1=y; } return [x0,y0,x1,y1]; }

  /* ---------- area ---------- */
  function ringArea(r, lat0){ let a=0; for(let i=0;i<r.length;i++){ const [x1,y1]=r[i], [x2,y2]=r[(i+1)%r.length]; a+=x1*y2-x2*y1; } return Math.abs(a)/2*111.32*111.32*Math.cos(lat0*Math.PI/180); }
  function munArea(c){ const lat0=(c.bbox[1]+c.bbox[3])/2; return c.geom.reduce((s,poly)=> s + ringArea(poly[0],lat0) - poly.slice(1).reduce((t,h)=>t+ringArea(h,lat0),0), 0); }
  function areaOf(c,it){ return it.areaMode==='hull' ? c.areaKm2 : munArea(c); }

  /* ---------- who the alert reaches: municipal seats inside the alert polygon ---------- */
  function inRing(x, y, ring){ let ins=false; for(let i=0,j=ring.length-1;i<ring.length;j=i++){ const [xi,yi]=ring[i], [xj,yj]=ring[j];
    if((yi>y)!==(yj>y) && x < (xj-xi)*(y-yi)/(yj-yi)+xi) ins=!ins; } return ins; }
  function inPolys(x, y, polys){ return polys.some(poly => inRing(x,y,poly[0]) && !poly.slice(1).some(h=>inRing(x,y,h))); }
  function citiesIn(c, it){
    const polys = it.areaMode==='hull' ? [[c.poly]] : c.geom;
    const pts = polys.flat(2), x0=Math.min(...pts.map(p=>p[0])), x1=Math.max(...pts.map(p=>p[0])), y0=Math.min(...pts.map(p=>p[1])), y1=Math.max(...pts.map(p=>p[1]));
    return CITIES.filter(k => k[4]>=x0 && k[4]<=x1 && k[3]>=y0 && k[3]<=y1 && inPolys(k[4], k[3], polys))
      .sort((a,b)=> b[5]-a[5] || a[1].localeCompare(b[1], 'pt-BR'));
  }
  function reachHtml(c, it){
    if(!CITIES.length) return '';
    const ks = citiesIn(c, it);
    const list = ks.map(k=>`<li${k[5]?' class="cap"':''}>${esc(k[1])} <span class="uf">${k[2]}</span></li>`).join('');
    return `<div class="reach"><span class="reach-h">${t('reach.h',{n:ks.length})}</span>${ks.length ? `<ul>${list}</ul>` : `<p class="hint">${t('reach.none')} ${nearestTown(c)}</p>`}</div>`;
  }
  // Nearest municipal seat to the centre of the municipality's fires, with the distance in km.
  function nearestTown(c){
    const fs = D.points.filter(p=>p.mun===c.id); if(!fs.length) return '';
    const lat = fs.reduce((s,p)=>s+p.lat,0)/fs.length, lon = fs.reduce((s,p)=>s+p.lon,0)/fs.length;
    const km = (a,b,c2,d) => { const r=Math.PI/180, x=Math.sin((c2-a)*r/2)**2 + Math.cos(a*r)*Math.cos(c2*r)*Math.sin((d-b)*r/2)**2; return 12742*Math.asin(Math.sqrt(x)); };
    let best=null, bd=Infinity; CITIES.forEach(k=>{ const d=km(lat,lon,k[3],k[4]); if(d<bd){ bd=d; best=k; } });
    return best ? t('reach.nearest',{name:esc(best[1]), uf:best[2], km:fmtInt(bd)}) : '';
  }

  /* ---------- message ---------- */
  const T = {
    en:{ title:{wildfire:'WILDFIRE ALERT', smoke:'HEAVY SMOKE ALERT', risk:'HIGH FIRE RISK'},
         what:{wildfire:n=>`Satellites detected ${n} active fire point${n>1?'s':''} in the area.`, smoke:()=>`Smoke from active fires is affecting the area.`, risk:()=>`Dry weather and nearby fires raise the risk of new fires.`},
         act:{avoid:'Do not burn waste or vegetation and stay away from the fire area.', indoors:'Stay indoors, close windows and protect children and older people from smoke.', evacuate:'Get ready to leave the area and follow instructions from the fire department.'},
         until:'Valid until', help:'Emergencies: 193 (fire) / 199 (civil protection).',
         cancel:(n,u)=>`ALERT CANCELLED – ${n} (${u}). The previous fire alert no longer applies.` },
    pt:{ title:{wildfire:'ALERTA DE INCÊNDIO', smoke:'ALERTA DE FUMAÇA', risk:'RISCO ALTO DE INCÊNDIO'},
         what:{wildfire:n=>`Satélites detectaram ${n} foco${n>1?'s':''} de fogo ativo${n>1?'s':''} na região.`, smoke:()=>`Fumaça de queimadas atinge a região.`, risk:()=>`Tempo seco e focos próximos aumentam o risco de novos incêndios.`},
         act:{avoid:'Não queime lixo nem vegetação e afaste-se da área do fogo.', indoors:'Fique em casa, feche as janelas e proteja crianças e idosos da fumaça.', evacuate:'Prepare-se para deixar a área e siga as orientações dos Bombeiros.'},
         until:'Válido até', help:'Emergência: 193 (Bombeiros) / 199 (Defesa Civil).',
         cancel:(n,u)=>`ALERTA CANCELADO – ${n} (${u}). O alerta de incêndio anterior não vale mais.` }
  };
  function untilText(it){ const d=new Date(nowBrt().getTime()+it.hours*3600e3); return `${String(d.getUTCDate()).padStart(2,'0')}/${String(d.getUTCMonth()+1).padStart(2,'0')} ${clock(d)}`; }
  function autoMsg(c,it){ const t=T[it.lang]; return `${t.title[it.event]} – ${c.name} (${c.uf}). ${t.what[it.event](c.n)} ${t.act[it.action]} ${t.until} ${untilText(it)}. ${t.help}`; }
  function msgOf(c,it){ return it.edited ? it.msg : autoMsg(c,it); }

  /* ---------- guardrails ---------- */
  function localHour(){ return nowBrt().getUTCHours(); }
  function checks(c,it){
    const out=[]; const msg=msgOf(c,it);
    const inJ = c.uf===S.juris;
    out.push({k:inJ?'ok':'fail', hard:true, txt: inJ?t('chk.inj',{j:S.juris}):t('chk.outj',{j:S.juris, uf:c.uf})});
    const complete = msg.includes(c.name) && /valid until|válido até/i.test(msg);
    out.push({k:complete?'ok':'fail', hard:true, txt: complete?t('chk.complete'):t('chk.incomplete')});
    const a=areaOf(c,it);
    out.push({k:a<=2000?'ok':'warn', txt: a<=2000?t('chk.area',{a:fmtInt(a)}):t('chk.bigarea',{a:fmtInt(a), max:fmtInt(2000)})});
    const h=localHour(), night=(h>=22||h<6);
    out.push({k:(night&&it.level==='extreme')?'warn':'ok', txt:(night&&it.level==='extreme')?t('chk.night',{h:String(h).padStart(2,'0')}):t('chk.time')});
    out.push({k:msg.length<=360?'ok':'warn', txt: msg.length<=360?t('chk.len',{n:msg.length}):t('chk.long',{n:msg.length})});
    out.push({k:'info', txt:t('chk.second')});
    return out;
  }
  const hardFail = cs => cs.some(x=>x.hard && x.k==='fail');
  const softWarn = cs => cs.some(x=>x.k==='warn');

  /* ---------- log ---------- */
  // role and text are [key, vars] so the log follows the interface language
  function addLog(role, text){ S.log.unshift({t:clockS(nowBrt()), role, text}); renderLog(); }
  const analyst = () => ['role.analyst',{uf:S.juris}], approver = ['role.approver',{}];
  // Log values stay raw (level code, area number) and are formatted when the log is drawn.
  const logVars = v => ({...v, ...(v.level ? {level:t('lvl.'+v.level).toLowerCase()} : {}), ...(v.a!=null ? {a:fmtInt(v.a)} : {})});
  function renderLog(){
    const el=document.getElementById('log');
    document.getElementById('logn').textContent=S.log.length;
    el.innerHTML = S.log.length ? S.log.map(l=>`<li><span class="t">${l.t}</span><span class="r">${esc(t(...l.role))}</span><span>${esc(t(l.text[0], logVars(l.text[1])))}</span></li>`).join('') : `<li class="empty">${t('log.empty')}</li>`;
  }


  /* ---------- queue ---------- */
  function isOpen(s){ return s==='new'||s==='draft'||s==='pending'; }
  function isAlert(s){ return s==='pending'||s==='sent'||s==='cancelled'; }
  function visible(){ return D.cands.filter(c=>{ const s=item(c.id).status; if(S.filter==='open') return isOpen(s) && (s!=='new' || c.uf===S.juris); if(S.filter==='active') return isAlert(s); return true; }); }
  /* All 27 states, grouped by region. A state opens to show its municipalities with fire;
     states without fire are listed too, so the analyst sees the whole country. */
  const REGION_ORDER = ['North','Northeast','Central-West','Southeast','South'];
  const STATES = (C ? C.states : D.states.map(s=>({uf:s.uf, name:s.uf, region:'North'})));
  const stateGeom = Object.fromEntries(D.states.map(s=>[s.uf, s.g]));
  const TIER_RANK = {high:3, elev:2, watch:1};
  const firesTxt = n => t(n>1?'q.fires.n':'q.fires.1',{n:fmtInt(n)});
  const FIRES_BY_UF = D.points.reduce((m,p)=>{ if(p.uf) m[p.uf]=(m[p.uf]||0)+1; return m; }, {});
  function stateSummary(uf){
    const cs = D.cands.filter(c=>c.uf===uf);
    const fires = FIRES_BY_UF[uf] || 0;
    const top = cs.reduce((m,c)=> TIER_RANK[c.tier] > (TIER_RANK[m]||0) ? c.tier : m, null);
    return {cs, fires, top};
  }
  function renderQueue(){
    const n={all:D.cands.length, open:0, active:0};
    D.cands.forEach(c=>{ const s=item(c.id).status; if(isOpen(s) && (s!=='new' || c.uf===S.juris)) n.open++; if(isAlert(s)) n.active++; });
    document.querySelectorAll('.filters button').forEach(b=>{ const e=b.querySelector('.n'); if(e) e.textContent=n[b.dataset.f]; });
    const shown = new Set(visible().map(c=>c.id));
    const row = c=>{
      const it=item(c.id), ra=rowAction(c,it);
      const btn = ra ? `<button class="qact ${ra[2]}" data-qa="${ra[0]}" aria-label="${ra[1]} ${esc(c.name)}">${ra[1]}</button>` : '';
      const chip = it.status==='new' ? '' : ' '+statusChip(it.status);
      return `<li class="qitem t-${c.tier}" role="button" tabindex="0" data-id="${c.id}" aria-current="${S.sel===c.id}">
        <span class="stripe"></span><span class="qname">${esc(c.name)}</span>${btn}
        <span class="qmeta"><span class="tier">${tierName(c.tier)}</span><span class="num">${t(c.n>1?'q.fires.n':'q.fires.1',{n:c.n})}</span><span class="num">${t('q.max',{v:fmt1(c.frpMax)})}</span>${chip}</span></li>`;
    };
    const stateRow = st=>{
      const sum = stateSummary(st.uf), cs = sum.cs.filter(c=>shown.has(c.id));
      if(S.filter!=='all' && !cs.length) return '';
      const open = S.expanded.has(st.uf), mine = st.uf===S.juris;
      const meta = !sum.fires ? t('st.none') : sum.cs.length ? t('st.in',{f:firesTxt(sum.fires), m:t(sum.cs.length>1?'st.mun.n':'st.mun.1',{n:sum.cs.length})}) : firesTxt(sum.fires);
      const head = `<li class="srow${sum.fires?' t-'+sum.top:' calm'}${mine?' mine':''}"><button class="sbtn" data-uf="${st.uf}" aria-expanded="${open}">
        <span class="sname">${esc(st.name)} <span class="uf">${st.uf}</span>${mine?` <span class="you">${t('st.yours')}</span>`:''}</span>
        <span class="smeta">${sum.top?`<span class="tier">${tierName(sum.top)}</span>`:''}<span>${meta}</span></span></button></li>`;
      return head + (open && cs.length ? `<li class="sgroup"><ul>${cs.map(row).join('')}</ul></li>` : '');
    };
    const html = REGION_ORDER.map(reg=>{
      const sts = STATES.filter(s=>s.region===reg)
        .sort((a,b)=> stateSummary(b.uf).fires - stateSummary(a.uf).fires || a.name.localeCompare(b.name, I18N.locale()));
      const rows = sts.map(stateRow).join('');
      return rows ? `<li class="qgroup" role="presentation">${t('region.'+reg)}</li>${rows}` : '';
    }).join('');
    document.getElementById('queue').innerHTML = html || `<li class="empty">${t(S.filter==='open'?'q.empty.open':'q.empty.active')}</li>`;
  }
  function stateBounds(uf){ return L.polygon(geomLL(stateGeom[uf])).getBounds(); }

  /* ---------- map (Leaflet + NASA GIBS imagery) ---------- */
  // Most recent day of imagery: today once the afternoon passes over Brazil are in (after 21 UTC), else yesterday.
  const SAT_DATE = (()=>{ const d=new Date(); if(d.getUTCHours()<21) d.setUTCDate(d.getUTCDate()-1); return d.toISOString().slice(0,10); })();
  const GIBS = 'https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/';
  const BASES = {
    sat:    {path:`VIIRS_NOAA20_CorrectedReflectance_TrueColor/default/${SAT_DATE}/GoogleMapsCompatible_Level9/{z}/{y}/{x}.jpg`, max:9, credit:'VIIRS NOAA-20 true color'},
    relief: {path:'BlueMarble_ShadedRelief_Bathymetry/default/2004-08-01/GoogleMapsCompatible_Level8/{z}/{y}/{x}.jpeg', max:8, credit:'Blue Marble'},
    night:  {path:'VIIRS_Black_Marble/default/2016-01-01/GoogleMapsCompatible_Level8/{z}/{y}/{x}.png', max:8, credit:'VIIRS Black Marble'},
  };
  const BRAZIL = L.latLngBounds([-34, -74.5], [5.5, -33]);
  const reduceMotion = () => matchMedia('(prefers-reduced-motion: reduce)').matches;
  const ll = ring => ring.map(([x,y]) => [y,x]);       // data is [lon, lat]; Leaflet wants [lat, lon]
  const geomLL = geom => geom.map(poly => poly.map(ll));
  const fireColor = f => f>40?'var(--f3)':f>=10?'var(--f2)':'var(--f1)';
  const map = L.map('map', {zoomControl:false, minZoom:3, maxZoom:11, zoomSnap:0.25, maxBounds:BRAZIL.pad(0.6), attributionControl:true});
  map.attributionControl.setPrefix('<a href="https://leafletjs.com" target="_blank" rel="noopener">Leaflet</a>');
  const zoomCtl = L.control.zoom({position:'bottomright'}).addTo(map);
  let baseKey = (()=>{ try { return localStorage.getItem('hac-base'); } catch(e){ return null; } })();
  if(!BASES[baseKey]) baseKey='sat';
  let baseLayer=null, tileErrors=0, tileLoads=0;
  const TILE_RETRIES = 3;
  const lStates=L.layerGroup().addTo(map), lSel=L.layerGroup().addTo(map), lPts=L.layerGroup().addTo(map);
  function setBase(key){
    baseKey=key; try { localStorage.setItem('hac-base', key); } catch(e){}
    if(baseLayer) map.removeLayer(baseLayer);
    const b=BASES[key]; tileErrors=0; tileLoads=0;
    baseLayer=L.tileLayer(GIBS+b.path, {maxNativeZoom:b.max, maxZoom:11, bounds:BRAZIL.pad(0.6),
      attribution:`<a href="https://earthdata.nasa.gov/gibs" target="_blank" rel="noopener">NASA GIBS</a> ${b.credit} · IBGE`});
    // GIBS sometimes answers 503 under load: retry each tile a few times, spaced out, before giving up.
    baseLayer.on('tileerror', e=>{
      const img=e.tile, tries=+(img.dataset.tries||0), src=img.src;
      if(tries < TILE_RETRIES){ img.dataset.tries=tries+1; setTimeout(()=>{ img.src=''; img.src=src; }, 1500*(tries+1)); return; }
      if(++tileErrors >= 6 && tileLoads === 0) offline(true);
    });
    baseLayer.on('tileload', ()=>{ if(++tileLoads === 1) offline(false); });
    baseLayer.addTo(map).bringToBack();
    document.querySelectorAll('[data-base]').forEach(btn=>btn.setAttribute('aria-pressed', String(btn.dataset.base===key)));
  }
  // A relief image stored with the page (tools/build_fallback.py) sits under the live imagery,
  // so the map keeps a realistic background if GIBS fails during a demo.
  const FALLBACK_BOUNDS = [[-61.6064, -101.25], [31.9522, 0]];
  function offline(on){ document.getElementById('mapnote').hidden=!on; }
  function buildMap(){
    map.createPane('fallback'); map.getPane('fallback').style.zIndex = 150;
    L.imageOverlay('fallback-relief.jpg', FALLBACK_BOUNDS, {pane:'fallback', interactive:false}).addTo(map);
    D.states.forEach(s=>L.polygon(geomLL(s.g), {color:'#ffffff', opacity:.55, weight:1, fillColor:'#1f272c', fillOpacity:0, interactive:false}).addTo(lStates));
    setBase(baseKey);
    map.fitBounds(BRAZIL, {animate:false});
  }
  // Fire points are drawn on a canvas: live FIRMS data has thousands of them. VIIRS as circles, MODIS as diamonds.
  const fireRenderer = L.canvas({padding:0.3});
  const Diamond = L.CircleMarker.extend({ _updatePath(){
    const rd=this._renderer; if(!rd._drawing || this._empty()) return;
    const p=this._point, ctx=rd._ctx, k=this._radius*1.25;
    ctx.beginPath(); ctx.moveTo(p.x, p.y-k); ctx.lineTo(p.x+k, p.y); ctx.lineTo(p.x, p.y+k); ctx.lineTo(p.x-k, p.y); ctx.closePath();
    rd._fillStroke(ctx, this); } });
  const cssVar = name => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  let fireMarkers = [];
  function drawPoints(){
    lPts.clearLayers();
    const col = {f1:cssVar('--f1'), f2:cssVar('--f2'), f3:cssVar('--f3')};
    const colorOf = f => f>40 ? col.f3 : f>=10 ? col.f2 : col.f1;
    fireMarkers = D.points.map(p=>{
      if(!p.uf) return L.circleMarker([p.lat,p.lon], {renderer:fireRenderer, radius:2.5, color:'#000', weight:.5, fillColor:'#9aa4aa', fillOpacity:.8, interactive:false}).addTo(lPts);
      const Shape = p.sensor==='VIIRS' ? L.CircleMarker : Diamond;
      const m = new Shape([p.lat,p.lon], {renderer:fireRenderer, radius:2.6+Math.min(5.5,Math.sqrt(p.frp)*0.8),
        color:'#10161a', weight:1, fillColor:colorOf(p.frp), fillOpacity: S.sel && p.mun!==S.sel ? 0.35 : 0.95});
      m.bindTooltip(()=>t('map.tip',{sensor:p.sensor, sat:p.sat, frp:fmt1(p.frp), time:hhmm(p.time), conf:p.conf}), {direction:'top', offset:[0,-4]});
      m.on('click', ()=>{ if(byId[p.mun]) select(p.mun); });
      m._p = p;
      return m.addTo(lPts);
    });
  }
  // Selecting a municipality only fades the other points; no need to rebuild thousands of markers.
  function fadePoints(){ fireMarkers.forEach(m=>{ if(m._p) m.setStyle({fillOpacity: S.sel && m._p.mun!==S.sel ? 0.35 : 0.95}); }); }
  function drawSelection(){
    lSel.clearLayers();
    if(!S.sel) return;
    const c=byId[S.sel], it=item(c.id), g=geomLL(c.geom);
    L.polygon(g, {color:'#000', opacity:.6, weight:4.5, fill:false, interactive:false}).addTo(lSel);   // halo for imagery
    L.polygon(g, {color:'#fff', weight:2, fillColor:'#fff', fillOpacity:.06, interactive:false}).addTo(lSel);
    if(it.status==='new' || it.status==='dismissed') return;
    const active = it.status==='sent';
    const col = it.status==='cancelled' ? '#9aa8b0' : it.level==='extreme' ? '#ff5a3c' : '#ffb547';
    const area = it.areaMode==='hull' ? [ll(c.poly)] : g;
    L.polygon(area, {color:col, weight:2.5, dashArray: active?null:'7 5', fillColor:col, fillOpacity: active?0.25:0.12, interactive:false}).addTo(lSel);
  }
  function fitTo(id){
    const opts={paddingTopLeft:[30,50], paddingBottomRight:[30,60], maxZoom:10, animate:!reduceMotion()};  // room for title, tools and legend
    if(id){ const b=byId[id].bbox; map.fitBounds([[b[1],b[0]],[b[3],b[2]]], opts); } else map.fitBounds(BRAZIL, opts);
  }
  function renderMapControls(){
    const zi=zoomCtl.getContainer().querySelector('.leaflet-control-zoom-in'), zo=zoomCtl.getContainer().querySelector('.leaflet-control-zoom-out');
    const sb=document.querySelector('[data-base="sat"]'); sb.textContent=t('base.sat',{d:new Date(SAT_DATE+'T12:00:00Z').toLocaleDateString(I18N.locale(),{day:'numeric',month:'short',timeZone:'UTC'})});
    zi.title=t('map.zoomin'); zi.setAttribute('aria-label', t('map.zoomin')); zo.title=t('map.zoomout-btn'); zo.setAttribute('aria-label', t('map.zoomout-btn'));
  }
  document.querySelectorAll('[data-base]').forEach(btn=>btn.addEventListener('click', ()=>setBase(btn.dataset.base)));

  /* ---------- places on the map: region names, capitals, municipal seats ---------- */
  // Regions are named on the country view; capitals always; other seats appear once zoomed to a state.
  // Labels are placed greedily (capitals first) and skipped where they would overlap.
  const REGION_LABELS = {North:[-3.5,-61], Northeast:[-7.5,-40.5], 'Central-West':[-14.5,-53.5], Southeast:[-20.5,-45], South:[-27.5,-52]};
  const CITY_ZOOM = 6, REGION_MAX_ZOOM = 5.25, MAX_SEATS = 600;
  map.createPane('places'); map.getPane('places').style.zIndex = 450; map.getPane('places').style.pointerEvents = 'none';
  const lPlaces = L.layerGroup().addTo(map);
  const capitals = CITIES.filter(c=>c[5]===1), seats = CITIES.filter(c=>c[5]!==1);
  const placeIcon = (name, cls, w) => L.divIcon({className:'place '+cls, iconSize:[w,16], iconAnchor:[5,8], html:`<span class="dot"></span><span class="nm">${esc(name)}</span>`});
  function drawPlaces(){
    lPlaces.clearLayers();
    const z = map.getZoom(), view = map.getBounds().pad(0.05), taken = [];
    const charW = 6.6 * (parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--fs')) || 1);
    const fits = (pt, w) => { const box=[pt.x-6, pt.y-9, pt.x+w, pt.y+9];
      if(taken.some(b=>box[0]<b[2] && box[2]>b[0] && box[1]<b[3] && box[3]>b[1])) return false; taken.push(box); return true; };
    const place = (lat, lon, name, cls, labelled) => {
      const w = labelled ? Math.round(name.length*charW)+14 : 10;
      const pt = map.latLngToContainerPoint([lat, lon]);
      const show = labelled && fits(pt, w);
      L.marker([lat, lon], {pane:'places', interactive:false, keyboard:false,
        icon: placeIcon(show ? name : '', cls + (show ? '' : ' nolabel'), show ? w : 10)}).addTo(lPlaces);
    };
    if(z <= REGION_MAX_ZOOM) Object.entries(REGION_LABELS).forEach(([k,[lat,lon]])=>{
      L.marker([lat,lon], {pane:'places', interactive:false, keyboard:false, icon:L.divIcon({className:'region', iconSize:[160,24], iconAnchor:[80,12], html:`<span>${t('region.'+k)}</span>`})}).addTo(lPlaces);
      const pt=map.latLngToContainerPoint([lat,lon]); taken.push([pt.x-80, pt.y-12, pt.x+80, pt.y+12]);
    });
    capitals.forEach(c=>{ if(view.contains([c[3],c[4]])) place(c[3], c[4], c[1], 'capital', true); });
    if(z >= CITY_ZOOM){
      const inView = seats.filter(c=>view.contains([c[3],c[4]]));
      inView.slice(0, MAX_SEATS).forEach(c=>place(c[3], c[4], c[1], 'seat', z >= CITY_ZOOM + 1 || inView.length <= 120));
    }
  }
  map.on('zoomend moveend', drawPlaces);

  /* ---------- live detections (INPE, every 10 minutes) and the evidence of where data comes from ---------- */
  // Points are drawn on a canvas (there can be thousands); detections of the last hour get a pulsing ring.
  const RECENT_MIN = 60, LIVE_MAX_AGE_MIN = 30;    // older than 30 min since INPE's last file = "delayed"
  const liveRenderer = L.canvas({padding:0.3});
  const lLive = L.layerGroup().addTo(map), lRecent = L.layerGroup().addTo(map);
  const stateBoxes = D.states.map(s=>{ const polys=s.g; const pts=polys.flat(2);
    return {uf:s.uf, polys, x0:Math.min(...pts.map(p=>p[0])), x1:Math.max(...pts.map(p=>p[0])), y0:Math.min(...pts.map(p=>p[1])), y1:Math.max(...pts.map(p=>p[1]))}; });
  const ufAt = (lat, lon) => { for(const b of stateBoxes){ if(lon>=b.x0 && lon<=b.x1 && lat>=b.y0 && lat<=b.y1 && inPolys(lon, lat, b.polys)) return b.uf; } return null; };
  let LIVE = {status:'loading', points:[], files:[]};
  const minutesAgo = d => Math.max(0, Math.round((Date.now() - d.getTime())/60000));
  const utcHM = d => `${String(d.getUTCHours()).padStart(2,'0')}:${String(d.getUTCMinutes()).padStart(2,'0')}`;
  const localDT = d => d.toLocaleString(I18N.locale(), {day:'numeric', month:'short', hour:'2-digit', minute:'2-digit'});
  function liveState(){
    if(LIVE.status==='loading') return 'loading';
    if(!LIVE.latestFile) return 'error';
    return minutesAgo(LIVE.latestFile.time) <= LIVE_MAX_AGE_MIN && LIVE.status==='live' ? 'live' : 'delayed';
  }
  function drawLive(){
    lLive.clearLayers(); lRecent.clearLayers();
    LIVE.br.forEach(p=>{
      L.circleMarker([p.lat,p.lon], {renderer:liveRenderer, radius:3.2, color:'#ffffff', weight:1, fillColor:'#ff3b1f', fillOpacity:.95, interactive:false}).addTo(lLive);
      if(minutesAgo(p.time) <= RECENT_MIN)
        L.marker([p.lat,p.lon], {interactive:false, keyboard:false, icon:L.divIcon({className:'live-pulse', iconSize:[22,22], html:'<span></span>'})}).addTo(lRecent);
    });
  }
  function renderLiveBadge(){
    const b=document.getElementById('livebadge'), st=liveState();
    b.dataset.state=st;
    const ago = LIVE.latestFile ? minutesAgo(LIVE.latestFile.time) : 0;
    b.querySelector('.lb-text').textContent = st==='loading' ? t('live.loading') : st==='error' ? t('live.error')
      : t(st==='live' ? 'live.on' : 'live.delayed', {m:ago, n:fmtInt(LIVE.br.length)});
  }
  function evidenceHtml(){
    const st=liveState(), m=D.meta;
    const latestBr = (LIVE.br||[]).reduce((x,p)=> !x || p.time > x ? p.time : x, null);   // newest detection inside Brazil
    const bySat = {}; (LIVE.br||[]).forEach(p=>{ bySat[p.sat]=(bySat[p.sat]||0)+1; });
    const sats = Object.entries(bySat).sort((a,b)=>b[1]-a[1]).map(([s,n])=>`<li>${esc(s)} <span class="num">${fmtInt(n)}</span></li>`).join('');
    const files = (LIVE.files||[]).slice().reverse().slice(0,6).map(f=>`<li><a href="${esc(f.url)}" target="_blank" rel="noopener">${esc(f.name)}</a> <span class="num">${t('ev.file-count',{n:fmtInt(f.count)})}</span></li>`).join('');
    const live = LIVE.latestFile ? `
      <dl class="kv">
        <dt>${t('ev.latest-file')}</dt><dd><a href="${esc(LIVE.latestFile.url)}" target="_blank" rel="noopener">${utcHM(LIVE.latestFile.time)} UTC</a> (${t('ev.ago',{m:minutesAgo(LIVE.latestFile.time)})})</dd>
        <dt>${t('ev.latest-det')}</dt><dd>${latestBr ? `${utcHM(latestBr)} UTC (${t('ev.ago',{m:minutesAgo(latestBr)})})` : '–'}</dd>
        <dt>${t('ev.in-brazil',{h:LiveFires.WINDOW_MIN/60})}</dt><dd class="num">${fmtInt(LIVE.br.length)}</dd>
        <dt>${t('ev.fetched')}</dt><dd>${localDT(LIVE.fetchedAt)}</dd>
      </dl>
      ${sats?`<p class="hint">${t('ev.by-sat')}</p><ul class="ev-list">${sats}</ul>`:''}
      ${files?`<details class="more"><summary>${t('ev.files')}</summary><ul class="ev-files">${files}</ul></details>`:''}` : `<p class="note">${t('ev.unavailable')}${LIVE.error?` <code>${esc(LIVE.error)}</code>`:''}</p>`;
    return `<div><span class="eyebrow">${t('ev.eyebrow')}</span><h2 id="sheet-h">${t('ev.h')}</h2></div>
      <section class="ev"><h3><span class="ev-dot" data-state="${st}"></span>${t('ev.live-h')}</h3>
        <p class="hint">${t('ev.live-p')} <a href="${esc(LIVE.source||'https://dataserver-coids.inpe.br/queimadas/queimadas/focos/csv/10min/')}" target="_blank" rel="noopener">dataserver-coids.inpe.br</a></p>${live}</section>
      <section class="ev"><h3><span class="ev-dot" data-state="${firmsState()}"></span>${t('ev.firms-h')}</h3>${firmsHtml()}</section>
      <section class="ev"><h3><span class="ev-dot" data-state="live"></span>${t('ev.img-h')}</h3>
        <p class="hint">${t('ev.img-p',{d:new Date(SAT_DATE+'T12:00:00Z').toLocaleDateString(I18N.locale(),{day:'numeric',month:'long',year:'numeric',timeZone:'UTC'})})} <a href="https://earthdata.nasa.gov/gibs" target="_blank" rel="noopener">NASA GIBS</a></p></section>
      <div class="actions"><button class="btn primary" data-sa="close">${t('howto.ok')}</button></div>`;
  }
  // FIRMS file made by the GitHub task every 3 h: "live" while it is at most FIRMS_MAX_AGE_H old.
  const FIRMS_MAX_AGE_H = 6;
  function firmsState(){ const m=D.meta; if(!m || m.kind!=='live') return 'sample';
    return (Date.now() - new Date(m.generated).getTime())/3600e3 <= FIRMS_MAX_AGE_H ? 'live' : 'delayed'; }
  function firmsHtml(){
    const m=D.meta, st=firmsState();
    if(st==='sample') return `<p class="hint">${t('ev.firms-sample')}</p>`;
    const hours = Math.round((Date.now() - new Date(m.generated).getTime())/3600e3);
    const rows = m.sources.map(s=>`<li><a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.sensor)} ${esc(s.satellite)}</a>
      ${t('ev.firms-src',{n:fmtInt(s.in_brazil), d:localDT(new Date(s.updated))})}</li>`).join('');
    return `<p class="hint">${t(st==='live'?'ev.firms-live':'ev.firms-delayed',{d:localDT(new Date(m.generated)), h:hours, w:m.window_hours})}</p>
      <ul class="ev-files">${rows}</ul>
      ${m.latest_pass?`<p class="hint">${t('ev.firms-pass',{d:localDT(new Date(m.latest_pass))})}</p>`:''}`;
  }
  document.getElementById('livebadge').addEventListener('click', ()=>openSheet(evidenceHtml()));
  LiveFires.start(state=>{
    LIVE = {...state, br: state.points.map(p=>({...p, uf:ufAt(p.lat,p.lon)})).filter(p=>p.uf)};
    drawLive(); renderLiveBadge(); renderMapStats();
  });
  setInterval(()=>{ renderLiveBadge(); if(LIVE.br) drawLive(); }, 60000);   // "N min ago" and the last-hour rings age

  /* ---------- side panel ---------- */
  function renderSide(){
    const side=document.getElementById('side');
    if(!S.sel){ side.innerHTML=`<div class="phead"><h2>${t('side.pick')}</h2></div><div class="empty">${t('side.pick-hint')}</div>`; return; }
    const c=byId[S.sel], it=item(c.id);
    const dets=D.points.filter(p=>p.mun===c.id).sort((a,b)=>b.frp-a.frp);
    let h=`<div class="phead"><div><h2 class="case-h">${esc(c.name)} <span class="uf">${c.uf}</span></h2><p class="case-sub t-${c.tier}"><span class="tier">${t('priority.'+c.tier)}</span> ${t('case.provisional')}</p></div>${it.status==='new'?'':statusChip(it.status)}</div><div class="body">`;
    h+=stepper(it);
    h+=`<div class="facts">
      <div><b class="num">${c.n}</b><span>${t('facts.det')}</span></div>
      <div><b class="num">${fmt1(c.frpMax)}<small> MW</small></b><span>${t('facts.max')}</span></div>
      <div><b class="num">${brtFromUtc(c.last)}</b><span>${t('facts.last')}</span></div></div>`;
    h+=actionBlock(c,it);
    h+=`<details class="more" data-keep="sat" ${S.open.sat?'open':''}><summary>${t('sat.h')}</summary>
      <dl class="kv">
        <dt>${t('sat.vm')}</dt><dd class="num">${c.nV} / ${c.nM}</dd>
        <dt>${t('sat.high')}</dt><dd class="num">${c.high}</dd>
        <dt>${t('sat.sum')}</dt><dd class="num">${fmt1(c.frpSum)} MW</dd>
        <dt>${t('sat.last')}</dt><dd class="num">${hhmm(c.last)} UTC</dd>
        <dt>${t('sat.harm')}</dt><dd class="num pend">${t('sat.pending')}</dd>
        <dt>${t('sat.usual')}</dt><dd class="num pend">${t('sat.pending')}</dd>
      </dl>
      <p class="hint">${t('sat.hint')}</p>
      <div class="tablebox"><table class="det"><thead><tr><th>UTC</th><th>Sensor</th><th>FRP MW</th><th>${t('sat.th.conf')}</th></tr></thead><tbody>${dets.map(p=>`<tr><td class="num">${hhmm(p.time)}</td><td>${p.sensor} ${p.sat}</td><td class="num">${fmt1(p.frp)}</td><td class="num">${esc(p.conf)}</td></tr>`).join('')}</tbody></table></div>
    </details>`;
    side.innerHTML=h+'</div>';
  }
  function checksHtml(cs){
    const bad=cs.filter(x=>x.k==='fail'||x.k==='warn'), ok=cs.filter(x=>x.k==='ok');
    const icon=k=>k==='fail'?'×':'!';
    return `<ul class="checks">${bad.map(x=>`<li class="${x.k}"><span class="i">${icon(x.k)}</span><span>${esc(x.txt)}</span></li>`).join('')}
      <li class="okline"><span class="i">✓</span><span>${t('checks.passed',{ok:ok.length, all:ok.length+bad.length})}</span></li></ul>`;
  }
  function stepper(it){
    const idx = {new:0, dismissed:0, draft:1, pending:2, sent:3, cancelled:3}[it.status];
    const names=[0,1,2,3].map(i=>t('step.'+i));
    return `<ol class="steps" aria-label="${t('steps.aria')}">${names.map((n,i)=>`<li class="${i<idx?'done':i===idx?'now':''}"${i===idx?' aria-current="step"':''}><span class="sn" aria-hidden="true">${i<idx?'✓':i+1}</span>${n}</li>`).join('')}</ol>`;
  }
  function actionBlock(c,it){
    if(it.status==='new' || it.status==='dismissed'){
      if(c.uf!==S.juris) return `<p class="note">${esc(t('act.other',{uf:c.uf, juris:S.juris}))}</p>`;
      return `<div class="actions"><button class="btn primary" data-act="draft">${t('act.write')}</button>${it.status==='new'?`<button class="btn" data-act="dismiss">${t('act.dismiss')}</button>`:''}</div>${it.status==='dismissed'?`<p class="note">${t('act.dismissed')}</p>`:''}`;
    }
    if(it.status==='draft'){
      const cs=checks(c,it), msg=msgOf(c,it), a=areaOf(c,it);
      return `<div class="form">
        <div class="levels" role="radiogroup" aria-label="${t('form.level')}">
          <label class="lvl"><input type="radio" name="level" value="severe" ${it.level==='severe'?'checked':''}><span><strong>${t('lvl.severe')}</strong><small>${t('lvl.severe.hint')}</small></span></label>
          <label class="lvl ext"><input type="radio" name="level" value="extreme" ${it.level==='extreme'?'checked':''}><span><strong>${t('lvl.extreme')}</strong><small>${t('lvl.extreme.hint')}</small></span></label></div>
        <div class="row2">
          <div class="field"><label for="f-event">${t('form.event')}</label><select id="f-event" data-k="event">
            <option value="wildfire" ${it.event==='wildfire'?'selected':''}>${t('ev.wildfire')}</option>
            <option value="smoke" ${it.event==='smoke'?'selected':''}>${t('ev.smoke')}</option>
            <option value="risk" ${it.event==='risk'?'selected':''}>${t('ev.risk')}</option></select></div>
          <div class="field"><label for="f-action">${t('form.action')}</label><select id="f-action" data-k="action">
            <option value="avoid" ${it.action==='avoid'?'selected':''}>${t('ac.avoid')}</option>
            <option value="indoors" ${it.action==='indoors'?'selected':''}>${t('ac.indoors')}</option>
            <option value="evacuate" ${it.action==='evacuate'?'selected':''}>${t('ac.evacuate')}</option></select></div>
        </div>
        <div class="field"><span>${t('form.msg')}</span><div class="msgbox" id="msgprev">${esc(msg)}</div></div>
        <details class="more" data-keep="opts" ${S.open.opts?'open':''}><summary>${t('form.more')} <span class="sum">${it.hours} h, ${t('form.lang.'+it.lang)}, ${fmtInt(a)} km²</span></summary>
          <div class="form">
            <div class="row2">
              <div class="field"><label for="f-hours">${t('form.hours')}</label><select id="f-hours" data-k="hours">
                ${[3,6,12,24].map(v=>`<option value="${v}" ${it.hours==v?'selected':''}>${t('form.hours.n',{n:v})}</option>`).join('')}</select></div>
              <div class="field"><label for="f-lang">${t('form.lang')}</label><select id="f-lang" data-k="lang">
                <option value="pt" ${it.lang==='pt'?'selected':''}>${t('form.lang.pt')}</option><option value="en" ${it.lang==='en'?'selected':''}>${t('form.lang.en')}</option></select></div>
            </div>
            <div class="field"><span>${t('form.area')}</span><div class="radios">
              <label><input type="radio" name="area" value="hull" ${it.areaMode==='hull'?'checked':''}> ${t('area.hull',{a:fmtInt(c.areaKm2)})}</label>
              <label><input type="radio" name="area" value="mun" ${it.areaMode==='mun'?'checked':''}> ${t('area.mun',{a:fmtInt(munArea(c))})}</label></div></div>
            <div class="field"><label for="f-msg">${t('form.edit')}</label><textarea id="f-msg">${esc(msg)}</textarea>
              ${it.edited?`<button class="btn sm" data-act="reset" style="justify-self:start">${t('form.reset')}</button>`:''}</div>
          </div></details>
        ${reachHtml(c,it)}
        <div id="checks">${checksHtml(cs)}</div>
        <div class="actions"><button class="btn primary" data-act="submit" ${hardFail(cs)?'disabled':''}>${t('form.submit')}</button><button class="btn" data-act="discard">${t('form.discard')}</button></div></div>`;
    }
    if(it.status==='pending'){
      return `<p class="note">${t('pending.note')}</p>
        <div class="msgbox">${esc(msgOf(c,it))}</div>
        <div class="actions"><button class="btn danger" data-act="review">${t('pending.approve')}</button><button class="btn" data-act="return">${t('pending.back')}</button></div>`;
    }
    if(it.status==='sent'){
      return `<p class="note">${t('sent.note',{t:it.sentAt, a:fmtInt(areaOf(c,it))})}</p>
        <div class="msgbox">${esc(msgOf(c,it))}</div>
        <div class="actions"><button class="btn" data-act="cancelask">${t('sent.cancel')}</button></div>`;
    }
    if(it.status==='cancelled') return `<p class="note">${t('cancelled.note',{t:it.cancelAt})}</p>`;
    return '';
  }

  /* ---------- review sheet ---------- */
  let sheetReturn=null;
  function openSheet(html){ sheetReturn=document.activeElement; const b=document.getElementById('sheet-body'); b.innerHTML=html; document.getElementById('sheet').hidden=false; const f=b.querySelector('input,button'); if(f) f.focus(); }
  function closeSheet(){ document.getElementById('sheet').hidden=true; if(sheetReturn && sheetReturn.focus) sheetReturn.focus(); }
  function reviewHtml(c,it){
    const cs=checks(c,it), warn=softWarn(cs);
    const lv = `<span class="chip ${it.level}">${t('lvl.'+it.level)}</span>`;
    return `<div><span class="eyebrow">${t('sheet.review')}</span><h2 id="sheet-h">${t('sheet.review.h',{name:esc(c.name), uf:c.uf})}</h2></div>
      <div>${t('sheet.review.sum',{level:lv, a:fmtInt(areaOf(c,it)), h:it.hours, uf:c.uf})}</div>
      ${reachHtml(c,it)}
      <div class="msgbox">${esc(msgOf(c,it))}</div>${checksHtml(cs)}
      <label class="ack"><input type="checkbox" id="ack-who"> ${t('sheet.ack-who')}</label>
      ${warn?`<label class="ack"><input type="checkbox" id="ack-warn"> ${t('sheet.ack-warn')}</label>`:''}
      <div class="actions"><button class="btn danger" data-sa="approve" disabled>${t('sheet.approve')}</button><button class="btn" data-sa="return">${t('sheet.return')}</button><button class="btn" data-sa="close">${t('sheet.close')}</button></div>`;
  }
  function cancelHtml(c){
    return `<div><span class="eyebrow">${t('sheet.cancel')}</span><h2 id="sheet-h">${t('sheet.cancel.h',{name:esc(c.name), uf:c.uf})}</h2></div>
      <p style="margin:0">${t('sheet.cancel.p')}</p>
      <div class="actions"><button class="btn danger" data-sa="cancel">${t('sheet.cancel.send')}</button><button class="btn" data-sa="close">${t('sheet.cancel.keep')}</button></div>`;
  }
  document.getElementById('sheet-body').addEventListener('change', ()=>{
    const b=document.querySelector('[data-sa="approve"]'); if(!b) return;
    const who=document.getElementById('ack-who'), w=document.getElementById('ack-warn');
    b.disabled = !(who && who.checked) || (w && !w.checked);
  });
  document.getElementById('sheet').addEventListener('click', e=>{ if(e.target.id==='sheet') closeSheet(); });
  document.addEventListener('keydown', e=>{ if(e.key==='Escape' && !document.getElementById('sheet').hidden) closeSheet(); });
  document.getElementById('sheet-body').addEventListener('click', e=>{
    const b=e.target.closest('[data-sa]'); if(!b || b.disabled) return; if(b.dataset.sa==='close' || !S.sel){ closeSheet(); return; } const c=byId[S.sel], it=item(c.id);
    if(b.dataset.sa==='approve'){ it.status='sent'; it.sentAt=clock(nowBrt()); addLog(approver, ['log.approved',{level:it.level, name:c.name, a:areaOf(c,it)}]); showPop(it.level, msgOf(c,it), c); setCap(capXml(c,it,'Alert')); if(window.realPhone) window.realPhone.send(it.level, c, msgOf(c,it)); }
    if(b.dataset.sa==='return'){ it.status='draft'; addLog(approver, ['log.returned',{name:c.name}]); }
    if(b.dataset.sa==='cancel'){ it.status='cancelled'; it.cancelAt=clock(nowBrt()); addLog(approver, ['log.cancelled',{name:c.name}]); showPop('cancel', T[it.lang].cancel(c.name,c.uf), c); setCap(capXml(c,it,'Cancel')); if(window.realPhone) window.realPhone.send('cancel', c, T[it.lang].cancel(c.name,c.uf)); }
    closeSheet(); renderQueue(); drawSelection(); renderSide();
  });

  /* ---------- phone ---------- */
  function renderPhoneClock(){ const n=nowBrt(); const t=clock(n); document.getElementById('ph-time').textContent=t; document.getElementById('ph-clock').textContent=t;
    document.getElementById('ph-date').textContent=n.toLocaleDateString(I18N.lang==='pt'?'pt-BR':'en-GB',{weekday:'long',day:'numeric',month:'long',timeZone:'UTC'}); }
  function showPop(kind, text, c){
    const pop=document.getElementById('pop');
    const title = t('pop.'+kind);
    pop.className='pop '+(kind==='extreme'?'':kind==='severe'?'sev':'cancel');
    pop.innerHTML=`<div class="ph"><span class="tri"></span>${title}</div><div class="pb">${esc(text)}</div><div class="pf"><span>${t('pop.sim')}</span><button id="pop-ok">OK</button></div>`;
    pop.hidden=false;
    S.phonecap = [kind==='cancel' ? 'phone.cancel' : 'phone.shown', {name:c.name}]; renderPhoneCap();
    document.getElementById('pop-ok').onclick=()=>{ pop.hidden=true; };
    if(S.sound) beep(kind);
    showTab('phone', true);
  }
  function renderPhoneCap(){ document.getElementById('phonecap').textContent = t(...S.phonecap); }
  let actx=null;
  function beep(kind){ try{ actx ||= new (window.AudioContext||window.webkitAudioContext)(); const t0=actx.currentTime; const n = kind==='extreme'?6:kind==='severe'?2:1;
    for(let i=0;i<n;i++){ const o=actx.createOscillator(), g=actx.createGain(); o.type='square'; o.frequency.value = i%2?853:960; g.gain.setValueAtTime(0.0001,t0+i*0.22); g.gain.exponentialRampToValueAtTime(0.06,t0+i*0.22+0.02); g.gain.exponentialRampToValueAtTime(0.0001,t0+i*0.22+0.2); o.connect(g).connect(actx.destination); o.start(t0+i*0.22); o.stop(t0+i*0.22+0.21);} }catch(e){} }

  /* ---------- CAP ---------- */
  function capXml(c,it,type){
    const now=new Date(); const iso=d=>d.toISOString().replace(/\.\d+Z$/,'-00:00').replace('-00:00','+00:00');
    const ring = it.areaMode==='hull' ? c.poly : c.geom.reduce((a,p)=>p[0].length>a.length?p[0]:a,[]);
    const poly = ring.concat([ring[0]]).map(([x,y])=>`${y},${x}`).join(' ');
    const exp = new Date(now.getTime()+it.hours*3600e3);
    const msg = type==='Cancel' ? T[it.lang].cancel(c.name,c.uf) : msgOf(c,it);
    return `<?xml version="1.0" encoding="UTF-8"?>
  <alert xmlns="urn:oasis:names:tc:emergency:cap:1.2">
    <identifier>hac-${c.id}-${now.getTime()}</identifier>
    <sender>hotspot-alert-console.demo</sender>
    <sent>${iso(now)}</sent>
    <status>Exercise</status>
    <msgType>${type}</msgType>
    <scope>Public</scope>
    <info>
      <language>${it.lang==='pt'?'pt-BR':'en'}</language>
      <category>Fire</category>
      <event>${T[it.lang].title[it.event]}</event>
      <urgency>Immediate</urgency>
      <severity>${it.level==='extreme'?'Extreme':'Severe'}</severity>
      <certainty>Observed</certainty>
      <expires>${iso(exp)}</expires>
      <description>${esc(msg)}</description>
      <area>
        <areaDesc>${esc(c.name)} - ${c.uf}</areaDesc>
        <polygon>${poly}</polygon>
        <geocode><valueName>IBGE</valueName><value>${c.id}</value></geocode>
      </area>
    </info>
  </alert>`;
  }
  function setCap(x){ S.lastCap=x; document.getElementById('capbox').hidden=false; document.getElementById('capxml').textContent=x; document.getElementById('copied').textContent=''; }
  document.getElementById('copycap').onclick=()=>{ const done=()=>document.getElementById('copied').textContent=t('cap.copied');
    const fallback=()=>{ const r=document.createRange(); r.selectNodeContents(document.getElementById('capxml')); const s=getSelection(); s.removeAllRanges(); s.addRange(r); document.getElementById('copied').textContent=t('cap.selected'); };
    try{ navigator.clipboard.writeText(S.lastCap).then(done,fallback); }catch(e){ fallback(); } };

  /* ---------- actions ---------- */
  function select(id){ S.sel=id; if(id) S.expanded.add(byId[id].uf); renderQueue(); drawSelection(); renderSide(); renderMapTitle(); fadePoints(); fitTo(id); }
  function renderMapTitle(){ document.getElementById('maptitle').textContent = S.sel ? `${byId[S.sel].name}, ${byId[S.sel].uf}` : t('map.brazil'); }
  function startDraft(c,it){ if(c.uf!==S.juris) return; it.status='draft'; it.lang='pt'; addLog(analyst(), ['log.started',{name:c.name, uf:c.uf}]); }
  function act(name){
    const c=byId[S.sel], it=item(c.id);
    switch(name){
      case 'draft': startDraft(c,it); break;
      case 'dismiss': it.status='dismissed'; addLog(analyst(), ['log.dismissed',{name:c.name}]); break;
      case 'reset': it.edited=false; it.msg=''; break;
      case 'discard': it.status='new'; it.edited=false; addLog(analyst(), ['log.discarded',{name:c.name}]); break;
      case 'submit': it.status='pending'; addLog(analyst(), ['log.submitted',{level:it.level, name:c.name}]); break;
      case 'return': it.status='draft'; addLog(analyst(), ['log.took-back',{name:c.name}]); break;
      case 'review': openSheet(reviewHtml(c,it)); return;
      case 'cancelask': openSheet(cancelHtml(c)); return;
    }
    renderQueue(); drawSelection(); renderSide();
  }
  document.getElementById('side').addEventListener('click', e=>{ const b=e.target.closest('[data-act]'); if(b && !b.disabled) act(b.dataset.act); });
  document.getElementById('side').addEventListener('change', e=>{
    const c=byId[S.sel]; if(!c) return; const it=item(c.id); const t=e.target;
    if(t.name==='level') it.level=t.value; else if(t.name==='area') it.areaMode=t.value;
    else if(t.dataset.k){ it[t.dataset.k] = t.dataset.k==='hours' ? +t.value : t.value; }
    else return;
    renderSide(); drawSelection();
  });
  document.getElementById('side').addEventListener('input', e=>{
    if(e.target.id!=='f-msg') return; const c=byId[S.sel], it=item(c.id); it.msg=e.target.value; it.edited=true; const pv=document.getElementById('msgprev'); if(pv) pv.textContent=it.msg;
    const cs=checks(c,it); document.getElementById('checks').innerHTML=checksHtml(cs);
    const sb=document.querySelector('[data-act="submit"]'); if(sb) sb.disabled=hardFail(cs);
  });
  function rowAction(c,it){
    const inJ=c.uf===S.juris;
    switch(it.status){
      case 'new': return inJ ? ['analyze',t('qa.analyze'),''] : null;
      case 'dismissed': return null;
      case 'draft': return ['view',t('qa.view'),''];
      case 'pending': return ['review',t('qa.review'),'go'];
      case 'sent': return ['cancelask',t('qa.cancelask'),'quiet'];
      default: return null;
    }
  }
  document.getElementById('queue').addEventListener('click', e=>{
    const sb=e.target.closest('.sbtn');
    if(sb){ const uf=sb.dataset.uf; if(S.expanded.has(uf)) S.expanded.delete(uf); else S.expanded.add(uf); renderQueue();
      map.fitBounds(stateBounds(uf), {paddingTopLeft:[30,50], paddingBottomRight:[30,60], animate:!reduceMotion()});
      const again=document.querySelector(`.sbtn[data-uf="${uf}"]`); if(again) again.focus(); return; }
    const li=e.target.closest('.qitem'); if(!li) return;
    const qa=e.target.closest('[data-qa]');
    select(li.dataset.id);
    if(!qa) return;
    const c=byId[li.dataset.id], it=item(c.id);
    if(qa.dataset.qa==='analyze'){ startDraft(c,it); renderQueue(); drawSelection(); renderSide(); const f=document.getElementById('f-event'); if(f) f.focus(); }
    else if(qa.dataset.qa==='review' || qa.dataset.qa==='cancelask') act(qa.dataset.qa);
  });
  // Arrow keys move between states and municipalities; Enter/Space opens a state or selects a municipality.
  document.getElementById('queue').addEventListener('keydown', e=>{
    const cur=e.target.closest('.sbtn, .qitem'); if(!cur || e.target.closest('[data-qa]')) return;
    if(cur.classList.contains('qitem') && (e.key==='Enter'||e.key===' ')){ e.preventDefault(); select(cur.dataset.id); }
    if(e.key==='ArrowDown'||e.key==='ArrowUp'){ e.preventDefault();
      const all=[...document.querySelectorAll('#queue .sbtn, #queue .qitem')], i=all.indexOf(cur);
      const next=all[i+(e.key==='ArrowDown'?1:-1)]; if(next) next.focus(); } });
  document.querySelectorAll('.filters button').forEach(b=>b.onclick=()=>{ S.filter=b.dataset.f; document.querySelectorAll('.filters button').forEach(x=>x.setAttribute('aria-pressed', x===b)); renderQueue(); });
  const jsel=document.getElementById('juris');
  [...STATES].sort((a,b)=>a.name.localeCompare(b.name,'pt-BR')).forEach(st=>{ const o=document.createElement('option'); o.value=st.uf; o.dataset.name=st.name; if(st.uf===S.juris) o.selected=true; jsel.appendChild(o); });
  const renderJuris = () => [...jsel.options].forEach(o=>{ o.textContent=t('juris.opt',{uf:o.value, name:o.dataset.name}); });
  jsel.onchange=()=>{ S.juris=jsel.value; S.expanded.add(S.juris); renderQueue(); renderSide();
    map.fitBounds(stateBounds(S.juris), {paddingTopLeft:[30,50], paddingBottomRight:[30,60], animate:!reduceMotion()}); };
  document.getElementById('zoom-out').onclick=()=>select(null);
  const renderSound = () => { document.getElementById('sound').textContent=t(S.sound?'sound.on':'sound.off'); };
  document.getElementById('sound').onclick=()=>{ S.sound=!S.sound; renderSound(); };
  window.addEventListener('resize', ()=>map.invalidateSize());

  /* ---------- tabs, how-to, remembered sections ---------- */
  const TABS=['phone','real','log'];
  function showTab(name, reveal){
    TABS.forEach(t=>{ const b=document.getElementById('tab-'+t), p=document.getElementById('pane-'+t); const on=t===name; b.setAttribute('aria-selected', on); b.tabIndex=on?0:-1; p.hidden=!on; });
    if(reveal){ const r=document.getElementById('lower').getBoundingClientRect(); if(r.top>innerHeight-120 || r.bottom<0) document.getElementById('lower').scrollIntoView({behavior: matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth', block:'start'}); }
  }
  TABS.forEach((t,i)=>{ const b=document.getElementById('tab-'+t); b.addEventListener('click',()=>showTab(t));
    b.addEventListener('keydown',e=>{ if(e.key!=='ArrowRight'&&e.key!=='ArrowLeft') return; const n=TABS[(i+(e.key==='ArrowRight'?1:TABS.length-1))%TABS.length]; showTab(n); document.getElementById('tab-'+n).focus(); }); });
  document.getElementById('side').addEventListener('toggle', e=>{ const k=e.target.dataset && e.target.dataset.keep; if(k) S.open[k]=e.target.open; }, true);
  document.getElementById('howto').addEventListener('click',()=>openSheet(`<div><span class="eyebrow">${t('howto')}</span><h2 id="sheet-h">${t('howto.h')}</h2></div>
    <ol class="howto">${[1,2,3,4].map(i=>`<li>${t('howto.'+i)}</li>`).join('')}</ol>
    <div class="actions"><button class="btn primary" data-sa="close">${t('howto.ok')}</button></div>`));

  /* ---------- boot ---------- */
  const inBr=D.points.filter(p=>p.uf).length;
  const renderMapStats = () => { const out=D.points.length-inBr;
    document.getElementById('mapstats').textContent = t(D.meta && D.meta.kind==='live' ? 'map.stats.live' : 'map.stats',{n:fmtInt(inBr), m:fmtInt(D.cands.length), o:fmtInt(out), h:D.meta?D.meta.window_hours:24})
    + (LIVE.br && LIVE.br.length ? ' ' + t('map.live',{n:fmtInt(LIVE.br.length), h:LiveFires.WINDOW_MIN/60}) : ''); };
  // Everything drawn by this file is redrawn when the interface language changes; an open dialog is closed.
  function renderTexts(){ renderLiveBadge(); renderJuris(); renderSound(); renderPhoneCap(); renderMapStats(); renderMapTitle(); renderQueue(); renderSide(); renderLog(); renderPhoneClock(); renderMapControls(); drawPoints(); drawPlaces(); }
  I18N.onChange(()=>{ if(!document.getElementById('sheet').hidden) closeSheet(); renderTexts(); });
  buildMap(); renderTexts(); setInterval(renderPhoneClock, 15000);
  select((D.cands.find(c=>c.uf===S.juris)||D.cands[0]).id);
}

const getJson = url => fetch(url).then(r => { if (!r.ok) throw new Error(url + ': HTTP ' + r.status); return r.json(); });
// cities.json is optional: without it the map simply has no place names.
// data.json is the live FIRMS file (refreshed every 3 h); data-sample.json (12 Nov) is the fallback.
Promise.all([getJson('data.json').catch(err => { console.warn(err); return getJson('data-sample.json'); }), getJson('cities.json').catch(err => { console.warn(err); return null; })])
  .then(([data, cities]) => main(data, cities))
  .catch(err => {
    const box = document.getElementById('side');
    box.innerHTML = '<div class="phead"><h2>' + I18N.t('load.h') + '</h2></div>' +
      '<div class="empty">' + I18N.t('load.p') + '<br><br><code>' + String(err).replace(/[<>&]/g, '') + '</code></div>';
  });
