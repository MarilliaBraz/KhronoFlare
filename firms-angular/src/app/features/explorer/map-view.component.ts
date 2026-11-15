import {
  AfterViewInit,
  Component,
  ElementRef,
  OnDestroy,
  ViewChild,
  effect,
  inject,
  untracked,
} from '@angular/core';
import * as L from 'leaflet';
import { HotspotDataService } from '../../core/services/hotspot-data.service';
import { ExplorerStateService } from '../../core/services/explorer-state.service';
import { HotspotPoint, SelectionReport } from '../../core/models';
import {
  ageColor,
  circleAreaKm2,
  haversineKm,
  parseSearch,
  sensorColor,
  statePolygonsToLatLngs,
} from '../../core/utils/geo';

const GIBS = 'https://gibs.earthdata.nasa.gov/wmts/epsg3857/best';

@Component({
  selector: 'app-map-view',
  standalone: true,
  template: `<div #mapHost class="map-host"></div>`,
  styles: [
    `
      :host {
        display: block;
        position: absolute;
        inset: 0;
      }
      .map-host {
        width: 100%;
        height: 100%;
        background: #1a2016;
      }
    `,
  ],
})
export class MapViewComponent implements AfterViewInit, OnDestroy {
  @ViewChild('mapHost', { static: true }) mapHost!: ElementRef<HTMLDivElement>;

  private readonly data = inject(HotspotDataService);
  readonly state = inject(ExplorerStateService);

  private map?: L.Map;
  private pointsLayer?: L.LayerGroup;
  private burnLayer?: L.LayerGroup;
  private ibgeLayer?: L.LayerGroup;
  private circleLayer?: L.LayerGroup;
  private measureLayer?: L.LayerGroup;
  private baseLayers: Record<string, L.TileLayer> = {};
  private playTimer?: number;

  constructor() {
    effect(() => {
      this.data.points();
      this.state.layers();
      this.state.rangeStart();
      this.state.rangeEnd();
      this.state.playDay();
      this.state.days();
      untracked(() => this.redrawPoints());
    });

    effect(() => {
      this.state.layers().burnEnabled;
      this.state.layers().offMonths;
      this.state.layers().hoverMonth;
      this.data.calendarReady();
      this.state.lastDataMonth();
      untracked(() => this.redrawBurn());
    });

    effect(() => {
      this.data.states();
      this.state.layers().ibgeEnabled;
      untracked(() => this.redrawIbgeMask());
    });

    effect(() => {
      this.state.circle();
      untracked(() => this.redrawCircle());
    });

    effect(() => {
      const playing = this.state.playing();
      const speed = this.state.speed();
      untracked(() => this.syncPlayback(playing, speed));
    });
  }

  ngAfterViewInit(): void {
    this.map = L.map(this.mapHost.nativeElement, {
      zoomControl: false,
      attributionControl: false,
      center: [-15, -60],
      zoom: 4,
      minZoom: 3,
      maxZoom: 12,
    });

    const date = '2026-11-14';
    this.baseLayers = {
      sat: L.tileLayer(
        `${GIBS}/VIIRS_NOAA20_CorrectedReflectance_TrueColor/default/${date}/GoogleMapsCompatible_Level9/{z}/{y}/{x}.jpg`,
        { maxZoom: 9, errorTileUrl: 'fallback-relief.jpg' },
      ),
      relief: L.tileLayer(
        `${GIBS}/BlueMarble_NextGeneration/default/${date}/GoogleMapsCompatible_Level8/{z}/{y}/{x}.jpeg`,
        { maxZoom: 8, errorTileUrl: 'fallback-relief.jpg' },
      ),
      night: L.tileLayer(
        `${GIBS}/VIIRS_Black_Marble/default/2016-01-01/GoogleMapsCompatible_Level8/{z}/{y}/{x}.png`,
        { maxZoom: 8, errorTileUrl: 'fallback-relief.jpg' },
      ),
    };
    this.baseLayers['sat'].addTo(this.map);
    this.state.activeBase.set('sat');

    this.map.createPane('ibgeMask');
    this.map.getPane('ibgeMask')!.style.zIndex = '350';

    this.ibgeLayer = L.layerGroup().addTo(this.map);
    this.burnLayer = L.layerGroup().addTo(this.map);
    this.pointsLayer = L.layerGroup().addTo(this.map);
    this.circleLayer = L.layerGroup().addTo(this.map);
    this.measureLayer = L.layerGroup().addTo(this.map);

    this.map.on('moveend', () => {
      const c = this.map!.getCenter();
      this.state.mapCenter.set({ lat: +c.lat.toFixed(3), lon: +c.lng.toFixed(3) });
    });

    this.map.on('click', (ev) => this.onMapClick(ev));
    this.map.on('mousemove', (ev) => this.onMapMove(ev));

    document.addEventListener('keydown', this.onKey);
    this.rebuildHistogram();
    this.redrawIbgeMask();
    this.redrawPoints();
    this.redrawBurn();
    // Layout overlays can settle after first paint
    queueMicrotask(() => this.map?.invalidateSize());
    window.setTimeout(() => this.map?.invalidateSize(), 200);
  }

