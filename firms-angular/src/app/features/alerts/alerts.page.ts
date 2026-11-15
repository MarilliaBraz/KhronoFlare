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

  t(key: string): string {
    return this.i18n.t(key);
  }

  statusOf(c: CandidateMun): string {
    return this.alerts.getStatus(c.id);
  }

  fmtHarm(id: string, field: 'frp' | 'anom'): string {
    const h = this.data.munHarm(id);
    if (!h) return '—';
    if (field === 'frp') {
      const v = h.frpHarm ?? h.value;
      return v == null ? '—' : Number(v).toFixed(1);
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
