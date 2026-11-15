import { Component, ViewChild, computed, effect, inject, OnInit, OnDestroy } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { HotspotDataService } from '../../core/services/hotspot-data.service';
import { ExplorerStateService } from '../../core/services/explorer-state.service';
import { I18nService } from '../../core/services/i18n.service';
import { MapViewComponent } from './map-view.component';

const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const PRESETS: Array<[string, number]> = [
  ['Today', 1],
  ['7d', 7],
  ['24d', 24],
  ['30d', 30],
  ['60d', 60],
];

@Component({
  selector: 'app-explorer-page',
  standalone: true,
  imports: [FormsModule, RouterLink, MapViewComponent],
  templateUrl: './explorer.page.html',
  styleUrl: './explorer.page.scss',
})
export class ExplorerPage implements OnInit, OnDestroy {
  @ViewChild(MapViewComponent) mapView?: MapViewComponent;

  readonly data = inject(HotspotDataService);
  readonly state = inject(ExplorerStateService);
  readonly i18n = inject(I18nService);

  search = '';
  dragAnchor: number | null = null;
  readonly months = MON;
  readonly presets = PRESETS;

  isPresetOn(len: number): boolean {
    const n = this.state.days().length;
    if (!n) return false;
    return this.state.rangeEnd() === n - 1 && this.state.rangeEnd() - this.state.rangeStart() + 1 === Math.min(len, n);
  }

  applyPreset(len: number): void {
    const n = this.state.days().length;
    this.state.setPreset(Math.min(len, Math.max(1, n)));
  }

  readonly viirsCount = computed(
    () => this.data.points().filter((p) => /viirs/i.test(p.sensor)).length,
  );
  readonly modisCount = computed(
    () => this.data.points().filter((p) => !/viirs/i.test(p.sensor)).length,
  );

  readonly monthMeta = computed(() => {
    const Lyr = this.state.layers();
    const vals = this.data.calendarMonthValues();
    const ready = this.data.calendarReady();
    const last = this.state.lastDataMonth();
    return MON.map((label, i) => {
      const month1 = i + 1;
      const hasData = ready && (vals[month1] != null || (last >= 0 && i <= last));
      const off = !!Lyr.offMonths[i];
      const v = vals[month1];
      return {
        i,
        label: label[0],
        full: label,
        hasData,
        off,
        color: hasData
          ? this.state.monthColors[i]
          : 'repeating-linear-gradient(135deg,#2b313b 0 4px,#1b2028 4px 8px)',
        tip: !ready
          ? `${label} · awaiting calendar.json`
          : hasData
            ? off
              ? `${label} · hidden`
              : v != null
                ? `${label} · ${v.toFixed(0)}`
                : label
            : `${label} · no data`,
      };
    });
  });

  readonly histMax = computed(() => {
    const days = this.state.days();
    return Math.max(1, ...days.map((d) => d.viirs + d.modis));
  });

  readonly sources = [
    { val: 'all' as const, label: 'All' },
    { val: 'VIIRS' as const, label: 'VIIRS' },
    { val: 'MODIS' as const, label: 'MODIS' },
  ];
  readonly colorModes = [
    { val: 'age' as const, labelKey: 'color.age' },
    { val: 'sensor' as const, labelKey: 'color.sensor' },
  ];
  readonly confs = [
    { val: 'all' as const, labelKey: 'conf.all' },
    { val: 'nominal' as const, labelKey: 'conf.nominal' },
    { val: 'high' as const, labelKey: 'conf.high' },
  ];
  readonly tools: Array<{ k: 'circle' | 'measure' | 'pin' | 'layers' | 'camera' | 'share' | 'help'; icon: string }> = [
    { k: 'circle', icon: 'M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20z' },
    { k: 'measure', icon: 'M2 12h20M12 2v20' },
    { k: 'pin', icon: 'M12 21s7-5.2 7-11a7 7 0 1 0-14 0c0 5.8 7 11 7 11z M12 10a2 2 0 1 0 0-4 2 2 0 0 0 0 4z' },
    { k: 'layers', icon: 'M12 2l10 5-10 5L2 7l10-5zM2 12l10 5 10-5M2 17l10 5 10-5' },
    { k: 'camera', icon: 'M4 7h3l2-2h6l2 2h3v12H4z M12 17a4 4 0 1 0 0-8 4 4 0 0 0 0 8z' },
    { k: 'share', icon: 'M4 12v7a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-7M16 6l-4-4-4 4M12 2v14' },
    { k: 'help', icon: 'M12 18h.01M9.1 9a3 3 0 1 1 4.6 2.6c-.8.5-1.2 1-1.2 2' },
  ];

