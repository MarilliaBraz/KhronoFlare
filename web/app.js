// Hotspot Alert Console: front-end logic.
// Loads data.json (fire detections + candidate municipalities) and runs the alert workflow.
"use strict";

function main(D) {
  const S = {role:'analyst', juris:'PA', filter:'all', sel:null, sound:true, items:{}, log:[], lastCap:null, phone:null, open:{}};
  const BRT = -3;
  const esc = s => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const fmt1 = n => n.toLocaleString('en-US',{maximumFractionDigits:1, minimumFractionDigits:1});
  const fmtInt = n => Math.round(n).toLocaleString('en-US');
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
  const TIER = {high:'High', elev:'Elevated', watch:'Watch'};
  const STATUS = {new:['Open',''], draft:['Draft','draft'], pending:['Awaiting approval','pending'], sent:['Alert active','sent'], cancelled:['Cancelled',''], dismissed:['Monitoring','']};
  function item(id){ return S.items[id] ||= {status:'new', level:'severe', lang:'en', event:'wildfire', action:'avoid', hours:6, areaMode:'hull', msg:'', edited:false, ack:false}; }
  function bboxOf(pts){ let x0=1e9,y0=1e9,x1=-1e9,y1=-1e9; for(const [x,y] of pts){ if(x<x0)x0=x; if(x>x1)x1=x; if(y<y0)y0=y; if(y>y1)y1=y; } return [x0,y0,x1,y1]; }

  /* ---------- area ---------- */
  function ringArea(r, lat0){ let a=0; for(let i=0;i<r.length;i++){ const [x1,y1]=r[i], [x2,y2]=r[(i+1)%r.length]; a+=x1*y2-x2*y1; } return Math.abs(a)/2*111.32*111.32*Math.cos(lat0*Math.PI/180); }
  function munArea(c){ const lat0=(c.bbox[1]+c.bbox[3])/2; return c.geom.reduce((s,poly)=> s + ringArea(poly[0],lat0) - poly.slice(1).reduce((t,h)=>t+ringArea(h,lat0),0), 0); }
  function areaOf(c,it){ return it.areaMode==='hull' ? c.areaKm2 : munArea(c); }

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
    out.push({k:inJ?'ok':'fail', hard:true, txt: inJ?`Area is inside your jurisdiction (${S.juris})`:`Outside your jurisdiction: you cover ${S.juris}, this area is in ${c.uf}`});
    const complete = msg.includes(c.name) && /valid until|válido até/i.test(msg);
    out.push({k:complete?'ok':'fail', hard:true, txt: complete?'Message names the place, the action and the end time':'Message must name the municipality and the end time'});
    const a=areaOf(c,it);
    out.push({k:a<=2000?'ok':'warn', txt: a<=2000?`Alert area ${fmtInt(a)} km²`:`Large alert area: ${fmtInt(a)} km² (over 2,000 km²)`});
    const h=localHour(), night=(h>=22||h<6);
    out.push({k:(night&&it.level==='extreme')?'warn':'ok', txt:(night&&it.level==='extreme')?`Extreme alert at ${String(h).padStart(2,'0')}h: it sounds even on silent phones`:'Level and time of day are compatible'});
    out.push({k:msg.length<=360?'ok':'warn', txt: msg.length<=360?`${msg.length} characters`:`Long message: ${msg.length} characters (keep it under 360)`});
    out.push({k:'info', txt:'A second person must approve before anything is sent'});
    return out;
  }
  const hardFail = cs => cs.some(x=>x.hard && x.k==='fail');
  const softWarn = cs => cs.some(x=>x.k==='warn');

  /* ---------- log ---------- */
  function addLog(role, text){ S.log.unshift({t:clockS(nowBrt()), role, text}); renderLog(); }
  function renderLog(){
    const el=document.getElementById('log');
    document.getElementById('logn').textContent=S.log.length;
    el.innerHTML = S.log.length ? S.log.map(l=>`<li><span class="t">${l.t}</span><span class="r">${esc(l.role)}</span><span>${esc(l.text)}</span></li>`).join('') : '<li class="empty">Nothing yet. Every draft, approval and cancellation is recorded here.</li>';
  }


  /* ---------- queue ---------- */
  function isOpen(s){ return s==='new'||s==='draft'||s==='pending'; }
  function isAlert(s){ return s==='pending'||s==='sent'||s==='cancelled'; }
  function visible(){ return D.cands.filter(c=>{ const s=item(c.id).status; if(S.filter==='open') return isOpen(s) && (s!=='new' || c.uf===S.juris); if(S.filter==='active') return isAlert(s); return true; }); }
  function renderQueue(){
    const n={all:D.cands.length, open:0, active:0};
    D.cands.forEach(c=>{ const s=item(c.id).status; if(isOpen(s) && (s!=='new' || c.uf===S.juris)) n.open++; if(isAlert(s)) n.active++; });
    document.querySelectorAll('.filters button').forEach(b=>{ const e=b.querySelector('.n'); if(e) e.textContent=n[b.dataset.f]; });
    const list=visible(), mine=list.filter(c=>c.uf===S.juris), others=list.filter(c=>c.uf!==S.juris);
    const row = c=>{
      const it=item(c.id), st=STATUS[it.status], ra=rowAction(c,it);
      const btn = ra ? `<button class="qact ${ra[2]}" data-qa="${ra[0]}" aria-label="${ra[1]} ${esc(c.name)}">${ra[1]}</button>` : '';
      const chip = it.status==='new' ? '' : ` <span class="chip ${st[1]}">${st[0]}</span>`;
      return `<li class="qitem t-${c.tier}" role="option" tabindex="0" data-id="${c.id}" aria-selected="${S.sel===c.id}">
        <span class="stripe"></span><span class="qname">${esc(c.name)} <span class="uf">${c.uf}</span></span>${btn}
        <span class="qmeta"><span class="tier">${TIER[c.tier]}</span><span class="num">${c.n} fire${c.n>1?'s':''}</span><span class="num">${fmt1(c.frpMax)} MW max</span>${chip}</span></li>`;
    };
    const group = (title, cs) => cs.length ? `<li class="qgroup" role="presentation">${title}</li>${cs.map(row).join('')}` : '';
    document.getElementById('queue').innerHTML =
      (group(`Your area, ${S.juris}`, mine) + group('Other states, view only', others))
      || `<li class="empty">${S.filter==='open'?'Nothing to do in your area.':'No alerts yet.'}</li>`;
  }

  /* ---------- map ---------- */
  const SVGNS='http://www.w3.org/2000/svg';
  const KX = Math.cos(8*Math.PI/180);
  const px = lon => lon*KX*100, py = lat => -lat*100;
  const svg=document.getElementById('map');
  let VB=null, anim=null;
  function pathD(geom){ return geom.map(poly=>poly.map(r=>'M'+r.map(([x,y])=>px(x).toFixed(1)+' '+py(y).toFixed(1)).join('L')+'Z').join('')).join(''); }
  function ringD(r){ return 'M'+r.map(([x,y])=>px(x).toFixed(1)+' '+py(y).toFixed(1)).join('L')+'Z'; }
  const fireColor = f => f>40?'var(--f3)':f>=10?'var(--f2)':'var(--f1)';
  function el(tag, attrs){ const e=document.createElementNS(SVGNS,tag); for(const k in attrs) e.setAttribute(k,attrs[k]); return e; }
  let gStates, gMun, gArea, gPts;
  function buildMap(){
    svg.innerHTML='';
    gStates=el('g',{}); gMun=el('g',{}); gArea=el('g',{}); gPts=el('g',{});
    D.states.forEach(s=>{ const p=el('path',{d:pathD(s.g), fill:'var(--land)', stroke:'var(--land-line)', 'stroke-width':'1', 'vector-effect':'non-scaling-stroke'}); gStates.appendChild(p); });
    svg.append(gStates,gMun,gArea,gPts);
    setVB(brazilVB(), false);
  }
  function brazilVB(){ return [px(-75), py(6), px(-33)-px(-75), py(-34.5)-py(6)]; }
  function fitVB(b){ const pad=0.25*Math.max(b[2]-b[0], b[3]-b[1])+0.05; const x0=px(b[0]-pad), x1=px(b[2]+pad), y0=py(b[3]+pad), y1=py(b[1]-pad);
    const cw=svg.clientWidth, ch=svg.clientHeight, r=(cw>0&&ch>0)?cw/ch:1.2; let w=x1-x0, h=y1-y0; if(w/h<r){ const nw=h*r; return [x0-(nw-w)/2,y0,nw,h]; } const nh=w/r; return [x0,y0-(nh-h)/2,w,nh]; }
  function setVB(target, animate){
    const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
    if(!VB || !animate || reduce){ VB=target; svg.setAttribute('viewBox', VB.join(' ')); svg.setAttribute('preserveAspectRatio','xMidYMid meet'); drawPoints(); return; }
    const from=VB.slice(), t0=performance.now(); cancelAnimationFrame(anim);
    const step=now=>{ const k=Math.min(1,(now-t0)/450), e=1-Math.pow(1-k,3); VB=from.map((v,i)=>v+(target[i]-v)*e); svg.setAttribute('viewBox',VB.join(' ')); drawPoints(); if(k<1) anim=requestAnimationFrame(step); };
    anim=requestAnimationFrame(step);
  }
  function unit(){ const w=svg.clientWidth||600, h=svg.clientHeight||500; return Math.max(VB[2]/w, VB[3]/h); }
  function drawPoints(){
    const u=unit(); gPts.innerHTML='';
    const frag=document.createDocumentFragment();
    D.points.forEach(p=>{
      const x=px(p.lon), y=py(p.lat);
      if(!p.uf){ frag.appendChild(el('circle',{cx:x,cy:y,r:2.2*u,fill:'var(--outside)'})); return; }
      const r=(2.6+Math.min(5.5,Math.sqrt(p.frp)*0.8))*u, col=fireColor(p.frp);
      const sel = S.sel && p.mun===S.sel;
      const shape = p.sensor==='VIIRS' ? el('circle',{cx:x,cy:y,r}) : el('path',{d:`M${x} ${y-r*1.25}L${x+r*1.25} ${y}L${x} ${y+r*1.25}L${x-r*1.25} ${y}Z`});
      shape.setAttribute('fill',col); shape.setAttribute('fill-opacity', S.sel && !sel ? '0.35':'0.9');
      shape.setAttribute('stroke','var(--panel)'); shape.setAttribute('stroke-width', String(0.8*u));
      shape.style.cursor='pointer'; shape.dataset.id=p.mun;
      const tt=el('title',{}); tt.textContent=`${p.sensor} ${p.sat}: ${p.frp} MW at ${hhmm(p.time)} UTC, confidence ${p.conf}`; shape.appendChild(tt);
      frag.appendChild(shape);
    });
    gPts.appendChild(frag);
  }
  function drawSelection(){
    gMun.innerHTML=''; gArea.innerHTML='';
    if(!S.sel) return;
    const c=byId[S.sel], it=item(c.id);
    gMun.appendChild(el('path',{d:pathD(c.geom), fill:'var(--mun)', stroke:'var(--ink)', 'stroke-width':'1.5', 'vector-effect':'non-scaling-stroke'}));
    if(it.status==='new' || it.status==='dismissed') return;
    const active = it.status==='sent';
    const d = it.areaMode==='hull' ? ringD(c.poly) : pathD(c.geom);
    const col = it.status==='cancelled' ? 'var(--watch)' : it.level==='extreme' ? 'var(--extreme)' : 'var(--severe)';
    gArea.appendChild(el('path',{d, fill:col, 'fill-opacity': active?'0.22':'0.10', stroke:col, 'stroke-width':'2', 'stroke-dasharray': active?'':'6 4', 'vector-effect':'non-scaling-stroke'}));
  }
  svg.addEventListener('click', e=>{ const id=e.target.dataset && e.target.dataset.id; if(id && id!=='null' && byId[id]) select(id); });

  /* ---------- side panel ---------- */
  function renderSide(){
    const side=document.getElementById('side');
    if(!S.sel){ side.innerHTML=`<div class="phead"><h2>Pick an area</h2></div><div class="empty">Choose a municipality in the list or click a fire on the map.</div>`; return; }
    const c=byId[S.sel], it=item(c.id), st=STATUS[it.status];
    const dets=D.points.filter(p=>p.mun===c.id).sort((a,b)=>b.frp-a.frp);
    let h=`<div class="phead"><div><h2 class="case-h">${esc(c.name)} <span class="uf">${c.uf}</span></h2><p class="case-sub t-${c.tier}"><span class="tier">${TIER[c.tier]} priority</span> (provisional score)</p></div>${it.status==='new'?'':`<span class="chip ${st[1]}">${st[0]}</span>`}</div><div class="body">`;
    h+=stepper(it);
    h+=`<div class="facts">
      <div><b class="num">${c.n}</b><span>fire detections</span></div>
      <div><b class="num">${fmt1(c.frpMax)}<small> MW</small></b><span>strongest fire</span></div>
      <div><b class="num">${brtFromUtc(c.last)}</b><span>last satellite pass</span></div></div>`;
    h+=actionBlock(c,it);
    h+=`<details class="more" data-keep="sat" ${S.open.sat?'open':''}><summary>Satellite details</summary>
      <dl class="kv">
        <dt>VIIRS / MODIS detections</dt><dd class="num">${c.nV} / ${c.nM}</dd>
        <dt>High-confidence detections</dt><dd class="num">${c.high}</dd>
        <dt>Total fire power</dt><dd class="num">${fmt1(c.frpSum)} MW</dd>
        <dt>Last pass</dt><dd class="num">${hhmm(c.last)} UTC</dd>
        <dt>Harmonized intensity (S-NPP units)</dt><dd class="num pend">pending</dd>
        <dt>Usual for this place in November</dt><dd class="num pend">pending</dd>
      </dl>
      <p class="hint">The two pending lines come from the harmonized MODIS + VIIRS series and will show how unusual this fire is.</p>
      <div class="tablebox"><table class="det"><thead><tr><th>UTC</th><th>Sensor</th><th>FRP MW</th><th>Conf.</th></tr></thead><tbody>${dets.map(p=>`<tr><td class="num">${hhmm(p.time)}</td><td>${p.sensor} ${p.sat}</td><td class="num">${fmt1(p.frp)}</td><td class="num">${esc(p.conf)}</td></tr>`).join('')}</tbody></table></div>
    </details>`;
    side.innerHTML=h+'</div>';
  }
  function checksHtml(cs){
    const bad=cs.filter(x=>x.k==='fail'||x.k==='warn'), ok=cs.filter(x=>x.k==='ok');
    const icon=k=>k==='fail'?'×':'!';
    return `<ul class="checks">${bad.map(x=>`<li class="${x.k}"><span class="i">${icon(x.k)}</span><span>${esc(x.txt)}</span></li>`).join('')}
      <li class="okline"><span class="i">✓</span><span>${ok.length} of ${ok.length+bad.length} checks passed</span></li></ul>`;
  }
  function stepper(it){
    const idx = {new:0, dismissed:0, draft:1, pending:2, sent:3, cancelled:3}[it.status];
    const names=['Analyze','Write','Approve','Sent'];
    return `<ol class="steps" aria-label="Progress">${names.map((n,i)=>`<li class="${i<idx?'done':i===idx?'now':''}"${i===idx?' aria-current="step"':''}><span class="sn" aria-hidden="true">${i<idx?'✓':i+1}</span>${n}</li>`).join('')}</ol>`;
  }
  function actionBlock(c,it){
    if(it.status==='new' || it.status==='dismissed'){
      if(c.uf!==S.juris) return `<p class="note">This area is in ${c.uf}. You write alerts for ${S.juris}. Change "Your area" at the top to act here.</p>`;
      return `<div class="actions"><button class="btn primary" data-act="draft">Write alert</button>${it.status==='new'?'<button class="btn" data-act="dismiss">No alert needed</button>':''}</div>${it.status==='dismissed'?'<p class="note">Marked as no alert needed. You can still write one.</p>':''}`;
    }
    if(it.status==='draft'){
      const cs=checks(c,it), msg=msgOf(c,it), a=areaOf(c,it);
      return `<div class="form">
        <div class="levels" role="radiogroup" aria-label="Level">
          <label class="lvl"><input type="radio" name="level" value="severe" ${it.level==='severe'?'checked':''}><span><strong>Severe</strong><small>Beep</small></span></label>
          <label class="lvl ext"><input type="radio" name="level" value="extreme" ${it.level==='extreme'?'checked':''}><span><strong>Extreme</strong><small>Siren, even on silent</small></span></label></div>
        <div class="row2">
          <div class="field"><label for="f-event">What is happening</label><select id="f-event" data-k="event">
            <option value="wildfire" ${it.event==='wildfire'?'selected':''}>Active wildfire</option>
            <option value="smoke" ${it.event==='smoke'?'selected':''}>Heavy smoke</option>
            <option value="risk" ${it.event==='risk'?'selected':''}>High fire risk</option></select></div>
          <div class="field"><label for="f-action">What people should do</label><select id="f-action" data-k="action">
            <option value="avoid" ${it.action==='avoid'?'selected':''}>Stay away, no burning</option>
            <option value="indoors" ${it.action==='indoors'?'selected':''}>Stay indoors</option>
            <option value="evacuate" ${it.action==='evacuate'?'selected':''}>Prepare to leave</option></select></div>
        </div>
        <div class="field"><span>Message people will see</span><div class="msgbox" id="msgprev">${esc(msg)}</div></div>
        <details class="more" data-keep="opts" ${S.open.opts?'open':''}><summary>More options <span class="sum">${it.hours} h, ${it.lang==='pt'?'Portuguese':'English'}, ${fmtInt(a)} km²</span></summary>
          <div class="form">
            <div class="row2">
              <div class="field"><label for="f-hours">Valid for</label><select id="f-hours" data-k="hours">
                ${[3,6,12,24].map(v=>`<option value="${v}" ${it.hours==v?'selected':''}>${v} hours</option>`).join('')}</select></div>
              <div class="field"><label for="f-lang">Language</label><select id="f-lang" data-k="lang">
                <option value="pt" ${it.lang==='pt'?'selected':''}>Portuguese</option><option value="en" ${it.lang==='en'?'selected':''}>English</option></select></div>
            </div>
            <div class="field"><span>Alert area</span><div class="radios">
              <label><input type="radio" name="area" value="hull" ${it.areaMode==='hull'?'checked':''}> Around the fires (${fmtInt(c.areaKm2)} km²)</label>
              <label><input type="radio" name="area" value="mun" ${it.areaMode==='mun'?'checked':''}> Whole municipality (${fmtInt(munArea(c))} km²)</label></div></div>
            <div class="field"><label for="f-msg">Edit the text by hand</label><textarea id="f-msg">${esc(msg)}</textarea>
              ${it.edited?'<button class="btn sm" data-act="reset" style="justify-self:start">Back to template</button>':''}</div>
          </div></details>
        <div id="checks">${checksHtml(cs)}</div>
        <div class="actions"><button class="btn primary" data-act="submit" ${hardFail(cs)?'disabled':''}>Send for approval</button><button class="btn" data-act="discard">Discard</button></div></div>`;
    }
    if(it.status==='pending'){
      return `<p class="note">Waiting for a second person to approve.</p>
        <div class="msgbox">${esc(msgOf(c,it))}</div>
        <div class="actions"><button class="btn danger" data-act="review">Approve</button><button class="btn" data-act="return">Back to draft</button></div>`;
    }
    if(it.status==='sent'){
      return `<p class="note">Active since ${it.sentAt} BRT over ${fmtInt(areaOf(c,it))} km².</p>
        <div class="msgbox">${esc(msgOf(c,it))}</div>
        <div class="actions"><button class="btn" data-act="cancelask">Cancel alert</button></div>`;
    }
    if(it.status==='cancelled') return `<p class="note">Cancelled at ${it.cancelAt} BRT. Phones in the area got a cancellation message.</p>`;
    return '';
  }

  /* ---------- review sheet ---------- */
  let sheetReturn=null;
  function openSheet(html){ sheetReturn=document.activeElement; const b=document.getElementById('sheet-body'); b.innerHTML=html; document.getElementById('sheet').hidden=false; const f=b.querySelector('input,button'); if(f) f.focus(); }
  function closeSheet(){ document.getElementById('sheet').hidden=true; if(sheetReturn && sheetReturn.focus) sheetReturn.focus(); }
  function reviewHtml(c,it){
    const cs=checks(c,it), warn=softWarn(cs);
    const lv = it.level==='extreme'?'<span class="chip extreme">Extreme</span>':'<span class="chip severe">Severe</span>';
    return `<div><span class="eyebrow">Second-person review</span><h2 id="sheet-h">Approve the alert for ${esc(c.name)} (${c.uf})?</h2></div>
      <div>${lv} alert over ${fmtInt(areaOf(c,it))} km², valid for ${it.hours} h. Written by Analyst ${c.uf}.</div>
      <div class="msgbox">${esc(msgOf(c,it))}</div>${checksHtml(cs)}
      <label style="display:flex;gap:8px;font-size:13px"><input type="checkbox" id="ack-who"> I am the approver on duty, not the person who wrote this alert</label>
      ${warn?`<label style="display:flex;gap:8px;font-size:13px"><input type="checkbox" id="ack-warn"> I reviewed the warnings and the alert is still needed</label>`:''}
      <div class="actions"><button class="btn danger" data-sa="approve" disabled>Approve and send</button><button class="btn" data-sa="return">Return to analyst</button><button class="btn" data-sa="close">Close</button></div>`;
  }
  function cancelHtml(c){
    return `<div><span class="eyebrow">Cancel alert</span><h2 id="sheet-h">Cancel the alert for ${esc(c.name)} (${c.uf})?</h2></div>
      <p style="margin:0">Phones in the area get a message saying the alert no longer applies.</p>
      <div class="actions"><button class="btn danger" data-sa="cancel">Send cancellation</button><button class="btn" data-sa="close">Keep alert active</button></div>`;
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
    if(b.dataset.sa==='approve'){ it.status='sent'; it.sentAt=clock(nowBrt()); addLog('Approver', `Approved and sent ${it.level} alert to ${c.name} (${fmtInt(areaOf(c,it))} km²)`); showPop(it.level, msgOf(c,it), c); setCap(capXml(c,it,'Alert')); if(window.realPhone) window.realPhone.send(it.level, c, msgOf(c,it)); }
    if(b.dataset.sa==='return'){ it.status='draft'; addLog('Approver', `Returned ${c.name} alert to the analyst`); }
    if(b.dataset.sa==='cancel'){ it.status='cancelled'; it.cancelAt=clock(nowBrt()); addLog('Approver', `Cancelled alert for ${c.name}`); showPop('cancel', T[it.lang].cancel(c.name,c.uf), c); setCap(capXml(c,it,'Cancel')); if(window.realPhone) window.realPhone.send('cancel', c, T[it.lang].cancel(c.name,c.uf)); }
    closeSheet(); renderQueue(); drawSelection(); renderSide();
  });

  /* ---------- phone ---------- */
  function renderPhoneClock(){ const n=nowBrt(); const t=clock(n); document.getElementById('ph-time').textContent=t; document.getElementById('ph-clock').textContent=t;
    document.getElementById('ph-date').textContent=n.toLocaleDateString('en-GB',{weekday:'long',day:'numeric',month:'long',timeZone:'UTC'}); }
  function showPop(kind, text, c){
    const pop=document.getElementById('pop');
    const title = kind==='extreme'?'Extreme alert':kind==='severe'?'Severe alert':'Alert cancelled';
    pop.className='pop '+(kind==='extreme'?'':kind==='severe'?'sev':'cancel');
    pop.innerHTML=`<div class="ph"><span class="tri"></span>${title}</div><div class="pb">${esc(text)}</div><div class="pf"><span>Simulation, not an official alert</span><button id="pop-ok">OK</button></div>`;
    pop.hidden=false;
    document.getElementById('phonecap').textContent = kind==='cancel' ? `Cancellation shown to phones in ${c.name}.` : `Simulation of what phones in the ${c.name} alert area would show.`;
    document.getElementById('pop-ok').onclick=()=>{ pop.hidden=true; };
    if(S.sound) beep(kind);
    showTab('phone', true);
  }
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
  document.getElementById('copycap').onclick=()=>{ const done=()=>document.getElementById('copied').textContent='Copied';
    const fallback=()=>{ const r=document.createRange(); r.selectNodeContents(document.getElementById('capxml')); const s=getSelection(); s.removeAllRanges(); s.addRange(r); document.getElementById('copied').textContent='Selected. Press Ctrl+C to copy.'; };
    try{ navigator.clipboard.writeText(S.lastCap).then(done,fallback); }catch(e){ fallback(); } };

  /* ---------- actions ---------- */
  function select(id){ S.sel=id; renderQueue(); drawSelection(); renderSide(); document.getElementById('maptitle').textContent = id ? `${byId[id].name}, ${byId[id].uf}` : 'Brazil'; setVB(id ? fitVB(byId[id].bbox) : brazilVB(), true); }
  function startDraft(c,it){ if(c.uf!==S.juris) return; it.status='draft'; it.lang='pt'; addLog(`Analyst ${S.juris}`, `Started alert for ${c.name} (${c.uf})`); }
  function act(name){
    const c=byId[S.sel], it=item(c.id);
    switch(name){
      case 'draft': startDraft(c,it); break;
      case 'dismiss': it.status='dismissed'; addLog(`Analyst ${S.juris}`, `Kept ${c.name} under monitoring, no alert`); break;
      case 'reset': it.edited=false; it.msg=''; break;
      case 'discard': it.status='new'; it.edited=false; addLog(`Analyst ${S.juris}`, `Discarded draft for ${c.name}`); break;
      case 'submit': it.status='pending'; addLog(`Analyst ${S.juris}`, `Sent ${it.level} alert for ${c.name} for approval`); break;
      case 'return': it.status='draft'; addLog(`Analyst ${S.juris}`, `Took ${c.name} alert back to draft`); break;
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
      case 'new': return inJ ? ['analyze','Analyze',''] : null;
      case 'dismissed': return null;
      case 'draft': return ['view','Continue',''];
      case 'pending': return ['review','Approve','go'];
      case 'sent': return ['cancelask','Cancel','quiet'];
      default: return null;
    }
  }
  document.getElementById('queue').addEventListener('click', e=>{
    const li=e.target.closest('.qitem'); if(!li) return;
    const qa=e.target.closest('[data-qa]');
    select(li.dataset.id);
    if(!qa) return;
    const c=byId[li.dataset.id], it=item(c.id);
    if(qa.dataset.qa==='analyze'){ startDraft(c,it); renderQueue(); drawSelection(); renderSide(); const f=document.getElementById('f-event'); if(f) f.focus(); }
    else if(qa.dataset.qa==='review' || qa.dataset.qa==='cancelask') act(qa.dataset.qa);
  });
  document.getElementById('queue').addEventListener('keydown', e=>{ const li=e.target.closest('.qitem'); if(!li || e.target.closest('[data-qa]')) return;
    if(e.key==='Enter'||e.key===' '){ e.preventDefault(); select(li.dataset.id); }
    if(e.key==='ArrowDown'||e.key==='ArrowUp'){ e.preventDefault(); let sib=li; do { sib=e.key==='ArrowDown'?sib.nextElementSibling:sib.previousElementSibling; } while(sib && !sib.classList.contains('qitem')); if(sib) sib.focus(); } });
  document.querySelectorAll('.filters button').forEach(b=>b.onclick=()=>{ S.filter=b.dataset.f; document.querySelectorAll('.filters button').forEach(x=>x.setAttribute('aria-pressed', x===b)); renderQueue(); });
  const jsel=document.getElementById('juris');
  [...new Set(D.cands.map(c=>c.uf))].sort().forEach(u=>{ const o=document.createElement('option'); o.value=u; o.textContent=`Civil protection, ${u}`; if(u===S.juris) o.selected=true; jsel.appendChild(o); });
  jsel.onchange=()=>{ S.juris=jsel.value; renderQueue(); renderSide(); };
  document.getElementById('zoom-out').onclick=()=>select(null);
  document.getElementById('sound').onclick=e=>{ S.sound=!S.sound; e.target.textContent=`Alert sound: ${S.sound?'on':'off'}`; };
  window.addEventListener('resize', ()=>{ if(VB) setVB(S.sel?fitVB(byId[S.sel].bbox):brazilVB(), false); });

  /* ---------- tabs, how-to, remembered sections ---------- */
  const TABS=['phone','real','log'];
  function showTab(name, reveal){
    TABS.forEach(t=>{ const b=document.getElementById('tab-'+t), p=document.getElementById('pane-'+t); const on=t===name; b.setAttribute('aria-selected', on); b.tabIndex=on?0:-1; p.hidden=!on; });
    if(reveal){ const r=document.getElementById('lower').getBoundingClientRect(); if(r.top>innerHeight-120 || r.bottom<0) document.getElementById('lower').scrollIntoView({behavior: matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth', block:'start'}); }
  }
  TABS.forEach((t,i)=>{ const b=document.getElementById('tab-'+t); b.addEventListener('click',()=>showTab(t));
    b.addEventListener('keydown',e=>{ if(e.key!=='ArrowRight'&&e.key!=='ArrowLeft') return; const n=TABS[(i+(e.key==='ArrowRight'?1:TABS.length-1))%TABS.length]; showTab(n); document.getElementById('tab-'+n).focus(); }); });
  document.getElementById('side').addEventListener('toggle', e=>{ const k=e.target.dataset && e.target.dataset.keep; if(k) S.open[k]=e.target.open; }, true);
  document.getElementById('howto').addEventListener('click',()=>openSheet(`<div><span class="eyebrow">How it works</span><h2 id="sheet-h">From a satellite fire to a phone alert</h2></div>
    <ol class="howto">
      <li><strong>Pick an area.</strong> The list is ordered by a provisional score: strongest fire, number of detections and high-confidence detections from NASA satellites. The goal is to replace it with the harmonized MODIS + VIIRS baseline, which shows how unusual a fire is for that place and month.</li>
      <li><strong>Analyze.</strong> Check the fires on the map, then write the alert: level, what is happening and what people should do.</li>
      <li><strong>Approve.</strong> A second person reviews the message and the checks, then sends it. In this prototype the second person is simulated; a real system needs separate logins.</li>
      <li><strong>Phones in the area</strong> show the alert. Only civil protection can send a real alert, through the government platform (IDAP). Here it is simulated on the phone preview, or on a real phone through the Real phone tab.</li>
    </ol>
    <div class="actions"><button class="btn primary" data-sa="close">Got it</button></div>`));

  /* ---------- boot ---------- */
  const inBr=D.points.filter(p=>p.uf).length;
  document.getElementById('mapstats').textContent = `${inBr} fires in Brazil across ${D.cands.length} municipalities. The ${D.points.length-inBr} grey points are in neighbouring countries and cannot be alerted.`;
  buildMap(); renderQueue(); renderSide(); renderLog(); renderPhoneClock(); setInterval(renderPhoneClock, 15000);
  select((D.cands.find(c=>c.uf===S.juris)||D.cands[0]).id);
}

fetch('data.json')
  .then(r => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
  .then(main)
  .catch(err => {
    const box = document.getElementById('side');
    box.innerHTML = '<div class="phead"><h2>Could not load data.json</h2></div>' +
      '<div class="empty">Open this page through a web server (for example <code>python -m http.server</code> in this folder, or GitHub Pages). ' +
      'Browsers block reading local files when the page is opened directly from disk.<br><br><code>' + String(err).replace(/[<>&]/g, '') + '</code></div>';
  });
