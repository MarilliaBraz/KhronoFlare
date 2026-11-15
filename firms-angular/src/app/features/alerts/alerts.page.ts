import { DatePipe, DecimalPipe } from '@angular/common';
import { Component, OnInit, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { HotspotDataService } from '../../core/services/hotspot-data.service';
import { AlertService } from '../../core/services/alert.service';
import { I18nService } from '../../core/services/i18n.service';
import { NtfyService } from '../../core/services/ntfy.service';
import { CandidateMun } from '../../core/models';

@Component({
  selector: 'app-alerts-page',
  standalone: true,
  imports: [FormsModule, RouterLink, DecimalPipe, DatePipe],
  templateUrl: './alerts.page.html',
  styleUrl: './alerts.page.scss',
})
export class AlertsPage implements OnInit {
  readonly data = inject(HotspotDataService);
  readonly alerts = inject(AlertService);
  readonly i18n = inject(I18nService);
  readonly ntfy = inject(NtfyService);

  ngOnInit(): void {
    if (!this.data.candidates().length) this.data.load();
  }

  t(key: string, vars?: Record<string, string | number>): string {
    return this.i18n.t(key, vars);
  }

  private locale(): string {
    return this.i18n.lang() === 'pt' ? 'pt-BR' : 'en-US';
  }

  /** "Nov 1–13, 2026" / "1–13 de nov. de 2026", a partir do window do harmonized_mun.json. */
  harmWindow(): string {
    const w = this.data.harmonizedMun()?.window;
    if (!w?.years) return '';
    const year = w.years[1];
    const month = new Intl.DateTimeFormat(this.locale(), {
      month: 'short',
      timeZone: 'UTC',
    }).format(new Date(Date.UTC(year, w.month - 1, 15)));
    const days = `${w.day_start}–${w.day_end}`;
    return this.i18n.lang() === 'pt'
      ? `${days} de ${month} de ${year}`
      : `${month} ${days}, ${year}`;
  }

  /** Anos de referência da mediana: todos menos o corrente. */
  harmRefYears(): string {
    const y = this.data.harmonizedMun()?.window?.years;
    return y ? `${y[0]}–${y[1] - 1}` : '';
  }

  statusOf(c: CandidateMun): string {
    return this.alerts.getStatus(c.id);
  }

  fmtHarm(id: string, field: 'frp' | 'anom'): string {
    const h = this.data.munHarm(id);
    if (!h) return '—';
    if (field === 'frp') {
      const v = h.frpHarm ?? h.value;
      if (v == null) return '—';
      return `${Number(v).toLocaleString(this.locale(), { maximumFractionDigits: 0 })} MW`;
    }
    const a = h.anomalia_pct;
    if (a == null) return '—';
    const sign = a > 0 ? '+' : '';
    return `${sign}${a.toFixed(0)}%`;
  }

  setCheck(key: 'imagery' | 'population' | 'duplicate', value: boolean): void {
    const ac = this.alerts.selectedCase();
    if (!ac) return;
    this.alerts.updateDraft({ checks: { ...ac.draft.checks, [key]: value } });
  }

  copyCap(): void {
    const x = this.alerts.lastCap();
    if (!x) return;
    void navigator.clipboard?.writeText(x);
  }
}
