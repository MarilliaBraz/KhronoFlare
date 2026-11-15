import { Injectable, signal } from '@angular/core';

const NTFY = 'https://ntfy.sh';
const STORE = 'hac-ntfy-topic';
const STORE_BASE = 'hac-phone-base';

export type NtfyKind = 'extreme' | 'severe' | 'cancel' | 'test';

const KIND: Record<NtfyKind, { label: string; tags: string[]; priority: number }> = {
  extreme: { label: 'Extreme alert', tags: ['rotating_light', 'extreme'], priority: 5 },
  severe: { label: 'Severe alert', tags: ['warning', 'severe'], priority: 4 },
  cancel: { label: 'Alert cancelled', tags: ['white_check_mark', 'cancel'], priority: 3 },
  test: { label: 'Test message', tags: ['test_tube', 'test'], priority: 3 },
};

function randomTopic(): string {
  const a = new Uint8Array(10);
  crypto.getRandomValues(a);
  return 'hac-' + Array.from(a, (b) => (b % 36).toString(36)).join('');
}

@Injectable({ providedIn: 'root' })
export class NtfyService {
  readonly topic = signal(this.loadTopic());
  readonly base = signal(this.loadBase());
  readonly enabled = signal(true);
  readonly status = signal('Nothing sent yet.');
  readonly lastError = signal<string | null>(null);

  private loadTopic(): string {
    try {
      let t = localStorage.getItem(STORE);
      if (!t) {
        t = randomTopic();
        localStorage.setItem(STORE, t);
      }
      return t;
    } catch {
      return randomTopic();
    }
  }

  private loadBase(): string {
    try {
      return localStorage.getItem(STORE_BASE) || '';
    } catch {
      return '';
    }
  }

  ntfyUrl(): string {
    return `${NTFY}/${encodeURIComponent(this.topic())}`;
  }

  phoneUrl(): string {
    const b = this.base();
    if (!b) return '';
    try {
      return new URL(`phone?t=${encodeURIComponent(this.topic())}`, b.endsWith('/') ? b : b + '/').href;
    } catch {
      return '';
    }
  }

  setBase(base: string): void {
    this.base.set(base);
    try {
      localStorage.setItem(STORE_BASE, base);
    } catch {
      /* ignore */
    }
  }

  async publish(kind: NtfyKind, place: string, message: string): Promise<boolean> {
    if (!this.enabled() && kind !== 'test') {
      this.status.set('Sending to phones is off.');
      return false;
    }
    const k = KIND[kind];
    this.status.set('Sending…');
    this.lastError.set(null);
    try {
      const r = await fetch(NTFY, {
        method: 'POST',
        body: JSON.stringify({
          topic: this.topic(),
          title: `SIMULATION · ${k.label} · ${place}`,
          message,
          priority: k.priority,
          tags: k.tags,
        }),
      });
      if (!r.ok) throw new Error('HTTP ' + r.status);
      this.status.set(`Sent ${kind} at ${new Date().toLocaleTimeString()}`);
      return true;
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      this.lastError.set(msg);
      this.status.set('Failed: ' + msg);
      return false;
    }
  }

  sendTest(): Promise<boolean> {
    return this.publish('test', 'Console', 'Test from FIRMS Angular (simulation)');
  }
}
