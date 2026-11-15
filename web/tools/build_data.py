import json, csv, sys, math, collections
S=sys.argv[1]
def load(p): return json.load(open(p,encoding='utf-8'))
uf=load(S+'/ibge/uf.json'); est={str(e['id']):e for e in load(S+'/ibge/estados.json')}
def pip(x,y,poly):
    ins=False
    for ring in poly:
        n=len(ring)
        for i in range(n):
            x1,y1=ring[i];x2,y2=ring[(i+1)%n]
            if (y1>y)!=(y2>y) and x<(x2-x1)*(y-y1)/(y2-y1)+x1: ins=not ins
    return ins
def polys(g): return [g['coordinates']] if g['type']=='Polygon' else g['coordinates']
def find(feats,lon,lat):
    for f in feats:
        for p in polys(f['geometry']):
            if pip(lon,lat,p): return f
mun={}; names={}
for u in ['15','21','16','27','26','23','17']:
    mun[u]=load(S+f'/ibge/mun_{u}.json')['features']
    for m in load(S+f'/ibge/nomes_{u}.json'): names[str(m['id'])]=m['nome']
pts=[]
for f,sensor in [('modis_nrt_sample.csv','MODIS'),('viirs_noaa20_nrt_sample.csv','VIIRS')]:
    for r in csv.DictReader(open(S+'/repo/tests/fixtures/'+f)):
        lon,lat=float(r['longitude']),float(r['latitude'])
        st=find(uf['features'],lon,lat)
        p=dict(lat=lat,lon=lon,frp=float(r['frp']),conf=r['confidence'],sensor=sensor,sat=r['satellite'],date=r['acq_date'],time=r['acq_time'].zfill(4),dn=r['daynight'])
        if st:
            u=st['properties']['codarea']; m=find(mun[u],lon,lat)
            p['uf']=est[u]['sigla']; p['mun']=m['properties']['codarea'] if m else None
        pts.append(p)
def r4(c): return [round(c[0],3),round(c[1],3)]
def simp(g,step=1):
    return [[[r4(c) for c in ring[::step]] for ring in poly] for poly in polys(g)]
groups=collections.defaultdict(list)
for p in pts:
    if p.get('mun'): groups[p['mun']].append(p)
def hull(points):
    points=sorted(set(points))
    if len(points)<3: return points
    def cross(o,a,b): return (a[0]-o[0])*(b[1]-o[1])-(a[1]-o[1])*(b[0]-o[0])
    lo=[];up=[]
    for q in points:
        while len(lo)>=2 and cross(lo[-2],lo[-1],q)<=0: lo.pop()
        lo.append(q)
    for q in reversed(points):
        while len(up)>=2 and cross(up[-2],up[-1],q)<=0: up.pop()
        up.append(q)
    return lo[:-1]+up[:-1]
cands=[]
for code,ps in groups.items():
    u=code[:2]; feat=next(f for f in mun[u] if f['properties']['codarea']==code)
    d=0.05; corners=[]
    for p in ps:
        for dx in(-d,d):
            for dy in(-d,d): corners.append((round(p['lon']+dx,3),round(p['lat']+dy,3)))
    h=hull(corners)
    lat0=sum(p['lat'] for p in ps)/len(ps)
    area=0
    for i in range(len(h)):
        x1,y1=h[i];x2,y2=h[(i+1)%len(h)]; area+=x1*y2-x2*y1
    area=abs(area)/2*111.32*111.32*math.cos(math.radians(lat0))
    cands.append(dict(id=code,name=names.get(code,code),uf=ps[0]['uf'],n=len(ps),
        nV=sum(p['sensor']=='VIIRS' for p in ps),nM=sum(p['sensor']=='MODIS' for p in ps),
        frpSum=round(sum(p['frp'] for p in ps),1),frpMax=round(max(p['frp'] for p in ps),1),
        high=sum(p['conf'] in('h',) or (p['conf'].isdigit() and int(p['conf'])>=80) for p in ps),
        last=max(p['time'] for p in ps),dn=sorted(set(p['dn'] for p in ps)),
        poly=[list(c) for c in h],areaKm2=round(area),geom=simp(feat['geometry'])))
cands.sort(key=lambda c:-c['frpSum'])
for c in cands: print(c['name'],c['uf'],c['n'],c['nV'],c['nM'],c['frpSum'],c['frpMax'],c['high'],c['last'],c['areaKm2'])
states=[dict(uf=est[f['properties']['codarea']]['sigla'],g=simp(f['geometry'])) for f in uf['features']]
out=dict(points=[{k:p[k] for k in('lat','lon','frp','conf','sensor','sat','time','dn')}|{'mun':p.get('mun'),'uf':p.get('uf')} for p in pts],cands=cands,states=states)
s=json.dumps(out,separators=(',',':'),ensure_ascii=False)
open(S+'/build/data.json','w',encoding='utf-8').write(s); print(len(s),'bytes')
