import { Routes } from '@angular/router';
import { authGuard, coreAdminGuard } from '../core/guards/auth.guard';
import { AccueilComponent } from './accueil/accueil.component';
import { espaceHubCanMatch } from './espace-hub.guard';
import { EspaceHubComponent } from './espace-hub/espace-hub.component';
import { CoreAdminActivityComponent } from './core-admin/core-admin-activity.component';
import { CoreAdminAlertsComponent } from './core-admin/core-admin-alerts.component';
import { CoreAdminAuditComponent } from './core-admin/core-admin-audit.component';
import {
  CoreAdminModuleStatesComponent,
  CoreAdminSupervisionComponent,
  CoreAdminVersionsComponent,
} from './core-admin/core-admin-control.component';
import { CoreAdminDashboardComponent } from './core-admin/core-admin-dashboard.component';
import { CoreAdminErrorsComponent } from './core-admin/core-admin-errors.component';
import { CoreAdminDepartmentFicheComponent } from './core-admin/core-admin-department-fiche.component';
import { CoreAdminDepartmentsComponent } from './core-admin/core-admin-departments.component';
import { CoreAdminGedComponent } from './core-admin/core-admin-ged.component';
import {
  CoreAdminGedAuditComponent,
  CoreAdminGedDashboardComponent,
  CoreAdminGedDossiersComponent,
  CoreAdminGedMissingComponent,
  CoreAdminGedOcrComponent,
  CoreAdminGedSearchComponent,
  CoreAdminGedSettingsComponent,
  CoreAdminGedStorageComponent,
  CoreAdminGedTrashComponent,
} from './core-admin/core-admin-ged-center.component';
import { CoreAdminLayoutComponent } from './core-admin/core-admin-layout.component';
import { CoreAdminMatrixComponent } from './core-admin/core-admin-matrix.component';
import { CoreAdminModuleFicheComponent } from './core-admin/core-admin-module-fiche.component';
import { CoreAdminModulesComponent } from './core-admin/core-admin-modules.component';
import { CoreAdminNotificationsComponent } from './core-admin/core-admin-notifications.component';
import { CoreAdminPermissionFicheComponent } from './core-admin/core-admin-permission-fiche.component';
import { CoreAdminPermissionsComponent } from './core-admin/core-admin-permissions.component';
import { CoreAdminRoleFicheComponent } from './core-admin/core-admin-role-fiche.component';
import { CoreAdminRolesComponent } from './core-admin/core-admin-roles.component';
import { CoreAdminSessionsComponent } from './core-admin/core-admin-sessions.component';
import {
  CoreAdminGeneralComponent,
  CoreAdminMaintenanceComponent,
  CoreAdminSecurityComponent,
} from './core-admin/core-admin-settings.component';
import { CoreAdminUserFicheComponent } from './core-admin/core-admin-user-fiche.component';
import { CoreAdminUsersComponent } from './core-admin/core-admin-users.component';
import { ModuleAccesComponent } from './module-acces/module-acces.component';
import { CoreAdminDemandesComponent } from './core-admin/core-admin-demandes.component';

