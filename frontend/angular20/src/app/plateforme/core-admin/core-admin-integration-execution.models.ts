import { HttpErrorResponse } from '@angular/common/http';
import { computed, inject } from '@angular/core';
import { AuthService } from '../../core/services/auth.service';
import { IntegrationPersonne, messageErreur } from './core-admin-integration-clients.models';
import type { OperationDetail } from './core-admin-integration-fournisseurs.models';

export type DestinationStatut = 'brouillon' | 'a_valider' | 'active' | 'suspendue' | 'archivee';
export type ExecutionStatut =
  | 'succes'
  | 'http_erreur'
  | 'refuse_securite'
  | 'timeout'
  | 'trop_volumineux'
  | 'dns'
  | 'tls'
  | 'redirection_refusee'
  | 'reponse_invalide'
  | 'secret_requis'
  | 'quota';
export type AlerteStatut = 'nouvelle' | 'en_cours' | 'resolue' | 'ignoree';

export const PERMISSIONS_DESTINATIONS = {
  view: 'core.admin.integrations.destinations.view',
  manage: 'core.admin.integrations.destinations.manage',
  approve: 'core.admin.integrations.destinations.approve',
} as const;

export const PERMISSIONS_TESTS = {
  view: 'core.admin.integrations.tests.view',
  execute: 'core.admin.integrations.tests.execute',
} as const;

export const PERMISSIONS_SUPERVISION = {
  view: 'core.admin.integrations.supervision.view',
  manage: 'core.admin.integrations.supervision.manage',
  export: 'core.admin.integrations.supervision.export',
} as const;

/** Permissions du Studio, telles que déclarées dans `plateforme_catalogue.py` (aucune n'est attribuée par défaut). */
export const PERMISSIONS_STUDIO = {
  catalogue: 'core.admin.integrations.view',
  clients: 'core.admin.integrations.clients.view',
  fournisseurs: 'core.admin.integrations.fournisseurs.view',
  destinations: PERMISSIONS_DESTINATIONS.view,
  testsView: PERMISSIONS_TESTS.view,
  testsExecute: PERMISSIONS_TESTS.execute,
  supervision: PERMISSIONS_SUPERVISION.view,
  supervisionExport: PERMISSIONS_SUPERVISION.export,
} as const;

/** Une seule de ces permissions suffit pour afficher l'entrée du Studio et sa vue d'ensemble. */
export const PERMISSIONS_ENTREE_STUDIO: readonly string[] = [
  PERMISSIONS_STUDIO.catalogue,
  PERMISSIONS_STUDIO.clients,
  PERMISSIONS_STUDIO.fournisseurs,
  PERMISSIONS_STUDIO.destinations,
  PERMISSIONS_STUDIO.testsView,
  PERMISSIONS_STUDIO.testsExecute,
  PERMISSIONS_STUDIO.supervision,
];

export function integrationStudioPermissions() {
  const has = _has();
  return {
    catalogue: has(PERMISSIONS_STUDIO.catalogue),
    clients: has(PERMISSIONS_STUDIO.clients),
    fournisseurs: has(PERMISSIONS_STUDIO.fournisseurs),
    destinations: has(PERMISSIONS_STUDIO.destinations),
    testsView: has(PERMISSIONS_STUDIO.testsView),
    testsExecute: has(PERMISSIONS_STUDIO.testsExecute),
    supervision: has(PERMISSIONS_STUDIO.supervision),
    supervisionManage: has(PERMISSIONS_SUPERVISION.manage),
    supervisionExport: has(PERMISSIONS_STUDIO.supervisionExport),
  };
}

export function integrationDestinationsPermissions() {
  const has = _has();
  return { view: has(PERMISSIONS_DESTINATIONS.view), manage: has(PERMISSIONS_DESTINATIONS.manage), approve: has(PERMISSIONS_DESTINATIONS.approve) };
}

export function integrationTestsPermissions() {
  const has = _has();
  return { view: has(PERMISSIONS_TESTS.view), execute: has(PERMISSIONS_TESTS.execute) };
}