  ngOnDestroy(): void {
    document.removeEventListener('keydown', this.onKey);
    if (this.playTimer) window.clearInterval(this.playTimer);
    this.map?.remove();
  }

  private onKey = (ev: KeyboardEvent) => {
    if (ev.key === 'Escape') {
      this.state.tool.set(null);
      this.state.circleStage.set(null);
      if (!this.state.circle()) this.state.report.set(null);
    }
  };

  setBase(kind: 'sat' | 'relief' | 'night'): void {
    const cur = this.state.activeBase();
    if (!this.map || cur === kind) return;
    this.map.removeLayer(this.baseLayers[cur]);
    this.baseLayers[kind].addTo(this.map);
    this.state.activeBase.set(kind);
  }

  zoomIn(): void {
    this.map?.zoomIn();
  }

  zoomOut(): void {
    this.map?.zoomOut();
  }

  flyToSearch(q: string): boolean {
    const p = parseSearch(q);
    if (!p || !this.map) return false;
    this.map.setView([p.lat, p.lon], 8);
    return true;
  }

  locate(): void {
    this.map?.locate({ setView: true, maxZoom: 8 });
  }

  private onMapClick(ev: L.LeafletMouseEvent): void {
    const tool = this.state.tool();
    if (tool === 'circle') {
      const stage = this.state.circleStage();
      if (!stage || stage === 'center') {
        this.state.circle.set({ lat: ev.latlng.lat, lon: ev.latlng.lng, radiusKm: 0 });
        this.state.circleStage.set('radius');
      } else {
        const c = this.state.circle();
        if (!c) return;
        const r = haversineKm(c, { lat: ev.latlng.lat, lon: ev.latlng.lng });
        const next = { ...c, radiusKm: Math.max(1, r) };
        this.state.circle.set(next);
        this.state.circleStage.set(null);
        this.state.tool.set(null);
        this.buildReport(next);
        this.state.panelView.set('report');
        this.state.panelOpen.set(true);
      }
      return;
    }
    if (tool === 'measure') {
      const pts = [...this.state.measurePoints(), { lat: ev.latlng.lat, lon: ev.latlng.lng }];
      this.state.measurePoints.set(pts);
      this.redrawMeasure(pts);
      if (pts.length >= 2) {
        this.state.measureKm.set(haversineKm(pts[0], pts[1]));
      }
    }
  }

  private onMapMove(ev: L.LeafletMouseEvent): void {
    if (this.state.tool() !== 'circle' || this.state.circleStage() !== 'radius') return;
    const c = this.state.circle();
    if (!c) return;
    const r = haversineKm(c, { lat: ev.latlng.lat, lon: ev.latlng.lng });
    this.state.circle.set({ ...c, radiusKm: Math.max(0.5, r) });
  }

  private filteredPoints(): HotspotPoint[] {
    const layers = this.state.layers();
    const days = this.state.days();
    const play = this.state.playDay();
    const rs = this.state.rangeStart();
    const re = this.state.rangeEnd();
    const keys = new Set(
      play != null
        ? [days[play]?.key].filter(Boolean)
        : days.slice(rs, re + 1).map((d) => d.key),
    );

    return this.data.points().filter((p) => {
      if (layers.source !== 'all') {
        const isV = /viirs/i.test(p.sensor);
        if (layers.source === 'VIIRS' && !isV) return false;
        if (layers.source === 'MODIS' && isV) return false;
      }
      const conf = HotspotDataService.confNumeric(p.conf);
      if (layers.confidence === 'nominal' && conf < 30) return false;
      if (layers.confidence === 'high' && conf < 80 && !HotspotDataService.isHighConfidence(p.conf))
        return false;
      if (keys.size) {
        const k = HotspotDataService.pointDayKey(p);
        // If point dates fall outside the synthetic window, keep those matching end or unknown
        if (!keys.has(k)) {
          // allow points whose date isn't in span if span covers "today" bucket used as fallback
          if (days.some((d) => d.key === k)) return false;
        }
      }
      return true;
    });
  }

