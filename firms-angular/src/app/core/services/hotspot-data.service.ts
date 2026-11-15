import { HttpClient } from '@angular/common/http';
import { Injectable, computed, inject, signal } from '@angular/core';
import { catchError, map, of, tap } from 'rxjs';
import {
  AlertTier,
  CandidateMun,
  DataPayload,
  ForecastPayload,
  HarmonizedCalendarPayload,
  HarmonizedMunPayload,
  HarmonizedMunStats,
  HotspotPoint,
} from '../models';

const POINT_FIELDS = ['lat', 'lon', 'frp', 'conf', 'sensor', 'sat', 'date', 'time', 'dn', 'mun', 'uf'] as const;

function scoreOf(c: CandidateMun): number {
  return c.frpMax + 0.5 * c.n + 5 * c.high;
}

function tierOf(score: number): AlertTier {
  if (score >= 50) return 'high';
  if (score >= 20) return 'elev';
  return 'watch';
}

function normalizePoint(raw: HotspotPoint | unknown[], fields?: string[]): HotspotPoint {
  if (!Array.isArray(raw)) {
    return {
      ...raw,
      conf: raw.conf,
      frp: Number(raw.frp) || 0,
      lat: Number(raw.lat),
      lon: Number(raw.lon),
    };
  }
  const keys = fields?.length ? fields : [...POINT_FIELDS];
  const obj: Record<string, unknown> = {};
  keys.forEach((k, i) => {
    obj[k] = raw[i];
  });
  return {
    lat: Number(obj['lat']),
    lon: Number(obj['lon']),
    frp: Number(obj['frp']) || 0,
    conf: (obj['conf'] as string | number) ?? 0,
    sensor: String(obj['sensor'] ?? ''),
    sat: String(obj['sat'] ?? ''),
    date: obj['date'] != null ? String(obj['date']) : undefined,
    time: String(obj['time'] ?? ''),
    dn: String(obj['dn'] ?? ''),
    mun: (obj['mun'] as string | null) ?? null,
    uf: (obj['uf'] as string | null) ?? null,
  };
}

function enrichCandidates(cands: CandidateMun[]): CandidateMun[] {
  return cands
    .map((c) => {
      const score = scoreOf(c);
      return { ...c, score, tier: tierOf(score) };
    })
    .sort((a, b) => (b.score ?? 0) - (a.score ?? 0));
}

function confValue(conf: number | string): number {
  if (typeof conf === 'number') return conf;
  const n = Number(conf);
  if (!Number.isNaN(n)) return n;
  const s = String(conf).toLowerCase();
  if (s === 'high' || s === 'h') return 80;
  if (s === 'nominal' || s === 'n') return 50;
  if (s === 'low' || s === 'l') return 20;
  return 0;
}

function emptyCalendar(): HarmonizedCalendarPayload {
  return {
    kind: 'harmonized-calendar',
    generated: undefined,
    current_year: undefined,
    current_month: undefined,
    rows: [],
    grid: {},
  };
}

function emptyMun(): HarmonizedMunPayload {
  return { kind: 'harmonized-mun', generated: undefined, byId: {} };
}

@Injectable({ providedIn: 'root' })
export class HotspotDataService {
  private readonly http = inject(HttpClient);

  readonly loading = signal(true);
  readonly error = signal<string | null>(null);
  readonly points = signal<HotspotPoint[]>([]);
  readonly candidates = signal<CandidateMun[]>([]);
  readonly states = signal<DataPayload['states']>([]);
  readonly meta = signal<DataPayload['meta'] | null>(null);
  readonly forecast = signal<ForecastPayload | null>(null);
  readonly sourceFile = signal<string>('');

  /** Série mensal harmonizada (calendar.json). Stub vazio = UI em awaiting. */
  readonly calendar = signal<HarmonizedCalendarPayload | null>(null);
  /** Join município → stats (harmonized_mun.json). */
  readonly harmonizedMun = signal<HarmonizedMunPayload | null>(null);