  constructor() {
    effect(() => {
      const c = this.data.calendar();
      if (!c?.rows.length) {
        this.state.lastDataMonth.set(-1);
        return;
      }
      const year = c.current_year ?? Math.max(...c.rows.map((r) => r.year));
      const months = c.rows.filter((r) => r.year === year).map((r) => r.month);
      this.state.lastDataMonth.set(months.length ? Math.max(...months) - 1 : -1);
    });
  }

  ngOnInit(): void {
    if (!this.data.points().length) this.data.load();
    // Rebuild histogram when data arrives
    const id = window.setInterval(() => {
      if (this.data.points().length && this.mapView) {
        this.mapView.rebuildHistogram();
        window.clearInterval(id);
      }
    }, 200);
  }

  ngOnDestroy(): void {
    this.state.playing.set(false);
  }

  t(key: string, vars?: Record<string, string | number>): string {
    return this.i18n.t(key, vars);
  }

  onSearch(): void {
    if (this.mapView?.flyToSearch(this.search)) return;
    alert(this.i18n.lang() === 'pt' ? 'Use lat, lon (ex.: -16.6, -49.2)' : 'Use lat, lon (e.g. -16.6, -49.2)');
  }

  toggleTool(k: (typeof this.tools)[number]['k']): void {
    if (k === 'layers') {
      this.state.panelOpen.update((v) => !v);
      this.state.panelView.set('layers');
      return;
    }
    if (k === 'pin') {
      this.mapView?.locate();
      return;
    }
    if (k === 'camera' || k === 'share' || k === 'help') {
      alert(k === 'help' ? 'FIRMS Angular explorer — Space Apps 2026 simulation.' : `${k} — coming soon`);
      return;
    }
    if (k === 'measure') {
      this.mapView?.clearMeasure();
    }
    if (k === 'circle') {
      this.state.circle.set(null);
      this.state.report.set(null);
      this.state.circleStage.set('center');
    }
    this.state.tool.set(this.state.tool() === k ? null : k);
  }

  dayDown(i: number): void {
    this.dragAnchor = i;
    this.state.setRange(i, i);
  }

  dayEnter(i: number): void {
    if (this.dragAnchor == null) return;
    this.state.setRange(this.dragAnchor, i);
  }

  dayUp(): void {
    this.dragAnchor = null;
  }

  togglePlay(): void {
    this.state.playing.update((p) => !p);
  }

  step(delta: number): void {
    const cur = this.state.playDay() ?? this.state.rangeEnd();
    const next = Math.min(this.state.rangeEnd(), Math.max(this.state.rangeStart(), cur + delta));
    this.state.playDay.set(next);
    this.state.playing.set(false);
  }

  exportCsv(): void {
    const csv = this.mapView?.exportSelectionCsv() ?? '';
    if (!csv) return;
    const blob = new Blob([csv], { type: 'text/csv' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'selection-hotspots.csv';
    a.click();
    URL.revokeObjectURL(a.href);
  }

  clearSelection(): void {
    this.state.circle.set(null);
    this.state.report.set(null);
    this.state.circleStage.set(null);
    this.state.panelView.set('layers');
  }

  newSelection(): void {
    this.clearSelection();
    this.state.tool.set('circle');
    this.state.circleStage.set('center');
  }

  barHeight(n: number): number {
    return Math.max(2, (n / this.histMax()) * 100);
  }

  peakOf(values: number[]): number {
    return values.length ? Math.max(...values) : 0;
  }

  isInRange(i: number): boolean {
    return i >= this.state.rangeStart() && i <= this.state.rangeEnd();
  }

  dayLabel(i: number, d: Date): string {
    const n = this.state.days().length;
    const s = this.state.rangeStart();
    const e = this.state.rangeEnd();
    const dn = d.getDate();
    const step = n > 45 ? 5 : n > 20 ? 3 : 1;
    if (i === s || i === e || i === n - 1 || (dn % step === 0 && Math.abs(i - s) > 1 && Math.abs(i - e) > 1 && i < n - 2)) {
      return String(dn);
    }
    return '';
  }
}