  private redrawPoints(): void {
    if (!this.pointsLayer || !this.map) return;
    this.pointsLayer.clearLayers();
    const layers = this.state.layers();
    const days = this.state.days();
    const endKey = days[days.length - 1]?.key;
    const endDate = endKey ? new Date(endKey + 'T12:00:00') : new Date();
    const pts = this.filteredPoints();
    this.state.visibleCount.set(pts.length);

    // Canvas-ish: circle markers in batches
    for (const p of pts) {
      const key = HotspotDataService.pointDayKey(p);
      const ageDays = Math.max(
        0,
        Math.round((endDate.getTime() - new Date(key + 'T12:00:00').getTime()) / 86400000),
      );
      const color = layers.colorBy === 'sensor' ? sensorColor(p.sensor) : ageColor(ageDays);
      const isViirs = /viirs/i.test(p.sensor);
      const marker = L.circleMarker([p.lat, p.lon], {
        radius: isViirs ? 3 : 4,
        color: '#0000',
        fillColor: color,
        fillOpacity: 0.85,
        weight: 0,
      });
      if (!isViirs) {
        // diamond approximation via rotating square is heavy; keep circle with yellow for MODIS when age mode
      }
      marker.bindTooltip(
        `${p.sensor} · FRP ${p.frp.toFixed?.(1) ?? p.frp} · conf ${p.conf}`,
        { direction: 'top', opacity: 0.9 },
      );
      marker.addTo(this.pointsLayer);
    }
  }

  /** Contornos de UF apenas — sem máscara escura do mundo. */
  private redrawIbgeMask(): void {
    if (!this.ibgeLayer || !this.map) return;
    this.ibgeLayer.clearLayers();
    if (!this.state.layers().ibgeEnabled) return;

    const states = this.data.states() ?? [];
    for (const s of states) {
      if (!s.g?.length) continue;
      for (const poly of statePolygonsToLatLngs(s.g)) {
        L.polygon(poly, {
          color: 'rgba(255,255,255,0.55)',
          weight: 1,
          opacity: 0.75,
          fill: false,
          interactive: false,
          pane: 'ibgeMask',
        }).addTo(this.ibgeLayer!);
      }
    }
  }

  private redrawBurn(): void {
    if (!this.burnLayer || !this.map) return;
    this.burnLayer.clearLayers();
    const Lyr = this.state.layers();
    if (!Lyr.burnEnabled) return;

    // Layout ready: só desenha proxy quando o calendário harmonizado tiver linhas.
    if (!this.data.calendarReady()) return;

    const last = this.state.lastDataMonth();
    const byMonth = new Map<number, HotspotPoint[]>();
    for (const p of this.data.points()) {
      const key = HotspotDataService.pointDayKey(p);
      const m = new Date(key + 'T12:00:00').getMonth();
      if (last >= 0 && m > last) continue;
      if (Lyr.offMonths[m]) continue;
      if (Lyr.hoverMonth != null && Lyr.hoverMonth !== m) continue;
      const arr = byMonth.get(m) ?? [];
      if (arr.length < 80) arr.push(p);
      byMonth.set(m, arr);
    }

    for (const [m, pts] of byMonth) {
      const color = this.state.monthColors[m];
      const op = Lyr.hoverMonth === m ? 0.55 : Lyr.hoverMonth != null ? 0.08 : 0.35;
      for (const p of pts) {
        const rect = L.rectangle(
          [
            [p.lat - 0.08, p.lon - 0.08],
            [p.lat + 0.08, p.lon + 0.08],
          ],
          {
            color: '#fff',
            weight: Lyr.hoverMonth === m ? 1 : 0,
            fillColor: color,
            fillOpacity: op,
            interactive: false,
          },
        );
        rect.addTo(this.burnLayer!);
      }
    }
  }

  private redrawCircle(): void {
    if (!this.circleLayer) return;
    this.circleLayer.clearLayers();
    const c = this.state.circle();
    if (!c || c.radiusKm <= 0) return;
    L.circle([c.lat, c.lon], {
      radius: c.radiusKm * 1000,
      color: '#ff9a3c',
      dashArray: '6 4',
      weight: 2,
      fillColor: '#ff9a3c',
      fillOpacity: 0.07,
    }).addTo(this.circleLayer);
    L.circleMarker([c.lat, c.lon], {
      radius: 4,
      color: '#ff7a1a',
      fillColor: '#fff',
      fillOpacity: 1,
      weight: 2,
    }).addTo(this.circleLayer);
  }

  private redrawMeasure(pts: Array<{ lat: number; lon: number }>): void {
    if (!this.measureLayer) return;
    this.measureLayer.clearLayers();
    for (const p of pts) {
      L.circleMarker([p.lat, p.lon], { radius: 4, color: '#7ec8ff', fillColor: '#fff', weight: 2 }).addTo(
        this.measureLayer,
      );
    }
    if (pts.length >= 2) {
      L.polyline(
        pts.map((p) => [p.lat, p.lon] as [number, number]),
        { color: '#7ec8ff', weight: 2 },
      ).addTo(this.measureLayer);
    }
  }

