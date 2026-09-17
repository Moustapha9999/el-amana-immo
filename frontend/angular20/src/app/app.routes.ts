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
import { EcritureDetailComponent } from './ecritures/ecriture-detail.component';
import { RapportsComponent } from './rapports/rapports.component';
import { AuditComponent } from './audit/audit.component';
import { CessionsComponent } from './cessions/cessions.component';
import { CessionDetailComponent } from './cessions/cession-detail.component';
import { RebutsComponent } from './rebuts/rebuts.component';
import { RebutDetailComponent } from './rebuts/rebut-detail.component';
import { UtilisateursComponent } from './utilisateurs/utilisateurs.component';
import { AmortissementsComponent } from './amortissements/amortissements.component';
import { CalculAmortissementsComponent } from './amortissements/calcul-amortissements.component';
import { AmortissementDetailComponent } from './amortissements/amortissement-detail.component';
import { RecapAmortissementComponent } from './recap-amortissement/recap-amortissement.component';
import { RecapImmobilisationsComponent } from './recap-immobilisations/recap-immobilisations.component';
import { AmortissementsAgenceComponent } from './amortissements-agence/amortissements-agence.component';
import { ComptesComponent } from './comptes/comptes.component';
import { Soldes14868Component } from './comptes/soldes-148-68.component';
import { PiecesComptablesComponent } from './pieces-comptables/pieces-comptables.component';
import { ReevaluationsComponent } from './reevaluations/reevaluations.component';
import { ReevaluationDetailComponent } from './reevaluations/reevaluation-detail.component';
import { ParametresComponent } from './parametres/parametres.component';
import { NotificationsComponent } from './notifications/notifications.component';
import { ArchivesComponent } from './archives/archives.component';
import { ArchiveDetailComponent } from './archives/archive-detail.component';
import { ArchiveNatureComponent } from './archives/archive-nature.component';
import { PLATEFORME_ROUTES } from './plateforme/plateforme.routes';

export const routes: Routes = [
  { path: 'login', component: LoginComponent, canActivate: [guestGuard] },
  { path: 'forgot-password', component: ForgotPasswordComponent, canActivate: [guestGuard] },
  { path: 'reset-password', component: ResetPasswordComponent, canActivate: [guestGuard] },
  { path: '', pathMatch: 'full', redirectTo: 'accueil' },
  ...PLATEFORME_ROUTES,
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
      { path: 'amortissements/calculer', component: CalculAmortissementsComponent },
      { path: 'amortissements/:id', component: AmortissementDetailComponent },
      { path: 'recap-amortissement', component: RecapAmortissementComponent },
      { path: 'recap-immobilisations', component: RecapImmobilisationsComponent },
      { path: 'amortissements-agence', component: AmortissementsAgenceComponent },
      { path: 'comptes/soldes-148-68', component: Soldes14868Component },
      { path: 'comptes', component: ComptesComponent },
      { path: 'archives', component: ArchivesComponent },
      { path: 'archives/:annee', component: ArchiveDetailComponent },
      { path: 'archives/:annee/:natureCode', component: ArchiveNatureComponent },
      { path: 'pieces-comptables', component: PiecesComptablesComponent },
      { path: 'ecritures', component: EcrituresComponent },
      { path: 'ecritures/:id', component: EcritureDetailComponent },
      { path: 'cessions', component: CessionsComponent },
      { path: 'cessions/:id', component: CessionDetailComponent },
      { path: 'rebuts', component: RebutsComponent },
      { path: 'rebuts/:id', component: RebutDetailComponent },
      { path: 'reevaluations', component: ReevaluationsComponent },
      { path: 'reevaluations/:id', component: ReevaluationDetailComponent },
      { path: 'notifications', component: NotificationsComponent },
      { path: 'rapports', component: RapportsComponent },
      { path: 'utilisateurs', component: UtilisateursComponent },
      { path: 'audit', component: AuditComponent },
      { path: 'parametres', component: ParametresComponent },
    ],
  },
  { path: '**', redirectTo: 'accueil' },
];