  readonly pointCount = computed(() => this.points().length);

  readonly calendarReady = computed(() => {
    const c = this.calendar();
    return !!(c && c.rows.length > 0);
  });

  readonly harmonizedMunReady = computed(() => {
    const h = this.harmonizedMun();
    return !!(h && Object.keys(h.byId).length > 0);
  });

  /** Meses 1–12 com valor no ano corrente do calendar (ou último ano com dados). */
  readonly calendarMonthValues = computed(() => {
    const c = this.calendar();
    const out: Record<number, number> = {};
    if (!c?.rows.length) return out;
    const year =
      c.current_year ??
      Math.max(...c.rows.map((r) => r.year));
    for (const r of c.rows) {
      if (r.year === year) out[r.month] = r.value;
    }
    return out;
  });

  load(): void {
    this.loading.set(true);
    this.error.set(null);
    this.http
      .get<DataPayload>('data/data.json')
      .pipe(
        catchError(() =>
          this.http.get<DataPayload>('data/data-sample.json').pipe(
            tap(() => this.sourceFile.set('data-sample.json')),
            catchError((err) => {
              this.error.set(String(err?.message ?? err));
              this.loading.set(false);
              return of(null);
            }),
          ),
        ),
        tap((payload) => {
          if (payload && !this.sourceFile()) this.sourceFile.set('data.json');
        }),
        map((payload) => (payload ? this.applyPayload(payload) : null)),
      )
      .subscribe(() => this.loading.set(false));

    this.http
      .get<ForecastPayload>('data/forecast.json')
      .pipe(catchError(() => of(null)))
      .subscribe((f) => this.forecast.set(f));

    this.http
      .get<HarmonizedCalendarPayload>('data/calendar.json')
      .pipe(
        catchError(() => of(emptyCalendar())),
        map((raw) => {
          if (!raw || raw.kind !== 'harmonized-calendar') return emptyCalendar();
          return {
            ...raw,
            rows: Array.isArray(raw.rows) ? raw.rows : [],
            grid: raw.grid ?? {},
          };
        }),
      )
      .subscribe((c) => this.calendar.set(c));

    this.http
      .get<HarmonizedMunPayload>('data/harmonized_mun.json')
      .pipe(
        catchError(() => of(emptyMun())),
        map((raw) => {
          if (!raw || raw.kind !== 'harmonized-mun') return emptyMun();
          return { ...raw, byId: raw.byId ?? {} };
        }),
      )
      .subscribe((h) => this.harmonizedMun.set(h));
  }

  munHarm(id: string): HarmonizedMunStats | null {
    const byId = this.harmonizedMun()?.byId;
    if (!byId) return null;
    return byId[id] ?? byId['*'] ?? null;
  }

  private applyPayload(payload: DataPayload): DataPayload {
    const points = (payload.points ?? []).map((p) =>
      normalizePoint(p as HotspotPoint | unknown[], payload.point_fields),
    );
    const cands = enrichCandidates(payload.cands ?? []);
    this.points.set(points);
    this.candidates.set(cands);
    this.states.set(payload.states ?? []);
    this.meta.set(payload.meta ?? null);
    return payload;
  }

  static isHighConfidence(conf: number | string): boolean {
    const v = confValue(conf);
    if (typeof conf === 'string' && /high|^h$/i.test(conf)) return true;
    return v >= 80;
  }

  static confNumeric(conf: number | string): number {
    return confValue(conf);
  }

  static pointDayKey(p: HotspotPoint): string {
    if (p.date && /^\d{4}-\d{2}-\d{2}/.test(p.date)) return p.date.slice(0, 10);
    if (p.date && /^\d{2}\/\d{2}\/\d{4}/.test(p.date)) {
      const [d, m, y] = p.date.split('/');
      return `${y}-${m}-${d}`;
    }
    // NRT sample without date: use a synthetic window ending today
    return new Date().toISOString().slice(0, 10);
  }
}