  clearMeasure(): void {
    this.state.measurePoints.set([]);
    this.state.measureKm.set(null);
    this.measureLayer?.clearLayers();
  }

  private buildReport(c: { lat: number; lon: number; radiusKm: number }): void {
    const days = this.state.days();
    const rs = this.state.rangeStart();
    const re = this.state.rangeEnd();
    const span = days.slice(rs, re + 1);
    const perDay = span.map(() => 0);
    let viirs = 0;
    let modis = 0;
    let high = 0;
    let lastDet = '—';
    let lastTs = 0;
    const inside: HotspotPoint[] = [];

    for (const p of this.data.points()) {
      if (haversineKm(c, p) > c.radiusKm) continue;
      inside.push(p);
      if (/viirs/i.test(p.sensor)) viirs++;
      else modis++;
      if (HotspotDataService.isHighConfidence(p.conf)) high++;
      const key = HotspotDataService.pointDayKey(p);
      const idx = span.findIndex((d) => d.key === key);
      if (idx >= 0) perDay[idx]++;
      const ts = new Date(key + 'T12:00:00').getTime();
      if (ts >= lastTs) {
        lastTs = ts;
        lastDet = key;
      }
    }

    let peakIdx = 0;
    for (let i = 1; i < perDay.length; i++) if (perDay[i] > perDay[peakIdx]) peakIdx = i;
    const area = circleAreaKm2(c.radiusKm);
    const report: SelectionReport = {
      center: { lat: c.lat, lon: c.lon },
      radiusKm: +c.radiusKm.toFixed(1),
      areaKm2: +area.toFixed(0),
      total: inside.length,
      viirs,
      modis,
      high,
      density: area > 0 ? +((inside.length / area) * 100).toFixed(2) : 0,
      perDay,
      peak: span[peakIdx]?.key ?? '—',
      lastDet,
    };
    this.state.report.set(report);
  }

  rebuildHistogram(): void {
    const counts = new Map<string, { v: number; m: number }>();
    for (const p of this.data.points()) {
      const key = HotspotDataService.pointDayKey(p);
      const cur = counts.get(key) ?? { v: 0, m: 0 };
      if (/viirs/i.test(p.sensor)) cur.v++;
      else cur.m++;
      counts.set(key, cur);
    }

    const keys = [...counts.keys()].sort();
    let end = new Date();
    let span = this.state.spanDays();
    if (keys.length) {
      end = new Date(keys[keys.length - 1] + 'T12:00:00');
      const first = new Date(keys[0] + 'T12:00:00');
      const realSpan = Math.max(
        1,
        Math.round((end.getTime() - first.getTime()) / 86400000) + 1,
      );
      // Janela alinhada aos dias presentes nos dados (sem inventar rampa)
      span = Math.min(Math.max(realSpan, 2), Math.max(this.state.spanDays(), realSpan));
      this.state.dataWindowLabel.set(
        realSpan <= 2
          ? `${keys[0]} → ${keys[keys.length - 1]} · ${this.data.meta()?.window_hours ?? 24}h live`
          : `${keys[0]} → ${keys[keys.length - 1]} · ${keys.length} days`,
      );
    } else {
      this.state.dataWindowLabel.set('No dated hotspots');
    }

    this.state.initDays(end, span);
    this.state.fillHistogram(counts);
  }

  private syncPlayback(playing: boolean, speed: number): void {
    if (this.playTimer) {
      window.clearInterval(this.playTimer);
      this.playTimer = undefined;
    }
    if (!playing) return;
    if (this.state.playDay() == null) this.state.playDay.set(this.state.rangeStart());
    this.playTimer = window.setInterval(() => {
      const cur = this.state.playDay() ?? this.state.rangeStart();
      const next = cur + 1;
      if (next > this.state.rangeEnd()) {
        this.state.playing.set(false);
        this.state.playDay.set(null);
        return;
      }
      this.state.playDay.set(next);
    }, 800 / speed);
  }

  exportSelectionCsv(): string {
    const r = this.state.report();
    const c = this.state.circle();
    if (!r || !c) return '';
    const lines = ['lat,lon,frp,conf,sensor,date'];
    for (const p of this.data.points()) {
      if (haversineKm(c, p) > c.radiusKm) continue;
      lines.push(
        [p.lat, p.lon, p.frp, JSON.stringify(String(p.conf)), p.sensor, HotspotDataService.pointDayKey(p)].join(
          ',',
        ),
      );
    }
    return lines.join('\n');
  }
}
