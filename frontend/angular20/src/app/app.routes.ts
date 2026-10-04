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
import { AchatsDemandesComponent } from './achats-appro/achats-demandes.component';
import { AchatsFournisseursComponent } from './achats-appro/achats-fournisseurs.component';
import { AchatsRapportsComponent } from './achats-appro/achats-rapports.component';
import { AchatsRapportViewerComponent } from './achats-appro/achats-rapport-viewer.component';
import {
  AchatsAlertesComponent,
  AchatsDashboardComponent,
  AchatsParametresComponent,
} from './achats-appro/achats-pages.component';
import { NotesListComponent } from './notes-frais/notes-list.component';
import { NotesDashboardComponent } from './notes-frais/notes-dashboard.component';
import { NotesRapportsComponent } from './notes-frais/notes-rapports.component';
import { NotesPaiementsComponent } from './notes-frais/notes-paiements.component';
import { NotesParametresComponent } from './notes-frais/notes-parametres.component';
import { ContratsDashboardComponent } from './contrats-echeances/contrats-dashboard.component';
import { ContratsListComponent } from './contrats-echeances/contrats-list.component';
import { ContratsFicheComponent } from './contrats-echeances/contrats-fiche.component';
import { withUnsavedChangesGuard } from './core/feedback/unsaved-changes.guard';
import { ContratsParametresComponent } from './contrats-echeances/contrats-parametres.component';
import { ContratsRapportsComponent } from './contrats-echeances/contrats-rapports.component';
import {
  DmgBatchesComponent,
  DmgDashboardComponent,
  DmgInboxComponent,
} from './demandes-mg/demandes-mg.pages';

const eerDashboard = () => import('./eer/eer-dashboard.component').then((m) => m.EerDashboardComponent);
const eerList = () => import('./eer/eer-list.component').then((m) => m.EerListComponent);
const eerNouveau = () => import('./eer/eer-nouveau.component').then((m) => m.EerNouveauComponent);
const eerFiche = () => import('./eer/eer-fiche.component').then((m) => m.EerFicheComponent);
const achatsBons = () => import('./achats-appro/achats-bons.component').then((m) => m.AchatsBonsComponent);
const achatsReceptions = () =>
  import('./achats-appro/achats-receptions.component').then((m) => m.AchatsReceptionsComponent);
const achatsFactures = () => import('./achats-appro/achats-factures.component').then((m) => m.AchatsFacturesComponent);
const achatsPaiements = () =>
  import('./achats-appro/achats-paiements.component').then((m) => m.AchatsPaiementsComponent);

const loadEmpAccueil = () =>
  import('./demandes-employes/demandes-employe.pages').then((m) => m.EmpAccueilComponent);
const loadEmpListe = () =>
  import('./demandes-employes/demandes-employe.pages').then((m) => m.EmpListeComponent);
const loadEmpNouvelle = () =>
  import('./demandes-employes/demandes-employe.pages').then((m) => m.EmpNouvelleComponent);
const loadEmpDocs = () =>
  import('./demandes-employes/demandes-employe.pages').then((m) => m.EmpDocsComponent);
const loadEmpNotifs = () =>
  import('./demandes-employes/demandes-employe.pages').then((m) => m.EmpNotifsComponent);
const loadEmpHistorique = () =>
  import('./demandes-employes/demandes-employe.pages').then((m) => m.EmpHistoriqueComponent);
import { ArchivesRegistreComponent } from './archives-mg/archives-registre.component';
import { ArchivesDashboardComponent } from './archives-mg/archives-dashboard.component';
import { ArchivesDocumentsComponent } from './archives-mg/archives-documents.component';
import { ArchivesMissingComponent } from './archives-mg/archives-missing.component';
import { ArchivesDossierComponent } from './archives-mg/archives-dossier.component';
import { ArchivesDocumentDetailComponent } from './archives-mg/archives-document-detail.component';
import { ArchivesRapportsComponent } from './archives-mg/archives-rapports.component';
import { ArchivesGeneralesComponent } from './archives-generales/archives-generales.component';
import { ArchivesGeneralesDashboardComponent } from './archives-generales/archives-generales-dashboard.component';
import {
  ArchivesGeneralesActiviteComponent,
  ArchivesGeneralesDossiersComponent,
  ArchivesGeneralesDoublonsComponent,
  ArchivesGeneralesManquantsComponent,
  ArchivesGeneralesNumeriserComponent,
  ArchivesGeneralesOcrComponent,
  ArchivesGeneralesParametresComponent,
  ArchivesGeneralesVerifierComponent,
} from './archives-generales/archives-generales-pages.component';

