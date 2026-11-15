import { Injectable, computed, signal } from '@angular/core';
import {
  ColorMode,
  ConfidenceLevel,
  DayBucket,
  LayerState,
  SelectionReport,
  SourceFilter,
} from '../models';

export type ExplorerTool = 'circle' | 'measure' | 'pin' | 'layers' | 'camera' | 'share' | 'help' | null;
export type PanelView = 'layers' | 'report';

const MONTH_COLORS = Array.from({ length: 12 }, (_, i) => {
  const l = (0.93 - i * 0.038).toFixed(3);
  const c = (0.03 + i * 0.017).toFixed(3);
  const h = 215 + i * 9;
  return `oklch(${l} ${c} ${h})`;
});

@Injectable({ providedIn: 'root' })
export class ExplorerStateService {
  readonly panelOpen = signal(true);
  readonly panelView = signal<PanelView>('layers');
  readonly tool = signal<ExplorerTool>(null);
  readonly layers = signal<LayerState>({
    source: 'all',
    colorBy: 'age',
    confidence: 'all',
    burnEnabled: false,
    ibgeEnabled: false,
    offMonths: {},
    hoverMonth: null,
  });

  readonly activeBase = signal<'sat' | 'relief' | 'night'>('sat');
  readonly dataWindowLabel = signal<string>('');

  readonly spanDays = signal(60);
  readonly rangeStart = signal(0);
  readonly rangeEnd = signal(59);
  readonly playDay = signal<number | null>(null);
  readonly playing = signal(false);
  readonly speed = signal(1);
  readonly days = signal<DayBucket[]>([]);
  readonly calOpen = signal(false);

  readonly mapCenter = signal<{ lat: number; lon: number }>({ lat: -15, lon: -60 });
  readonly visibleCount = signal(0);

  readonly circle = signal<{
    lat: number;
    lon: number;
    radiusKm: number;
  } | null>(null);
  readonly circleStage = signal<'center' | 'radius' | null>(null);
  readonly report = signal<SelectionReport | null>(null);

  readonly measurePoints = signal<Array<{ lat: number; lon: number }>>([]);
  readonly measureKm = signal<number | null>(null);

  readonly monthColors = MONTH_COLORS;
  /**
   * Último mês (0–11) com dados no calendário harmonizado.
   * Atualizado pelo explorer quando `calendar.json` carrega; -1 = awaiting.
   */
  readonly lastDataMonth = signal(-1);

  readonly rangeLabel = computed(() => {
    const days = this.days();
    if (!days.length) return '—';
    const s = days[this.rangeStart()]?.date;
    const e = days[this.rangeEnd()]?.date;
    if (!s || !e) return '—';
    const fmt = (d: Date) =>
      d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    if (this.rangeStart() === this.rangeEnd()) return `${fmt(e)}, ${e.getFullYear()}`;
    return `${fmt(s)} – ${fmt(e)}, ${e.getFullYear()}`;
  });

  readonly durationLabel = computed(() => {
    const n = this.rangeEnd() - this.rangeStart() + 1;
    return n === 1 ? '1 day' : `${n} days`;
  });

  setSource(source: SourceFilter): void {
    this.layers.update((l) => ({ ...l, source }));
  }

  setColorBy(colorBy: ColorMode): void {
    this.layers.update((l) => ({ ...l, colorBy }));
  }

  setConfidence(confidence: ConfidenceLevel): void {
    this.layers.update((l) => ({ ...l, confidence }));
  }

  toggleBurn(): void {
    this.layers.update((l) => ({ ...l, burnEnabled: !l.burnEnabled }));
  }

  toggleIbge(): void {
    this.layers.update((l) => ({ ...l, ibgeEnabled: !l.ibgeEnabled }));
  }

  toggleMonth(m: number): void {
    this.layers.update((l) => {
      const off = { ...l.offMonths };
      if (off[m]) delete off[m];
      else off[m] = true;
      return { ...l, offMonths: off };
    });
  }

  setHoverMonth(m: number | null): void {
    this.layers.update((l) => ({ ...l, hoverMonth: m }));
  }

  showAllMonths(): void {
    this.layers.update((l) => ({ ...l, offMonths: {} }));
  }

  showLast3Months(): void {
    const last = this.lastDataMonth();
    if (last < 0) return;
    const off: Record<number, boolean> = {};
    for (let i = 0; i <= last; i++) {
      if (i < last - 2) off[i] = true;
    }
    this.layers.update((l) => ({ ...l, offMonths: off }));
  }

  setRange(start: number, end: number): void {
    const a = Math.max(0, Math.min(start, end));
    const b = Math.min(this.days().length - 1, Math.max(start, end));
    this.rangeStart.set(a);
    this.rangeEnd.set(b);
    this.playDay.set(null);
  }

  setPreset(len: number): void {
    const n = this.days().length;
    if (!n) return;
    this.setRange(Math.max(0, n - len), n - 1);
  }

  initDays(end: Date, span: number): void {
    const days: DayBucket[] = [];
    for (let i = span - 1; i >= 0; i--) {
      const d = new Date(end);
      d.setHours(12, 0, 0, 0);
      d.setDate(d.getDate() - i);
      const key = d.toISOString().slice(0, 10);
      days.push({ date: d, key, viirs: 0, modis: 0 });
    }
    this.days.set(days);
    this.spanDays.set(span);
    this.rangeStart.set(0);
    this.rangeEnd.set(days.length - 1);
  }

  fillHistogram(counts: Map<string, { v: number; m: number }>): void {
    this.days.update((days) =>
      days.map((d) => {
        const c = counts.get(d.key) ?? { v: 0, m: 0 };
        return { ...d, viirs: c.v, modis: c.m };
      }),
    );
  }
}
