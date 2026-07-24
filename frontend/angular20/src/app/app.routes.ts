import { Routes } from '@angular/router';
import { authGuard, guestGuard } from './core/guards/auth.guard';
import { LoginComponent } from './auth/login/login.component';
import { ForgotPasswordComponent } from './auth/forgot-password/forgot-password.component';
import { ResetPasswordComponent } from './auth/reset-password/reset-password.component';
import { ShellComponent } from './layout/shell/shell.component';
import { DashboardComponent } from './dashboard/dashboard.component';
import { ImmobilisationsListComponent } from './immobilisations/immobilisations-list.component';
import { ImmobilisationFormComponent } from './immobilisations/immobilisation-form.component';
import { InventaireComponent } from './inventaire/inventaire.component';
import { EcrituresComponent } from './ecritures/ecritures.component';
import { RapportsComponent } from './rapports/rapports.component';
import { AuditComponent } from './audit/audit.component';
import { CessionsComponent } from './cessions/cessions.component';
import { RebutsComponent } from './rebuts/rebuts.component';
import { UtilisateursComponent } from './utilisateurs/utilisateurs.component';
import { AmortissementsComponent } from './amortissements/amortissements.component';
import { ReevaluationsComponent } from './reevaluations/reevaluations.component';
import { ParametresComponent } from './parametres/parametres.component';
import { NotificationsComponent } from './notifications/notifications.component';

export const routes: Routes = [
  { path: 'login', component: LoginComponent, canActivate: [guestGuard] },
  { path: 'forgot-password', component: ForgotPasswordComponent, canActivate: [guestGuard] },
  { path: 'reset-password', component: ResetPasswordComponent, canActivate: [guestGuard] },
  {
    path: '',
    component: ShellComponent,
    canActivate: [authGuard],
    children: [
      { path: '', pathMatch: 'full', redirectTo: 'dashboard' },
      { path: 'dashboard', component: DashboardComponent },
      { path: 'immobilisations', component: ImmobilisationsListComponent },
      { path: 'immobilisations/nouveau', component: ImmobilisationFormComponent },
      { path: 'immobilisations/:id/:section', component: ImmobilisationFormComponent },
      { path: 'immobilisations/:id', component: ImmobilisationFormComponent },
      { path: 'inventaire', component: InventaireComponent },
      { path: 'amortissements', component: AmortissementsComponent },
      { path: 'ecritures', component: EcrituresComponent },
      { path: 'cessions', component: CessionsComponent },
      { path: 'rebuts', component: RebutsComponent },
      { path: 'reevaluations', component: ReevaluationsComponent },
      { path: 'notifications', component: NotificationsComponent },
      { path: 'rapports', component: RapportsComponent },
      { path: 'utilisateurs', component: UtilisateursComponent },
      { path: 'audit', component: AuditComponent },
      { path: 'parametres', component: ParametresComponent },
    ],
  },
  { path: '**', redirectTo: 'dashboard' },
];
