import { Injectable, computed, signal } from '@angular/core';
import { Lang, MESSAGES } from '../i18n/messages';

@Injectable({ providedIn: 'root' })
export class I18nService {
  readonly lang = signal<Lang>(
    (typeof localStorage !== 'undefined' && (localStorage.getItem('firms-lang') as Lang)) || 'en',
  );

  readonly dict = computed(() => MESSAGES[this.lang()]);

  t(key: string, vars: Record<string, string | number> = {}): string {
    let s = this.dict()[key] ?? MESSAGES.en[key] ?? key;
    for (const [k, v] of Object.entries(vars)) {
      s = s.replace(`{${k}}`, String(v));
    }
    return s;
  }

  setLang(lang: Lang): void {
    this.lang.set(lang);
    try {
      localStorage.setItem('firms-lang', lang);
    } catch {
      /* ignore */
    }
  }
}