export function integrationSupervisionPermissions() {
  const has = _has();
  return {
    view: has(PERMISSIONS_SUPERVISION.view),
    manage: has(PERMISSIONS_SUPERVISION.manage),
    export: has(PERMISSIONS_SUPERVISION.export),
  };
}

function _has() {
  const auth = inject(AuthService);
  return (code: string) =>
    computed(() => {
      const p = auth.user();
      if (!p) return false;
      const codes = p.permission_codes ?? [];
      return p.is_superuser || codes.includes('*') || codes.includes(code);
    });
}

export interface DestinationResume {
  id: string;
  code: string;
  nom: string;
  fournisseur_id: string;
  environnement: 'TEST';
  statut: DestinationStatut;
  hotes: string[];
  methodes: string[];
  updated_at: string;
  valide_le?: string | null;
  fournisseur_nom?: string | null;
  nb_operations?: number;
}

export interface DestinationPage {
  items: DestinationResume[];
  total: number;
  page: number;
  size: number;
}

export interface DestinationFiche extends Omit<DestinationResume, 'fournisseur_nom'> {
  fournisseur_nom: string;
  fournisseur_statut: string;
  protocole: string;
  ports: number[];
  operations: string[];
  motif_statut?: string | null;
  notes?: string | null;
  revision: number;
  modifiable: boolean;
  transitions: DestinationStatut[];
  valide_par?: IntegrationPersonne | null;
  created_at: string;
  cree_par?: IntegrationPersonne | null;
  modifie_par?: IntegrationPersonne | null;
  archived_at?: string | null;
  archive_par?: IntegrationPersonne | null;
  motif_archivage?: string | null;
  avertissement: string;
}

export interface DestinationSaisie {
  nom: string;
  fournisseur_id: string;
  hotes: string[];
  ports: number[];
  methodes: ('GET' | 'HEAD')[];
  operations: string[];
  notes: string | null;
}

export interface TestApercu {
  methode: string;
  url: string;
  hote: string;
  port: number;
  chemin: string;
  parametres_requete: string[];
  entetes_envoyes: string[];
  authentification: string;
  redirections: string;
  environnement: string;
  avertissement: string;
  fournisseur: string;
  operation: string;
  destination: string;
}

export interface ExecutionDetail {
  id: string;
  correlation_id: string;
  fournisseur_id: string;
  fournisseur_nom?: string | null;
  operation_id: string;
  operation_nom?: string | null;
  methode: string;
  chemin: string;
  destination_id: string;
  destination_nom?: string | null;
  environnement: string;
  hote: string;
  port: number;
  started_at: string;
  duree_ms?: number | null;
  statut: ExecutionStatut;
  http_status?: number | null;
  erreur_categorie?: string | null;
  acteur?: IntegrationPersonne | null;
  controles: Record<string, unknown>;
  limites: Record<string, unknown>;
  reponse?: {
    type_contenu?: string | null;
    taille?: number;
    extrait?: string | null;
    entetes?: { nom: string; valeur: string }[];
    tronque?: boolean;
    redirection?: string | null;
  } | null;
  message?: string | null;
  disponibilite: string;
}

export interface ExecutionResume {
  id: string;
  correlation_id: string;
  fournisseur_id: string;
  fournisseur_nom?: string | null;
  operation_id: string;
  operation_nom?: string | null;
  destination_id: string;
  destination_nom?: string | null;
  environnement?: string;
  methode: string;
  chemin: string;
  hote: string;
  started_at: string;
  duree_ms?: number | null;
  statut: ExecutionStatut;
  http_status?: number | null;
  erreur_categorie?: string | null;
}

export interface ExecutionPage {
  items: ExecutionResume[];
  total: number;
  page: number;
  size: number;
  retention_jours: number;
}

