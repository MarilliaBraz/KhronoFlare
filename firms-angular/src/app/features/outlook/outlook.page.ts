import { DecimalPipe } from '@angular/common';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { HotspotDataService } from '../../core/services/hotspot-data.service';
import { I18nService } from '../../core/services/i18n.service';
import { ForecastMunicipality } from '../../core/models';

@Component({
  selector: 'app-outlook-page',
  standalone: true,
  imports: [FormsModule, RouterLink, DecimalPipe],
  templateUrl: './outlook.page.html',
  styleUrl: './outlook.page.scss',
})
export class OutlookPage implements OnInit {
  readonly data = inject(HotspotDataService);
  readonly i18n = inject(I18nService);

  readonly uf = signal('ALL');
  readonly cls = signal<'all' | 'high' | 'medium'>('all');
  readonly limit = signal(40);

  readonly ufs = computed(() => {
    const f = this.data.forecast();
    if (!f) return ['ALL'];
    return ['ALL', ...Array.from(new Set(f.municipalities.map((m) => m.uf))).sort()];
  });

  readonly rows = computed(() => {
    const f = this.data.forecast();
    if (!f) return [] as ForecastMunicipality[];
    return f.municipalities
      .filter((m) => (this.uf() === 'ALL' || m.uf === this.uf()) && (this.cls() === 'all' || m.cls === this.cls()))
      .sort((a, b) => (b.prob ?? 0) - (a.prob ?? 0) || b.mean - a.mean)
      .slice(0, this.limit());
  });

  readonly cellStats = computed(() => {
    const f = this.data.forecast();
    if (!f) return { high: 0, medium: 0, low: 0 };
    let high = 0;
    let medium = 0;
    let low = 0;
    for (const c of f.cells) {
      if (c[2] === 'high') high++;
      else if (c[2] === 'medium') medium++;
      else low++;
    }
    return { high, medium, low };
  });

  ngOnInit(): void {
    if (!this.data.forecast()) this.data.load();
  }

  t(key: string): string {
    return this.i18n.t(key);
  }

  showMore(): void {
    this.limit.update((n) => n + 40);
  }

  exportCsv(): void {
    const f = this.data.forecast();
    if (!f) return;
    const lines = ['id,name,uf,cls,mean,prob,active_mun'];
    for (const m of f.municipalities) {
      if (this.uf() !== 'ALL' && m.uf !== this.uf()) continue;
      if (this.cls() !== 'all' && m.cls !== this.cls()) continue;
      lines.push([m.id, JSON.stringify(m.name), m.uf, m.cls, m.mean, m.prob ?? '', m.active_mun].join(','));
    }
    const blob = new Blob([lines.join('\n')], { type: 'text/csv' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `outlook-${f.meta.target}.csv`;
    a.click();
    URL.revokeObjectURL(a.href);
  }
}