/**
 * Contrat de routes (voir plateforme/module-routing.contract.ts) :
 * - Immobilisations = legacy-root (ShellComponent, paths inchangés).
 * - Modules MG / futurs = même ShellComponent + nav MODULE_SHELL_NAV, path préfixé.
 */
export const routes: Routes = withUnsavedChangesGuard([
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
      { path: 'dashboard', loadComponent: () => import('./stock-fournitures/stock-dashboard.component').then((m) => m.StockDashboardComponent) },
      { path: 'articles', loadComponent: () => import('./stock-fournitures/stock-articles.component').then((m) => m.StockArticlesComponent) },
      { path: 'articles/:id', loadComponent: () => import('./stock-fournitures/stock-article-fiche.component').then((m) => m.StockArticleFicheComponent) },
      { path: 'stock', loadComponent: () => import('./stock-fournitures/stock-pages.component').then((m) => m.StockEtatComponent) },
      { path: 'entrees', loadComponent: () => import('./stock-fournitures/stock-pages.component').then((m) => m.StockEntreesComponent) },
      { path: 'sorties', loadComponent: () => import('./stock-fournitures/stock-pages.component').then((m) => m.StockSortiesComponent) },
      { path: 'mouvements', loadComponent: () => import('./stock-fournitures/stock-mouvements.component').then((m) => m.StockMouvementsComponent) },
      { path: 'journal', loadComponent: () => import('./stock-fournitures/stock-mouvements.component').then((m) => m.StockMouvementsComponent) },
      { path: 'demandes', loadComponent: () => import('./stock-fournitures/stock-demandes.component').then((m) => m.StockDemandesComponent) },
      { path: 'demandes/nouvelle', loadComponent: () => import('./stock-fournitures/stock-demandes.component').then((m) => m.StockDemandesComponent) },
      { path: 'demandes/:id', loadComponent: () => import('./stock-fournitures/stock-demandes.component').then((m) => m.StockDemandesComponent) },
      { path: 'inventaires', loadComponent: () => import('./stock-fournitures/inventaire/stock-inventaires.component').then((m) => m.StockInventairesComponent) },
      { path: 'inventaires/:id', loadComponent: () => import('./stock-fournitures/inventaire/stock-inventaire-detail.component').then((m) => m.StockInventaireDetailComponent) },
      { path: 'inventaire', pathMatch: 'full', redirectTo: 'inventaires' },
      { path: 'alertes', loadComponent: () => import('./stock-fournitures/stock-pages.component').then((m) => m.StockAlertesComponent) },
      { path: 'rapports', loadComponent: () => import('./stock-fournitures/stock-rapports.component').then((m) => m.StockRapportsComponent) },
      { path: 'rapports/:key', loadComponent: () => import('./stock-fournitures/stock-rapport-viewer.component').then((m) => m.StockRapportViewerComponent) },
      { path: 'parametres', loadComponent: () => import('./stock-fournitures/stock-pages.component').then((m) => m.StockParametresComponent) },
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
      { path: 'fournisseurs/nouveau', component: AchatsFournisseursComponent },
      { path: 'fournisseurs/:id', component: AchatsFournisseursComponent },
      { path: 'bons', loadComponent: achatsBons },
      { path: 'nouveau', loadComponent: achatsBons },
      { path: 'bons/:id', loadComponent: achatsBons },
      { path: 'receptions', loadComponent: achatsReceptions },
      { path: 'receptions/nouvelle', loadComponent: achatsReceptions },
      { path: 'receptions/:id', loadComponent: achatsReceptions },
      { path: 'factures', loadComponent: achatsFactures },
      { path: 'factures/nouvelle', loadComponent: achatsFactures },
      { path: 'factures/:id', loadComponent: achatsFactures },
      { path: 'paiements', loadComponent: achatsPaiements },
      { path: 'paiements/nouveau', loadComponent: achatsPaiements },
      { path: 'paiements/:id', loadComponent: achatsPaiements },
      { path: 'rapports', component: AchatsRapportsComponent },
      { path: 'rapports/:key', component: AchatsRapportViewerComponent },
      { path: 'parametres', component: AchatsParametresComponent },
    ],
  },
  {
    path: 'notes-frais',
    component: ShellComponent,
    canActivate: [authGuard, moduleGuard('notes-frais')],
    children: [
      { path: '', pathMatch: 'full', redirectTo: 'dashboard' },
      { path: 'dashboard', component: NotesDashboardComponent },
      { path: 'notes', component: NotesListComponent },
      { path: 'nouvelle', component: NotesListComponent },
      { path: 'notes/:id', component: NotesListComponent },
      { path: 'paiements', component: NotesPaiementsComponent },
      { path: 'rapports', component: NotesRapportsComponent },
      { path: 'parametres', component: NotesParametresComponent },
    ],
  },
  {
    path: 'contrats-echeances',
    component: ShellComponent,
    canActivate: [authGuard, moduleGuard('contrats-echeances')],
    children: [
      { path: '', pathMatch: 'full', redirectTo: 'dashboard' },
      { path: 'dashboard', component: ContratsDashboardComponent },
      { path: 'liste', component: ContratsListComponent },
      { path: 'alertes', component: ContratsListComponent },
      { path: 'echeances', component: ContratsListComponent },
      { path: 'paiements', component: ContratsListComponent },
      { path: 'renouvellements', component: ContratsListComponent },
      { path: 'nouveau', component: ContratsFicheComponent },
      { path: 'rapports', component: ContratsRapportsComponent },
      { path: 'parametres', component: ContratsParametresComponent },
      { path: ':id', component: ContratsFicheComponent },
    ],
  },
  {
    path: 'eer',
    component: ShellComponent,
    canActivate: [authGuard, moduleGuard('eer')],
    children: [
      { path: '', pathMatch: 'full', redirectTo: 'dashboard' },
      { path: 'dashboard', loadComponent: eerDashboard },
      { path: 'dossiers', loadComponent: eerList },
      { path: 'dossiers/nouveau', loadComponent: eerNouveau },
      { path: 'dossiers/:id', loadComponent: eerFiche },
    ],
  },
  {
    path: 'archives-mg',
    component: ShellComponent,
    canActivate: [authGuard, moduleGuard('archives-mg')],
    children: [
      { path: '', pathMatch: 'full', redirectTo: 'dashboard' },
      { path: 'dashboard', component: ArchivesDashboardComponent },
      { path: 'documents', component: ArchivesDocumentsComponent },
      { path: 'documents/:id', component: ArchivesDocumentDetailComponent },
      { path: 'recherche', component: ArchivesDocumentsComponent },
      { path: 'numerisation', component: ArchivesDocumentsComponent },
      { path: 'ocr', component: ArchivesDocumentsComponent },
      { path: 'manquants', component: ArchivesMissingComponent },
      { path: 'corbeille', component: ArchivesDocumentsComponent },
      { path: 'dossiers/:module/:type/:id', component: ArchivesDossierComponent },
      { path: 'registre', component: ArchivesRegistreComponent },
      { path: 'rapports', component: ArchivesRapportsComponent, data: { archivesMode: 'mg' } },
    ],
  },
  {
    path: 'archives-generales',
    component: ShellComponent,
    canActivate: [authGuard, moduleGuard('archives-generales')],
    children: [
      { path: '', pathMatch: 'full', redirectTo: 'dashboard' },
      { path: 'dashboard', component: ArchivesGeneralesDashboardComponent },
      { path: 'vue', pathMatch: 'full', redirectTo: 'documents' },
      { path: 'documents', component: ArchivesGeneralesComponent, data: { archivesMode: 'documents' } },
      { path: 'recherche', component: ArchivesGeneralesComponent, data: { archivesMode: 'recherche' } },
      { path: 'dossiers', component: ArchivesGeneralesDossiersComponent },
      { path: 'ocr', component: ArchivesGeneralesOcrComponent },
      { path: 'numeriser', component: ArchivesGeneralesNumeriserComponent },
      { path: 'manquants', component: ArchivesGeneralesManquantsComponent },
      { path: 'a-verifier', component: ArchivesGeneralesVerifierComponent },
      { path: 'doublons', component: ArchivesGeneralesDoublonsComponent },
      { path: 'controle', pathMatch: 'full', redirectTo: 'manquants' },
      { path: 'activite', component: ArchivesGeneralesActiviteComponent },
      { path: 'parametres', component: ArchivesGeneralesParametresComponent },
      { path: 'rapports', component: ArchivesRapportsComponent, data: { archivesMode: 'general' } },
    ],
  },
  {
    path: 'demandes-comptabilite',
    component: ShellComponent,
    canActivate: [authGuard, moduleGuard('demandes-comptabilite')],
    children: [
      { path: '', pathMatch: 'full', redirectTo: 'accueil' },
      { path: 'accueil', loadComponent: loadEmpAccueil },
      { path: 'demandes', loadComponent: loadEmpListe },
      { path: 'nouvelle', loadComponent: loadEmpNouvelle },
      { path: 'documents', loadComponent: loadEmpDocs },
      { path: 'notifications', loadComponent: loadEmpNotifs },
      { path: 'historique', loadComponent: loadEmpHistorique },
    ],
  },
  {
    path: 'demandes-credit',
    component: ShellComponent,
    canActivate: [authGuard, moduleGuard('demandes-credit')],
    children: [
      { path: '', pathMatch: 'full', redirectTo: 'accueil' },
      { path: 'accueil', loadComponent: loadEmpAccueil },
      { path: 'demandes', loadComponent: loadEmpListe },
      { path: 'nouvelle', loadComponent: loadEmpNouvelle },
      { path: 'documents', loadComponent: loadEmpDocs },
      { path: 'notifications', loadComponent: loadEmpNotifs },
      { path: 'historique', loadComponent: loadEmpHistorique },
    ],
  },
  {
    path: 'demandes-rh',
    component: ShellComponent,
    canActivate: [authGuard, moduleGuard('demandes-rh')],
    children: [
      { path: '', pathMatch: 'full', redirectTo: 'accueil' },
      { path: 'accueil', loadComponent: loadEmpAccueil },
      { path: 'demandes', loadComponent: loadEmpListe },
      { path: 'nouvelle', loadComponent: loadEmpNouvelle },
      { path: 'documents', loadComponent: loadEmpDocs },
      { path: 'notifications', loadComponent: loadEmpNotifs },
      { path: 'historique', loadComponent: loadEmpHistorique },
    ],
  },
  {
    path: 'demandes-informatique',
    component: ShellComponent,
    canActivate: [authGuard, moduleGuard('demandes-informatique')],
    children: [
      { path: '', pathMatch: 'full', redirectTo: 'accueil' },
      { path: 'accueil', loadComponent: loadEmpAccueil },
      { path: 'demandes', loadComponent: loadEmpListe },
      { path: 'nouvelle', loadComponent: loadEmpNouvelle },
      { path: 'documents', loadComponent: loadEmpDocs },
      { path: 'notifications', loadComponent: loadEmpNotifs },
      { path: 'historique', loadComponent: loadEmpHistorique },
    ],
  },
  {
    path: 'demandes-mg',
    component: ShellComponent,
    canActivate: [authGuard, moduleGuard('demandes-mg')],
    children: [
      { path: '', pathMatch: 'full', redirectTo: 'dashboard' },
      { path: 'dashboard', component: DmgDashboardComponent },
      { path: 'accueil', loadComponent: loadEmpAccueil },
      { path: 'nouvelle', loadComponent: loadEmpNouvelle },
      { path: 'mes-demandes', loadComponent: loadEmpListe },
      { path: 'demandes', component: DmgInboxComponent },
      { path: 'a-traiter', component: DmgInboxComponent, data: { statut: 'a_traiter' } },
      { path: 'a-completer', component: DmgInboxComponent, data: { statut: 'A_COMPLETER' } },
      { path: 'validees', component: DmgInboxComponent, data: { statut: 'a_regrouper' } },
      { path: 'refusees', component: DmgInboxComponent, data: { statut: 'REFUSEE' } },
      { path: 'regroupements', component: DmgBatchesComponent },
      { path: 'documents', loadComponent: loadEmpDocs },
      { path: 'notifications', loadComponent: loadEmpNotifs },
    ],
  },
  { path: 'demandes-employes', redirectTo: 'accueil' },
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
      // Comptes gérés par CORE ADMIN ; l'URL reste réservée (anciens liens / favoris).
      { path: 'utilisateurs', redirectTo: '/admin/users', pathMatch: 'full' },
      { path: 'audit', component: AuditComponent },
      { path: 'parametres', component: ParametresComponent },
    ],
  },
  { path: '**', redirectTo: 'accueil' },
]);