export interface TableauSupervision {
  periode: { depuis?: string | null; jusqua?: string | null; denominateur: string };
  total: number;
  succes: number;
  echecs: number;
  taux_succes: number | null;
  taux_libelle: string;
  latence_moyenne_ms: number | null;
  latence_mediane_ms: number | null;
  erreurs: { categorie: string; nombre: number }[];
  series?: SerieJour[];
  par_fournisseur?: { fournisseur_id: string; nom?: string | null; total: number; succes: number; echecs: number }[];
  dernier?: { id: string; correlation_id: string; statut: string; started_at: string; duree_ms?: number | null; http_status?: number | null; methode?: string; chemin?: string } | null;
  dernier_succes?: { id: string; started_at: string } | null;
  dernier_echec?: { id: string; started_at: string; statut: string } | null;
  sans_mesure: { id: string; nom: string; statut: string; disponibilite: string }[];
  destinations_suspendues: { id: string; nom: string; statut: string }[];
  disponibilite: string;
  retention_jours: number;
  sondes_automatiques: boolean;
}

export interface AlerteItem {
  id: string;
  type: string;
  statut: AlerteStatut;
  message: string;
  niveau?: AlerteNiveau;
  regle?: string | null;
  resolue_le?: string | null;
  occurences: number;
  fournisseur_id?: string | null;
  destination_id?: string | null;
  operation_id?: string | null;
  details: Record<string, unknown>;
  derniere_le: string;
  created_at: string;
  fournisseur_nom?: string | null;
  destination_nom?: string | null;
  operation_nom?: string | null;
  resolue_par?: IntegrationPersonne | null;
  /** Transitions permises par le serveur (le serveur reste seul juge). */
  transitions?: AlerteStatut[];
}

export interface AlertePage {
  items: AlerteItem[];
  total: number;
  page: number;
  size: number;
  compteurs?: Record<AlerteStatut, number>;
}

export interface AlerteHistorique {
  id: string;
  acteur?: IntegrationPersonne | null;
  created_at: string;
  avant?: string | null;
  apres?: string | null;
}

export interface SerieJour {
  jour: string;
  total: number;
  succes: number;
  echecs: number;
  taux_succes: number | null;
  latence_moyenne_ms: number | null;
}

export const TRANSITIONS_DESTINATION: Partial<Record<DestinationStatut, { libelle: string; droit: 'manage' | 'approve'; motif: boolean; tone: 'primary' | 'danger' }>> = {
  brouillon: { libelle: 'Revenir en brouillon', droit: 'manage', motif: false, tone: 'primary' },
  a_valider: { libelle: 'Soumettre à approbation', droit: 'manage', motif: false, tone: 'primary' },
  active: { libelle: 'Approuver (TEST)', droit: 'approve', motif: false, tone: 'primary' },
  suspendue: { libelle: 'Suspendre', droit: 'approve', motif: true, tone: 'danger' },
};

export function destinationStatutLabel(s: string): string {
  return ({ brouillon: 'Brouillon', a_valider: 'À approuver', active: 'Active (TEST)', suspendue: 'Suspendue', archivee: 'Archivée' } as Record<string, string>)[s] ?? s;
}

export function destinationStatutTone(s: string): string {
  if (s === 'active') return 'bea-badge bea-badge--actif';
  if (s === 'brouillon' || s === 'a_valider') return 'bea-badge bea-badge--bientot';
  return 'bea-badge bea-badge--inactif';
}

export function executionStatutLabel(s: string): string {
  return ({
    succes: 'Succès', http_erreur: 'Erreur HTTP', refuse_securite: 'Refus de sécurité',
    timeout: 'Délai dépassé', trop_volumineux: 'Réponse trop volumineuse', dns: 'DNS',
    tls: 'TLS', redirection_refusee: 'Redirection refusée', reponse_invalide: 'Réponse invalide',
    secret_requis: 'Secret requis', quota: 'Quota',
  } as Record<string, string>)[s] ?? s;
}