export const PLATEFORME_ROUTES: Routes = [
  { path: 'accueil', component: AccueilComponent, canActivate: [authGuard] },
  {
    path: 'comptabilite',
    component: EspaceHubComponent,
    canActivate: [authGuard],
    data: { espaceCode: 'comptabilite' },
  },
  {
    path: 'moyens-generaux',
    component: EspaceHubComponent,
    canActivate: [authGuard],
    data: { espaceCode: 'moyens-generaux' },
  },
  {
    path: 'archive-generale',
    component: EspaceHubComponent,
    canActivate: [authGuard],
    data: { espaceCode: 'archives' },
  },
  { path: 'employe', redirectTo: 'accueil', pathMatch: 'full' },
  {
    path: 'credit',
    component: EspaceHubComponent,
    canActivate: [authGuard],
    data: { espaceCode: 'credit' },
  },
  {
    path: 'rh',
    component: EspaceHubComponent,
    canActivate: [authGuard],
    data: { espaceCode: 'rh' },
  },
  {
    path: 'informatique',
    component: EspaceHubComponent,
    canActivate: [authGuard],
    data: { espaceCode: 'informatique' },
  },
  {
    path: 'audit-controle-conformite',
    component: EspaceHubComponent,
    canActivate: [authGuard],
    data: { espaceCode: 'audit-controle-conformite' },
  },
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
      { path: 'departments', component: CoreAdminDepartmentsComponent },
      { path: 'departments/nouveau', component: CoreAdminDepartmentFicheComponent },
      { path: 'departments/:id/modifier', component: CoreAdminDepartmentFicheComponent },
      { path: 'departments/:id', component: CoreAdminDepartmentFicheComponent },
      { path: 'demandes', component: CoreAdminDemandesComponent },
      { path: 'modules', component: CoreAdminModulesComponent },
      { path: 'modules/nouveau', component: CoreAdminModuleFicheComponent },
      { path: 'modules/:id/modifier', component: CoreAdminModuleFicheComponent },
      { path: 'modules/:id', component: CoreAdminModuleFicheComponent },
      { path: 'roles', component: CoreAdminRolesComponent },
      { path: 'roles/nouveau', component: CoreAdminRoleFicheComponent },
      { path: 'roles/:id/modifier', component: CoreAdminRoleFicheComponent },
      { path: 'roles/:id', component: CoreAdminRoleFicheComponent },
      { path: 'permissions', component: CoreAdminPermissionsComponent },
      { path: 'permissions/nouveau', component: CoreAdminPermissionFicheComponent },
      { path: 'permissions/:id/modifier', component: CoreAdminPermissionFicheComponent },
      { path: 'permissions/:id', component: CoreAdminPermissionFicheComponent },
      { path: 'matrix', component: CoreAdminMatrixComponent },
      { path: 'sessions', component: CoreAdminSessionsComponent },
      { path: 'audit', component: CoreAdminAuditComponent },
      { path: 'erreurs', component: CoreAdminErrorsComponent },
      { path: 'activity', component: CoreAdminActivityComponent },
      { path: 'alerts', component: CoreAdminAlertsComponent },
      { path: 'notifications', component: CoreAdminNotificationsComponent },
      { path: 'ged', component: CoreAdminGedDashboardComponent },
      { path: 'ged/documents', component: CoreAdminGedComponent },
      { path: 'ged/dossiers', component: CoreAdminGedDossiersComponent },
      { path: 'ged/ocr', component: CoreAdminGedOcrComponent },
      { path: 'ged/recherche', component: CoreAdminGedSearchComponent },
      { path: 'ged/stockage', component: CoreAdminGedStorageComponent },
      { path: 'ged/manquants', component: CoreAdminGedMissingComponent },
      { path: 'ged/corbeille', component: CoreAdminGedTrashComponent },
      { path: 'ged/audit', component: CoreAdminGedAuditComponent },
      { path: 'ged/parametres', component: CoreAdminGedSettingsComponent },
      { path: 'general', component: CoreAdminGeneralComponent },
      { path: 'security', component: CoreAdminSecurityComponent },
      { path: 'maintenance', component: CoreAdminMaintenanceComponent },
      {
        path: 'core-query',
        loadComponent: () => import('./core-admin/core-admin-query.component').then((m) => m.CoreAdminQueryAssistantComponent),
      },
      {
        path: 'core-query/builder',
        loadComponent: () =>
          import('./core-admin/core-admin-query-builder.component').then((m) => m.CoreAdminQueryBuilderComponent),
      },
      {
        path: 'core-query/sql',
        loadComponent: () => import('./core-admin/core-admin-query.component').then((m) => m.CoreAdminQuerySqlComponent),
      },
      {
        path: 'core-query/favoris',
        loadComponent: () =>
          import('./core-admin/core-admin-query-history.component').then((m) => m.CoreAdminQueryFavoritesComponent),
      },
      {
        path: 'core-query/historique',
        loadComponent: () =>
          import('./core-admin/core-admin-query-history.component').then((m) => m.CoreAdminQueryHistoryComponent),
      },
      {
        path: 'sauvegardes',
        loadComponent: () =>
          import('./core-admin/core-admin-sauvegardes.component').then((m) => m.CoreAdminSauvegardesOverviewComponent),
      },
      {
        path: 'sauvegardes/sauvegarde',
        loadComponent: () =>
          import('./core-admin/core-admin-sauvegardes.component').then((m) => m.CoreAdminSauvegardesBackupComponent),
      },
      {
        path: 'sauvegardes/recovery',
        loadComponent: () =>
          import('./core-admin/core-admin-sauvegardes.component').then((m) => m.CoreAdminSauvegardesRecoveryComponent),
      },
      {
        path: 'sauvegardes/historique',
        loadComponent: () =>
          import('./core-admin/core-admin-sauvegardes.component').then((m) => m.CoreAdminSauvegardesHistoryComponent),
      },
      { path: 'backups', pathMatch: 'full', redirectTo: 'sauvegardes' },
      { path: 'recovery', pathMatch: 'full', redirectTo: 'sauvegardes/recovery' },
      { path: 'supervision', component: CoreAdminSupervisionComponent },
      { path: 'module-states', component: CoreAdminModuleStatesComponent },
      { path: 'versions', component: CoreAdminVersionsComponent },
      { path: '**', redirectTo: '/admin/dashboard' },
    ],
  },
  // Après admin/modules : hub pour tout département créé en CORE ADMIN (route = /{code}).
  // canMatch refuse les segments Immobilisations (dashboard, …) → shell legacy-root.
  {
    path: ':espaceCode',
    component: EspaceHubComponent,
    canMatch: [espaceHubCanMatch],
    canActivate: [authGuard],
  },
];
