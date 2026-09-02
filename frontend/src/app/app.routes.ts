import { Routes } from '@angular/router';
import { authGuard } from './core/auth';

export const routes: Routes = [
  {
    path: 'login',
    loadComponent: () => import('./pages/login').then((m) => m.LoginPage),
  },
  {
    path: '',
    canActivate: [authGuard],
    children: [
      {
        path: '',
        pathMatch: 'full',
        loadComponent: () => import('./pages/home').then((m) => m.HomePage),
      },
      {
        path: 'upload',
        loadComponent: () => import('./pages/upload').then((m) => m.UploadPage),
      },
      {
        path: 'settings',
        loadComponent: () => import('./pages/settings').then((m) => m.SettingsPage),
      },
      {
        path: 'class/:name',
        loadComponent: () => import('./pages/class-view/class-view').then((m) => m.ClassViewPage),
      },
    ],
  },
  { path: '**', redirectTo: '' },
];