export function disponibiliteLabel(s: string): string {
  return ({
    configuree: 'Configurée', approuvee: 'Approuvée', testee: 'Testée',
    disponible_dernier_test: 'Disponible lors du dernier test', en_erreur: 'En erreur', inconnue: 'Inconnue',
  } as Record<string, string>)[s] ?? s;
}

export function alerteTypeLabel(s: string): string {
  return ({
    echecs_consecutifs: 'Échecs consécutifs', taux_erreur: 'Taux d’erreur', latence: 'Latence',
    non_testee: 'Non testée', destination_suspendue: 'Destination suspendue', refus_securite: 'Refus de sécurité',
  } as Record<string, string>)[s] ?? s;
}

export function hotesDepuisTexte(texte: string): string[] {
  return texte.split(/[\s,;]+/).map((h) => h.trim().toLowerCase()).filter(Boolean);
}

export type AlerteNiveau = 'elevee' | 'moyenne' | 'info';

export const STATUTS_EXECUTION: ExecutionStatut[] = [
  'succes', 'http_erreur', 'timeout', 'dns', 'tls', 'redirection_refusee', 'trop_volumineux',
  'reponse_invalide', 'refuse_securite', 'secret_requis', 'quota',
];

export const TYPES_ALERTE = [
  'echecs_consecutifs', 'taux_erreur', 'latence', 'non_testee', 'destination_suspendue', 'refus_securite',
] as const;

export const STATUTS_ALERTE: AlerteStatut[] = ['nouvelle', 'en_cours', 'resolue', 'ignoree'];

export function alerteStatutLabel(s: string): string {
  return ({ nouvelle: 'Nouvelle', en_cours: 'En cours de traitement', resolue: 'Résolue', ignoree: 'Ignorée' } as Record<string, string>)[s] ?? s;
}

export function alerteStatutTone(s: string): string {
  if (s === 'nouvelle') return 'bea-badge bea-badge--inactif';
  if (s === 'en_cours') return 'bea-badge bea-badge--bientot';
  return 'bea-badge bea-badge--actif';
}

export function niveauLabel(s: string | undefined): string {
  return ({ elevee: 'Élevé', moyenne: 'Moyen', info: 'Information' } as Record<string, string>)[s ?? ''] ?? '—';
}

export function niveauTone(s: string | undefined): string {
  if (s === 'elevee') return 'bea-badge bea-badge--inactif';
  if (s === 'moyenne') return 'bea-badge bea-badge--bientot';
  return 'bea-badge';
}

/** Famille d'un statut d'exécution : distingue erreur du fournisseur, erreur réseau et refus local. */
export function executionFamille(s: string): 'succes' | 'fournisseur' | 'reseau' | 'refus' {
  if (s === 'succes') return 'succes';
  if (s === 'http_erreur' || s === 'trop_volumineux' || s === 'reponse_invalide' || s === 'redirection_refusee') return 'fournisseur';
  if (s === 'timeout' || s === 'dns' || s === 'tls') return 'reseau';
  return 'refus';
}

export function executionFamilleLabel(s: string): string {
  return ({
    succes: 'Réponse reçue',
    fournisseur: 'Réponse du fournisseur non conforme',
    reseau: 'Connectivité',
    refus: 'Refusé par BEA DIGITAL (aucun appel ou appel interrompu)',
  } as Record<string, string>)[executionFamille(s)];
}

export function executionStatutTone(s: string): string {
  const f = executionFamille(s);
  if (f === 'succes') return 'bea-badge bea-badge--actif';
  if (f === 'refus') return 'bea-badge bea-badge--bientot';
  return 'bea-badge bea-badge--inactif';
}

export type PeriodeCode = '24h' | '7j' | '30j' | 'tout' | 'perso';

export const PERIODES: { code: PeriodeCode; libelle: string }[] = [
  { code: '24h', libelle: '24 dernières heures' },
  { code: '7j', libelle: '7 derniers jours' },
  { code: '30j', libelle: '30 derniers jours' },
  { code: 'tout', libelle: 'Toute la rétention (90 jours)' },
  { code: 'perso', libelle: 'Personnalisée' },
];

