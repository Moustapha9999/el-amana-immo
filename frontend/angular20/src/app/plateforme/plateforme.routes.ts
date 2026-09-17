import { Routes } from '@angular/router';
import { authGuard, coreAdminGuard } from '../core/guards/auth.guard';
import { AccueilComponent } from './accueil/accueil.component';
import { ComptabiliteComponent } from './comptabilite/comptabilite.component';
import { CoreAdminDashboardComponent } from './core-admin/core-admin-dashboard.component';
import { CoreAdminLayoutComponent } from './core-admin/core-admin-layout.component';
import { CoreAdminUserFicheComponent } from './core-admin/core-admin-user-fiche.component';
import { CoreAdminUsersComponent } from './core-admin/core-admin-users.component';
import { ModuleAccesComponent } from './module-acces/module-acces.component';

export const PLATEFORME_ROUTES: Routes = [
  { path: 'accueil', component: AccueilComponent, canActivate: [authGuard] },
  { path: 'comptabilite', component: ComptabiliteComponent, canActivate: [authGuard] },
  { path: 'modules/:moduleCode/acces', component: ModuleAccesComponent, canActivate: [authGuard] },
  {
    path: 'admin',
    component: CoreAdminLayoutComponent,
    canActivate: [authGuard, coreAdminGuard],
    children: [
      { path: '', pathMatch: 'full', redirectTo: 'dashboard' },
      { path: 'dashboard', component: CoreAdminDashboardComponent },
      { path: 'users', component: CoreAdminUsersComponent },
      { path: 'users/nouveau', component: CoreAdminUserFicheComponent },
      { path: 'users/:id/modifier', component: CoreAdminUserFicheComponent },
      { path: 'users/:id', component: CoreAdminUserFicheComponent },
      { path: '**', redirectTo: '/admin/dashboard' },
    ],
  },
];
