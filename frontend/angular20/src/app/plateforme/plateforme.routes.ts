import { Routes } from '@angular/router';
import { authGuard, coreAdminGuard } from '../core/guards/auth.guard';
import { AccueilComponent } from './accueil/accueil.component';
import { ComptabiliteComponent } from './comptabilite/comptabilite.component';
import { CoreAdminActivityComponent } from './core-admin/core-admin-activity.component';
import { CoreAdminAlertsComponent } from './core-admin/core-admin-alerts.component';
import { CoreAdminAuditComponent } from './core-admin/core-admin-audit.component';
import { CoreAdminDashboardComponent } from './core-admin/core-admin-dashboard.component';
import { CoreAdminDepartmentFicheComponent } from './core-admin/core-admin-department-fiche.component';
import { CoreAdminDepartmentsComponent } from './core-admin/core-admin-departments.component';
import { CoreAdminGedComponent } from './core-admin/core-admin-ged.component';
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
      { path: 'departments', component: CoreAdminDepartmentsComponent },
      { path: 'departments/nouveau', component: CoreAdminDepartmentFicheComponent },
      { path: 'departments/:id/modifier', component: CoreAdminDepartmentFicheComponent },
      { path: 'departments/:id', component: CoreAdminDepartmentFicheComponent },
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
      { path: 'activity', component: CoreAdminActivityComponent },
      { path: 'alerts', component: CoreAdminAlertsComponent },
      { path: 'notifications', component: CoreAdminNotificationsComponent },
      { path: 'ged', component: CoreAdminGedComponent },
      { path: 'general', component: CoreAdminGeneralComponent },
      { path: 'security', component: CoreAdminSecurityComponent },
      { path: 'maintenance', component: CoreAdminMaintenanceComponent },
      { path: '**', redirectTo: '/admin/dashboard' },
    ],
  },
];