/** Bornes ISO d'une période ; `perso` lit les champs `datetime-local` saisis. */
export function bornesPeriode(code: PeriodeCode, depuis = '', jusqua = '', maintenant = new Date()): { depuis?: string; jusqua?: string } {
  const heures: Partial<Record<PeriodeCode, number>> = { '24h': 24, '7j': 24 * 7, '30j': 24 * 30 };
  const h = heures[code];
  if (h) return { depuis: new Date(maintenant.getTime() - h * 3600_000).toISOString() };
  if (code === 'perso') {
    const out: { depuis?: string; jusqua?: string } = {};
    if (depuis) out.depuis = new Date(depuis).toISOString();
    if (jusqua) out.jusqua = new Date(jusqua).toISOString();
    return out;
  }
  return {};
}

export function telechargerBlob(blob: Blob, nomFichier: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = nomFichier;
  a.click();
  URL.revokeObjectURL(url);
}

/** Plafond serveur de l'export CSV de supervision (lignes les plus récentes). */
export const EXPORT_MAX_LIGNES = 500;

/** Paramètres de requête sans valeurs vides. */
export function sansVides(valeurs: Record<string, string | undefined | null>): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [k, v] of Object.entries(valeurs)) {
    if (v !== undefined && v !== null && String(v).trim() !== '') out[k] = String(v).trim();
  }
  return out;
}

export function codeErreur(err: unknown): string | null {
  if (!(err instanceof HttpErrorResponse)) return null;
  const code = (err.error ?? {}).code;
  return typeof code === 'string' ? code : null;
}

const MESSAGES_TEST: Record<string, string> = {
  SECRET_REQUIS:
    'Test bloqué : cette opération exige une authentification. Aucun coffre de secrets n’est approuvé ; aucun secret ne peut être saisi ni transmis.',
  QUOTA: 'Quota de tests atteint (10 par utilisateur et 20 par fournisseur sur 10 minutes, 3 simultanés). Réessayez plus tard.',
  QUOTA_INDISPONIBLE: 'Le service de limitation de débit est indisponible : par sécurité, aucun test n’est envoyé.',
  TIMEOUT: 'Délai dépassé : la destination n’a pas répondu dans le temps imparti (connexion 3 s, lecture 8 s).',
  TLS: 'Connexion TLS impossible ou certificat invalide.',
  DNS: 'Résolution DNS impossible pour l’hôte de la destination.',
  RESEAU: 'Réponse ou protocole invalide.',
  DESTINATION_INACTIVE: 'La destination n’est pas approuvée (statut actif requis).',
  FOURNISSEUR_NON_VALIDE: 'Le fournisseur doit être validé avant tout test.',
  ENVIRONNEMENT_FERME: 'Seul l’environnement TEST est autorisé.',
  METHODE_INTERDITE: 'Seules les méthodes GET et HEAD autorisées par la destination peuvent être testées.',
  OPERATION_NON_AUTORISEE: 'Cette opération n’est pas autorisée sur la destination choisie.',
  IP_INTERDITE: 'Refus de sécurité : l’hôte résout vers une adresse interne ou non publique.',
  HOTE_INTERDIT: 'Refus de sécurité : hôte interdit.',
  PORT_INTERDIT: 'Refus de sécurité : port non autorisé.',
};

/** Message explicite pour une erreur de test ; le message serveur reste la référence quand le code est inconnu. */
export function messageTest(err: unknown, fallback: string): string {
  const code = codeErreur(err);
  if (code && MESSAGES_TEST[code]) return MESSAGES_TEST[code];
  return messageErreur(err, fallback);
}

/** Miroir de la règle serveur : seul le mécanisme `aucun` est testable (le serveur reste seul juge). */
export function operationExigeSecret(op: Pick<OperationDetail, 'configuration'> | null | undefined): boolean {
  const m = (op?.configuration?.mecanisme_auth ?? 'non_precise').toString().toLowerCase();
  return m !== 'aucun';
}
