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
        loadComponent: () =>
          import('./pages/leagues-home').then((m) => m.LeaguesHomePage),
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
        path: 'league/:id',
        loadComponent: () =>
          import('./pages/league-shell').then((m) => m.LeagueShellPage),
        children: [
          {
            path: '',
            pathMatch: 'full',
            loadComponent: () =>
              import('./pages/league-view/league-view').then((m) => m.LeagueViewPage),
          },
          {
            path: 'system',
            loadComponent: () =>
              import('./pages/system-rankings/system-rankings').then(
                (m) => m.SystemRankingsPage,
              ),
          },
          {
            path: 'classes',
            loadComponent: () =>
              import('./pages/league-classes').then((m) => m.LeagueClassesPage),
          },
        ],
      },
      {
        path: 'class/:name',
        loadComponent: () =>
          import('./pages/class-view/class-view').then((m) => m.ClassViewPage),
      },
    ],
  },
  { path: '**', redirectTo: '' },
];
