import { Routes } from '@angular/router';
import { authGuard, guestGuard, moduleGuard } from './core/guards/auth.guard';
import { LoginComponent } from './auth/login/login.component';
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
import { LEGACY_ROOT_MODULE_CODE } from './plateforme/module-routing.contract';
import { StockDashboardComponent } from './stock-fournitures/stock-dashboard.component';
import { StockArticlesComponent } from './stock-fournitures/stock-articles.component';
import { StockArticleFicheComponent } from './stock-fournitures/stock-article-fiche.component';
import { StockMouvementsComponent } from './stock-fournitures/stock-mouvements.component';
import { StockDemandesComponent } from './stock-fournitures/stock-demandes.component';
import { StockRapportsComponent } from './stock-fournitures/stock-rapports.component';
import {
  StockAlertesComponent,
  StockEntreesComponent,
  StockEtatComponent,
  StockInventairesComponent,
  StockParametresComponent,
  StockSortiesComponent,
} from './stock-fournitures/stock-pages.component';
import { AchatsBonsComponent } from './achats-appro/achats-bons.component';
import {
  AchatsAlertesComponent,
  AchatsComparaisonsComponent,
  AchatsConsultationsComponent,
  AchatsDashboardComponent,
  AchatsDemandesComponent,
  AchatsDevisComponent,
  AchatsFacturesComponent,
  AchatsFournisseursComponent,
  AchatsLivraisonsComponent,
  AchatsPaiementsComponent,
  AchatsParametresComponent,
  AchatsRapportsComponent,
  AchatsReceptionsComponent,
} from './achats-appro/achats-pages.component';
import { NotesListComponent } from './notes-frais/notes-list.component';
import { ContratsListComponent } from './contrats-echeances/contrats-list.component';
import { ArchivesRegistreComponent } from './archives-mg/archives-registre.component';

/**
 * Contrat de routes (voir plateforme/module-routing.contract.ts) :
 * - Immobilisations = legacy-root (ShellComponent, paths inchangés).
 * - Modules MG / futurs = même ShellComponent + nav MODULE_SHELL_NAV, path préfixé.
 */
export const routes: Routes = [
  { path: 'login', component: LoginComponent, canActivate: [guestGuard] },
  { path: 'forgot-password', redirectTo: 'login', pathMatch: 'full' },
  { path: 'reset-password', redirectTo: 'login', pathMatch: 'full' },
  { path: '', pathMatch: 'full', redirectTo: 'accueil' },
  {
    path: 'stock-fournitures',
    component: ShellComponent,
    canActivate: [authGuard, moduleGuard('stock-fournitures')],
    children: [
      { path: '', pathMatch: 'full', redirectTo: 'dashboard' },
      { path: 'dashboard', component: StockDashboardComponent },
      { path: 'articles', component: StockArticlesComponent },
      { path: 'articles/:id', component: StockArticleFicheComponent },
      { path: 'stock', component: StockEtatComponent },
      { path: 'entrees', component: StockEntreesComponent },
      { path: 'sorties', component: StockSortiesComponent },
      { path: 'mouvements', component: StockMouvementsComponent },
      { path: 'journal', component: StockMouvementsComponent },
      { path: 'demandes', component: StockDemandesComponent },
      { path: 'demandes/nouvelle', component: StockDemandesComponent },
      { path: 'demandes/:id', component: StockDemandesComponent },
      { path: 'inventaires', component: StockInventairesComponent },
      { path: 'alertes', component: StockAlertesComponent },
      { path: 'rapports', component: StockRapportsComponent },
      { path: 'parametres', component: StockParametresComponent },
    ],
  },
  {
    path: 'achats-appro',
    component: ShellComponent,
    canActivate: [authGuard, moduleGuard('achats-appro')],
    children: [
      { path: '', pathMatch: 'full', redirectTo: 'dashboard' },
      { path: 'dashboard', component: AchatsDashboardComponent },
      { path: 'alertes', component: AchatsAlertesComponent },
      { path: 'demandes', component: AchatsDemandesComponent },
      { path: 'demandes/nouvelle', component: AchatsDemandesComponent },
      { path: 'demandes/:id', component: AchatsDemandesComponent },
      { path: 'fournisseurs', component: AchatsFournisseursComponent },
      { path: 'fournisseurs/:id', component: AchatsFournisseursComponent },
      { path: 'consultations', component: AchatsConsultationsComponent },
      { path: 'consultations/nouvelle', component: AchatsConsultationsComponent },
      { path: 'consultations/:id', component: AchatsConsultationsComponent },
      { path: 'devis', component: AchatsDevisComponent },
      { path: 'devis/nouveau', component: AchatsDevisComponent },
      { path: 'devis/:id', component: AchatsDevisComponent },
      { path: 'comparaisons', component: AchatsComparaisonsComponent },
      { path: 'comparaisons/nouvelle', component: AchatsComparaisonsComponent },
      { path: 'comparaisons/:id', component: AchatsComparaisonsComponent },
      { path: 'bons', component: AchatsBonsComponent },
      { path: 'nouveau', component: AchatsBonsComponent },
      { path: 'bons/:id', component: AchatsBonsComponent },
      { path: 'livraisons', component: AchatsLivraisonsComponent },
      { path: 'livraisons/nouvelle', component: AchatsLivraisonsComponent },
      { path: 'livraisons/:id', component: AchatsLivraisonsComponent },
      { path: 'receptions', component: AchatsReceptionsComponent },
      { path: 'receptions/nouvelle', component: AchatsReceptionsComponent },
      { path: 'receptions/:id', component: AchatsReceptionsComponent },
      { path: 'factures', component: AchatsFacturesComponent },
      { path: 'factures/nouvelle', component: AchatsFacturesComponent },
      { path: 'factures/:id', component: AchatsFacturesComponent },
      { path: 'paiements', component: AchatsPaiementsComponent },
      { path: 'paiements/nouveau', component: AchatsPaiementsComponent },
      { path: 'paiements/:id', component: AchatsPaiementsComponent },
      { path: 'rapports', component: AchatsRapportsComponent },
      { path: 'parametres', component: AchatsParametresComponent },
    ],
  },
  {
    path: 'notes-frais',
    component: ShellComponent,
    canActivate: [authGuard, moduleGuard('notes-frais')],
    children: [
      { path: '', pathMatch: 'full', redirectTo: 'notes' },
      { path: 'notes', component: NotesListComponent },
      { path: 'nouvelle', component: NotesListComponent },
      { path: 'notes/:id', component: NotesListComponent },
    ],
  },
  {
    path: 'contrats-echeances',
    component: ShellComponent,
    canActivate: [authGuard, moduleGuard('contrats-echeances')],
    children: [
      { path: '', pathMatch: 'full', redirectTo: 'liste' },
      { path: 'liste', component: ContratsListComponent },
      { path: 'alertes', component: ContratsListComponent },
      { path: 'nouveau', component: ContratsListComponent },
      { path: ':id', component: ContratsListComponent },
    ],
  },
  {
    path: 'archives-mg',
    component: ShellComponent,
    canActivate: [authGuard, moduleGuard('archives-mg')],
    children: [
      { path: '', pathMatch: 'full', redirectTo: 'registre' },
      { path: 'registre', component: ArchivesRegistreComponent },
    ],
  },
  ...PLATEFORME_ROUTES,
  {
    // Exception figée : module immobilisations aux URLs racine.
    path: '',
    component: ShellComponent,
    canActivate: [authGuard, moduleGuard(LEGACY_ROOT_MODULE_CODE)],
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
