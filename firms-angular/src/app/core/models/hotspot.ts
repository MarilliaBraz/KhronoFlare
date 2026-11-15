/** Contratos alinhados a nasa-space-apps-2026/web/data.json e forecast.json */

export type SensorKind = 'VIIRS' | 'MODIS' | string;
export type ConfidenceLevel = 'all' | 'nominal' | 'high';
export type ColorMode = 'age' | 'sensor';
export type SourceFilter = 'all' | 'VIIRS' | 'MODIS';
export type AlertStatus = 'new' | 'draft' | 'pending' | 'sent' | 'cancelled' | 'dismissed';
export type AlertTier = 'high' | 'elev' | 'watch';
export type ForecastClass = 'high' | 'medium' | 'low';

export interface HotspotPoint {
  lat: number;
  lon: number;
  frp: number;
  conf: number | string;
  sensor: SensorKind;
  sat: string;
  date?: string;
  time: string;
  dn: string;
  mun: string | null;
  uf: string | null;
}

export interface CandidateMun {
  id: string;
  name: string;
  uf: string;
  n: number;
  nV: number;
  nM: number;
  frpSum: number;
  frpMax: number;
  high: number;
  last: string;
  lastDate?: string;
  dn: string[];
  areaKm2?: number;
  geom?: number[][][] | number[][][][];
  poly?: number[][];
  score?: number;
  tier?: AlertTier;
}

export interface StateGeom {
  uf: string;
  /** MultiPolygon compacto IBGE: poligono → anel → [lon, lat] */
  g: number[][][] | number[][][][];
}

export interface DataMeta {
  kind?: string;
  generated?: string;
  window_hours?: number;
  sources?: Array<Record<string, unknown>>;
  latest_pass?: string;
}

export interface DataPayload {
  point_fields?: string[];
  points: HotspotPoint[] | unknown[][];
  cands: CandidateMun[];
  states?: StateGeom[];
  meta?: DataMeta;
}

export interface CalendarMonth {
  month: number; // 0-11
  label: string;
  hasData: boolean;
  hidden: boolean;
  color: string;
}

/** Exportado de calendar_brasil.csv (+ grid opcional). */
export interface HarmonizedCalendarRow {
  year: number;
  month: number;
  ym: string;
  value: number;
  origin?: string;
  mediana?: number | null;
  p10?: number | null;
  p90?: number | null;
  anomalia_pct?: number | null;
  percentil?: number | null;
}

export interface HarmonizedCalendarPayload {
  kind: 'harmonized-calendar';
  generated?: string;
  current_year?: number;
  current_month?: number;
  rows: HarmonizedCalendarRow[];
  /** year → month(1-12) → value */
  grid?: Record<string, Record<string, number>>;
}

/** Join por município IBGE (ou agregado Brasil com id "*"). */
export interface HarmonizedMunStats {
  value?: number | null;
  mediana?: number | null;
  anomalia_pct?: number | null;
  percentil?: number | null;
  frpHarm?: number | null;
  ym?: string;
}

export interface HarmonizedMunPayload {
  kind: 'harmonized-mun';
  generated?: string;
  byId: Record<string, HarmonizedMunStats>;
}

export interface ForecastModelMeta {
  name: string;
  train_years?: number[];
  roc_auc_temporal?: number;
  roc_auc_spatial?: number;
  base_rate?: number;
  data_until?: string;
  generated?: string;
  min_prob?: number;
}

export interface ForecastMeta {
  kind?: string;
  target: string;
  model?: ForecastModelMeta;
  generated?: string;
  live_generated?: string;
  active_counted?: boolean;
  history_years?: number[];
  n_years?: number;
  res?: number;
  rule?: Record<string, number>;
}

/** Compact cell: [cy, cx, cls, years, mean, active, prob|null] */
export type ForecastCell = [number, number, ForecastClass | string, number, number, number, number | null];

export interface ForecastMunicipality {
  id: string;
  name: string;
  uf: string;
  cls: ForecastClass | string;
  years: number;
  n_years: number;
  mean: number;
  active_cell: number;
  active_mun: number;
  prob: number | null;
}

export interface ForecastPayload {
  meta: ForecastMeta;
  cells: ForecastCell[];
  municipalities: ForecastMunicipality[];
}

export interface AlertDraft {
  level: 'extreme' | 'severe' | 'moderate';
  event: string;
  action: string;
  area: string;
  checks: {
    imagery: boolean;
    population: boolean;
    duplicate: boolean;
  };
  author: string;
  approver: string;
}

export interface AlertCase {
  munId: string;
  status: AlertStatus;
  draft: AlertDraft;
  sentAt?: string;
  cancelledAt?: string;
}

export interface ActivityEntry {
  id: string;
  at: string;
  kind: string;
  message: string;
  munId?: string;
}

export interface DayBucket {
  date: Date;
  key: string;
  viirs: number;
  modis: number;
}

export interface SelectionReport {
  center: { lat: number; lon: number };
  radiusKm: number;
  areaKm2: number;
  total: number;
  viirs: number;
  modis: number;
  high: number;
  density: number;
  perDay: number[];
  peak: string;
  lastDet: string;
}

export interface LayerState {
  source: SourceFilter;
  colorBy: ColorMode;
  confidence: ConfidenceLevel;
  burnEnabled: boolean;
  /** Contornos de UF (sem máscara de mundo / sem foco regional). */
  ibgeEnabled: boolean;
  offMonths: Record<number, boolean>;
  hoverMonth: number | null;
}
