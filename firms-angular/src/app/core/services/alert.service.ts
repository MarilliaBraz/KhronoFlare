import { Injectable, computed, inject, signal } from '@angular/core';
import {
  ActivityEntry,
  AlertCase,
  AlertDraft,
  AlertStatus,
  CandidateMun,
} from '../models';
import { HotspotDataService } from './hotspot-data.service';
import { NtfyService } from './ntfy.service';

function defaultDraft(c: CandidateMun): AlertDraft {
  return {
    level: c.tier === 'high' ? 'extreme' : c.tier === 'elev' ? 'severe' : 'moderate',
    event: 'Wildfire / hotspots',
    action: 'Monitor and prepare response',
    area: `${c.name}, ${c.uf}`,
    checks: { imagery: false, population: false, duplicate: false },
    author: '',
    approver: '',
  };
}

@Injectable({ providedIn: 'root' })
export class AlertService {
  private readonly data = inject(HotspotDataService);
  private readonly ntfy = inject(NtfyService);

  readonly cases = signal<Record<string, AlertCase>>({});
  readonly selectedId = signal<string | null>(null);
  readonly filter = signal<'all' | 'open' | 'active'>('all');
  readonly jurisdiction = signal<string>('ALL');
  readonly activity = signal<ActivityEntry[]>([]);
  readonly lastCap = signal<string>('');

  readonly selected = computed(() => {
    const id = this.selectedId();
    if (!id) return null;
    return this.data.candidates().find((c) => c.id === id) ?? null;
  });

  readonly selectedCase = computed(() => {
    const id = this.selectedId();
    if (!id) return null;
    return this.ensureCase(id);
  });

  readonly filtered = computed(() => {
    const uf = this.jurisdiction();
    const f = this.filter();
    return this.data.candidates().filter((c) => {
      if (uf !== 'ALL' && c.uf !== uf) return false;
      const st = this.getStatus(c.id);
      if (f === 'open') return st === 'new' || st === 'draft';
      if (f === 'active') return st === 'pending' || st === 'sent';
      return st !== 'dismissed';
    });
  });

  readonly ufs = computed(() => {
    const set = new Set(this.data.candidates().map((c) => c.uf));
    return ['ALL', ...Array.from(set).sort()];
  });

  getStatus(id: string): AlertStatus {
    return this.cases()[id]?.status ?? 'new';
  }

  ensureCase(id: string): AlertCase {
    const existing = this.cases()[id];
    if (existing) return existing;
    const c = this.data.candidates().find((x) => x.id === id);
    const created: AlertCase = {
      munId: id,
      status: 'new',
      draft: c ? defaultDraft(c) : defaultDraft({
        id, name: id, uf: '', n: 0, nV: 0, nM: 0, frpSum: 0, frpMax: 0, high: 0, last: '', dn: [],
      }),
    };
    this.cases.update((m) => ({ ...m, [id]: created }));
    return created;
  }

  select(id: string): void {
    this.selectedId.set(id);
    this.ensureCase(id);
  }

  updateDraft(partial: Partial<AlertDraft>): void {
    const id = this.selectedId();
    if (!id) return;
    this.cases.update((m) => {
      const cur = m[id] ?? this.ensureCase(id);
      return {
        ...m,
        [id]: { ...cur, draft: { ...cur.draft, ...partial, checks: { ...cur.draft.checks, ...(partial.checks ?? {}) } } },
      };
    });
  }

  private setStatus(id: string, status: AlertStatus, extra: Partial<AlertCase> = {}): void {
    this.cases.update((m) => {
      const cur = m[id] ?? this.ensureCase(id);
      return { ...m, [id]: { ...cur, ...extra, status } };
    });
  }

  private log(kind: string, message: string, munId?: string): void {
    this.activity.update((a) => [
      {
        id: crypto.randomUUID(),
        at: new Date().toISOString(),
        kind,
        message,
        munId,
      },
      ...a,
    ]);
  }

  startDraft(): void {
    const id = this.selectedId();
    if (!id) return;
    this.setStatus(id, 'draft');
    this.log('draft', 'Draft started', id);
  }

  submit(): void {
    const id = this.selectedId();
    if (!id) return;
    const c = this.ensureCase(id);
    if (!c.draft.author.trim()) return;
    this.setStatus(id, 'pending');
    this.log('pending', `Submitted by ${c.draft.author}`, id);
  }

  approve(): void {
    const id = this.selectedId();
    if (!id) return;
    const c = this.ensureCase(id);
    const mun = this.selected();
    if (!c.draft.approver.trim() || c.draft.approver === c.draft.author) return;
    const checks = c.draft.checks;
    if (!checks.imagery || !checks.population || !checks.duplicate) return;
    this.setStatus(id, 'sent', { sentAt: new Date().toISOString() });
    const place = mun ? `${mun.name}, ${mun.uf}` : id;
    const msg = `${c.draft.level.toUpperCase()}: ${c.draft.event}. ${c.draft.action}. Area: ${c.draft.area}`;
    this.lastCap.set(this.buildCap(mun, c, 'Alert'));
    this.log('sent', `Approved by ${c.draft.approver}`, id);
    void this.ntfy.publish(c.draft.level === 'extreme' ? 'extreme' : 'severe', place, msg);
  }

  cancel(): void {
    const id = this.selectedId();
    if (!id) return;
    const mun = this.selected();
    this.setStatus(id, 'cancelled', { cancelledAt: new Date().toISOString() });
    this.lastCap.set(this.buildCap(mun, this.ensureCase(id), 'Cancel'));
    this.log('cancel', 'Alert cancelled', id);
    void this.ntfy.publish('cancel', mun ? `${mun.name}, ${mun.uf}` : id, 'Alert cancelled (simulation)');
  }

  dismiss(): void {
    const id = this.selectedId();
    if (!id) return;
    this.setStatus(id, 'dismissed');
    this.log('dismiss', 'Case dismissed', id);
  }

  returnToDraft(): void {
    const id = this.selectedId();
    if (!id) return;
    this.setStatus(id, 'draft');
    this.log('return', 'Returned to draft', id);
  }

  buildCap(mun: CandidateMun | null, c: AlertCase, msgType: string): string {
    const now = new Date().toISOString();
    const id = `FIRMS-SIM-${c.munId}-${Date.now()}`;
    return `<?xml version="1.0" encoding="UTF-8"?>
<alert xmlns="urn:oasis:names:tc:emergency:cap:1.2">
  <identifier>${id}</identifier>
  <sender>firms-angular-simulation</sender>
  <sent>${now}</sent>
  <status>Actual</status>
  <msgType>${msgType}</msgType>
  <scope>Public</scope>
  <info>
    <category>Fire</category>
    <event>${escapeXml(c.draft.event)}</event>
    <urgency>Immediate</urgency>
    <severity>${c.draft.level === 'extreme' ? 'Extreme' : c.draft.level === 'severe' ? 'Severe' : 'Moderate'}</severity>
    <certainty>Observed</certainty>
    <senderName>Hotspot Alert Console (simulation)</senderName>
    <headline>${escapeXml(c.draft.level.toUpperCase() + ' — ' + (mun?.name ?? c.munId))}</headline>
    <description>${escapeXml(c.draft.action)}</description>
    <area>
      <areaDesc>${escapeXml(c.draft.area)}</areaDesc>
    </area>
  </info>
</alert>`;
  }
}

function escapeXml(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
