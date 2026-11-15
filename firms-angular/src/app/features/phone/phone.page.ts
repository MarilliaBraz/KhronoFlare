import { Component, OnDestroy, OnInit, inject, signal } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { NtfyService } from '../../core/services/ntfy.service';

interface PhoneMsg {
  id: string;
  title: string;
  message: string;
  at: string;
}

@Component({
  selector: 'app-phone-page',
  standalone: true,
  imports: [RouterLink],
  templateUrl: './phone.page.html',
  styleUrl: './phone.page.scss',
})
export class PhonePage implements OnInit, OnDestroy {
  private readonly route = inject(ActivatedRoute);
  readonly ntfy = inject(NtfyService);

  readonly ready = signal(false);
  readonly active = signal<PhoneMsg | null>(null);
  readonly history = signal<PhoneMsg[]>([]);
  private es?: EventSource;
  private audio?: AudioContext;

  ngOnInit(): void {
    const t = this.route.snapshot.queryParamMap.get('t');
    if (t) {
      try {
        localStorage.setItem('hac-ntfy-topic', t);
      } catch {
        /* ignore */
      }
    }
  }

  ngOnDestroy(): void {
    this.es?.close();
  }

  start(): void {
    this.ready.set(true);
    try {
      this.audio = new AudioContext();
    } catch {
      /* ignore */
    }
    const topic = this.route.snapshot.queryParamMap.get('t') || this.ntfy.topic();
    this.es?.close();
    this.es = new EventSource(`https://ntfy.sh/${encodeURIComponent(topic)}/sse`);
    this.es.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data);
        if (!data?.title && !data?.message) return;
        const msg: PhoneMsg = {
          id: String(data.id ?? crypto.randomUUID()),
          title: data.title ?? 'Alert',
          message: data.message ?? '',
          at: new Date().toISOString(),
        };
        this.active.set(msg);
        this.history.update((h) => [msg, ...h].slice(0, 20));
        this.siren();
        try {
          navigator.vibrate?.([200, 100, 200, 100, 400]);
        } catch {
          /* ignore */
        }
      } catch {
        /* ignore */
      }
    };
  }

  dismiss(): void {
    this.active.set(null);
  }

  private siren(): void {
    if (!this.audio) return;
    const ctx = this.audio;
    const o = ctx.createOscillator();
    const g = ctx.createGain();
    o.type = 'sawtooth';
    o.frequency.value = 880;
    g.gain.value = 0.05;
    o.connect(g);
    g.connect(ctx.destination);
    o.start();
    setTimeout(() => {
      o.stop();
    }, 600);
  }
}
