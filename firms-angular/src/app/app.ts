import { Component, OnInit, inject } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { HotspotDataService } from './core/services/hotspot-data.service';

@Component({
  imports: [RouterOutlet],
  selector: 'app-root',
  styleUrl: './app.scss',
  template: `<router-outlet />`,
})
export class App implements OnInit {
  private readonly data = inject(HotspotDataService);

  ngOnInit(): void {
    this.data.load();
  }
}
