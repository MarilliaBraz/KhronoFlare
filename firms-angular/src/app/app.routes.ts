import { Routes } from '@angular/router';
import { ExplorerPage } from './features/explorer/explorer.page';
import { AlertsPage } from './features/alerts/alerts.page';
import { PhonePage } from './features/phone/phone.page';
import { OutlookPage } from './features/outlook/outlook.page';

export const routes: Routes = [
  { path: '', component: ExplorerPage },
  { path: 'alerts', component: AlertsPage },
  { path: 'phone', component: PhonePage },
  { path: 'outlook', component: OutlookPage },
  { path: '**', redirectTo: '' },
];
