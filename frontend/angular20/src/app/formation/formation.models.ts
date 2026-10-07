export const FO_BASE = '/formation';

export type Domaine = 'THEME' | 'FORMATEUR' | 'LIEU' | 'FONCTION' | 'PERIMETRE';
export type Presence = 'PRESENT' | 'ABSENT' | null;
export type StatutSession = 'PLANIFIEE' | 'REALISEE' | 'CLOTUREE' | 'ANNULEE' | 'ARCHIVEE';

export const DOMAINES: { code: Domaine | 'ENTITE'; label: string; pluriel: string; icon: string }[] = [
  { code: 'THEME', label: 'Thème', pluriel: 'Thèmes', icon: 'category' },
  { code: 'FORMATEUR', label: 'Formateur', pluriel: 'Formateurs', icon: 'record_voice_over' },
  { code: 'LIEU', label: 'Lieu', pluriel: 'Lieux', icon: 'place' },
  { code: 'FONCTION', label: 'Fonction', pluriel: 'Fonctions', icon: 'work_outline' },
  { code: 'PERIMETRE', label: 'Périmètre', pluriel: 'Périmètres', icon: 'hub' },
  { code: 'ENTITE', label: 'Entité', pluriel: 'Entités', icon: 'account_tree' },
];

export interface RefCourt {
  id: string;
  libelle: string;
  actif?: boolean;
}

export interface RefItem extends RefCourt {
  domaine: Domaine;
  description: string | null;
  ordre: number;
  actif: boolean;
  usage: number;
}

export interface Entite {
  id: string;
  libelle: string;
  perimetre_id: string;
  perimetre: string | null;
  lieu_id: string | null;
  lieu: string | null;
  actif: boolean;
  ordre?: number;
  agence_id?: string | null;
  usage?: number;
}

export interface Capacites {
  voir: boolean;
  creer: boolean;
  modifier: boolean;
  annuler: boolean;
  cloturer: boolean;
  employes_voir: boolean;
  employes_gerer: boolean;
  presences_voir: boolean;
  presences_gerer: boolean;
  referentiels_voir: boolean;
  referentiels_gerer: boolean;
  imports_voir: boolean;
  imports_executer: boolean;
  reporting_voir: boolean;
  reporting_exporter: boolean;
  admin: boolean;
}

export interface FoConfig {
  capacites: Capacites;
  referentiels: Record<Domaine, RefItem[]>;
  entites: Entite[];
  statuts: { code: StatutSession; libelle: string }[];
  aujourdhui: string;
  utilisateur: string;
}

export interface Employe {
  id: string;
  nom: string;
  prenom: string | null;
  nom_complet: string;
  fonction_id: string | null;
  fonction: string | null;
  entite_id: string | null;
  entite: string | null;
  perimetre_id: string | null;
  perimetre: string | null;
  email: string | null;
  telephone: string | null;
  actif: boolean;
  motif_desactivation: string | null;
  source: string;
  created_at: string | null;
  updated_at: string | null;
  nb_formations?: number;
  nb_presents?: number;
  nb_absents?: number;
  derniere_formation?: string | null;
  identique?: boolean;
}

export interface HistoriqueLigne {
  participant_id: string;
  session_id: string;
  reference: string;
  date: string;
  themes: string[];
  theme: string;
  lieu: string | null;
  formateurs: string[];
  presence: Presence;
  statut: StatutSession;
  statut_libelle: string;
  entite: string | null;
  perimetre: string | null;
}

export interface FicheEmploye extends Employe {
  stats: { participations: number; presents: number; absents: number; non_saisis: number; taux_presence: number | null; derniere_formation: string | null };
  par_theme: { libelle: string; valeur: number }[];
  historique: HistoriqueLigne[];
}

export interface Participant {
  id: string;
  n: number;
  employe_id: string;
  nom: string;
  prenom: string | null;
  nom_complet: string;
  fonction: string | null;
  entite: string | null;
  perimetre: string | null;
  employe_actif: boolean;
  presence: Presence;
  presence_saisie_le: string | null;
}

export interface StatsSession {
  participants: number;
  presents: number;
  absents: number;
  non_saisis: number;
  taux_presence: number | null;
}

export interface ActionsSession {
  modifier: boolean;
  participants: boolean;
  saisir_presences: boolean;
  cloturer: boolean;
  rouvrir: boolean;
  annuler: boolean;
  retablir: boolean;
  archiver: boolean;
  desarchiver: boolean;
  supprimer: boolean;
  exporter: boolean;
}

export interface Session {
  id: string;
  reference: string;
  intitule: string | null;
  date_session: string;
  lieu: RefCourt | null;
  themes: RefCourt[];
  formateurs: RefCourt[];
  theme_libelle: string;
  formateur_libelle: string;
  statut: StatutSession;
  statut_libelle: string;
  a_saisir: boolean;
  a_venir: boolean;
  observations: string | null;
  motif_annulation: string | null;
  presences_saisies_le: string | null;
  cloturee_le: string | null;
  source: string;
  revision: number;
  created_at: string | null;
  updated_at: string | null;
  stats: StatsSession;
  actions: ActionsSession;
  participants?: Participant[];
  feuilles_signees?: number;
}

export interface FeuilleSignee {
  id: string;
  filename: string;
  mime_type: string | null;
  size_bytes: number;
  created_at: string | null;
  uploaded_by: string | null;
  ocr_status: string;
}

export interface FeuillesSession {
  items: FeuilleSignee[];
  actions: { deposer: boolean; retirer: boolean };
}

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  taille: number;
}

export interface Groupe {
  libelle: string;
  formations: number;
  participants: number;
  presents: number;
  absents: number;
  employes: number;
  taux: number | null;
  cle?: string;
}

export interface FormationLigne {
  id: string;
  reference: string;
  date: string;
  intitule: string | null;
  theme: string;
  lieu: string | null;
  formateur: string;
  statut: StatutSession;
  statut_libelle: string;
  participants: number;
  presents: number;
  absents: number;
  non_saisis: number;
  taux: number | null;
}

export interface ParticipationLigne {
  session_id: string;
  reference: string;
  date: string;
  theme: string;
  lieu: string | null;
  formateur: string;
  employe_id: string;
  nom: string;
  prenom: string | null;
  nom_complet: string;
  fonction: string | null;
  entite: string | null;
  perimetre: string | null;
  presence: Presence;
  presence_libelle: string;
}

export interface Kpis {
  formations: number;
  formations_realisees: number;
  formations_a_venir: number;
  participations: number;
  presents: number;
  absents: number;
  non_saisis: number;
  taux_presence: number | null;
  employes_concernes: number;
  employes_formes: number;
  employes_actifs: number;
  themes_couverts: number;
}

export interface Reporting {
  filtres: Record<string, string | number>;
  genere_le: string;
  kpis: Kpis;
  par_annee: Groupe[];
  par_mois: Groupe[];
  par_theme: Groupe[];
  par_entite: Groupe[];
  par_perimetre: Groupe[];
  par_lieu: Groupe[];
  par_formateur: Groupe[];
  par_fonction: Groupe[];
  presence: { libelle: string; valeur: number; cle: string }[];
  formations: FormationLigne[];
  participations: ParticipationLigne[];
  participations_total: number;
}

export interface SessionCourte {
  id: string;
  reference: string;
  date: string;
  theme: string;
  lieu: string | null;
  statut: StatutSession;
  statut_libelle: string;
  participants: number;
}

export interface Dashboard extends Reporting {
  prochaines: SessionCourte[];
  a_saisir: SessionCourte[];
  nb_a_saisir: number;
  nb_a_cloturer: number;
  dernieres: SessionCourte[];
  couverture: { libelle: string; actifs: number; formes: number; taux: number | null }[];
  couverture_globale: { actifs: number; formes: number; jamais_formes: number; taux: number | null };
  annees: number[];
}

export interface JournalLigne {
  id: string;
  action: string;
  libelle: string;
  entity: string;
  entity_id: string | null;
  utilisateur: string;
  date: string | null;
  avant: Record<string, unknown> | null;
  apres: Record<string, unknown> | null;
  request_id: string | null;
}

export interface ResultatRecherche {
  employes: { id: string; libelle: string; sous: string; actif: boolean }[];
  formations: { id: string; libelle: string; sous: string }[];
  referentiels: { id: string; libelle: string; domaine: Domaine; sous: string }[];
  entites: { id: string; libelle: string; sous: string }[];
}

// ------------------------------------------------------------------ import
export interface ValeurImport {
  cle: string;
  brut: string;
  occurrences: number;
  libelle: string;
  action: 'MAPPER' | 'CREER' | 'IGNORER';
  cible_id: string | null;
  cible: string | null;
  score: number;
  a_verifier: boolean;
  suggestion?: string | null;
  suggestion_id?: string | null;
  perimetre_id?: string | null;
  perimetre?: string | null;
  perimetre_brut?: string | null;
  lieu_id?: string | null;
}

export interface PersonneImport {
  cle: string;
  brut: string;
  variantes: string[];
  occurrences: number;
  mots: string[];
  fonction: string;
  entite: string;
  nom_colonne: string | null;
  prenom_colonne: string | null;
  action: 'NOUVEAU' | 'EXISTANT';
  employe_id: string | null;
  employe: string | null;
  candidats: { id: string; nom_complet: string; entite: string | null }[];
}

export interface AnomalieImport {
  ligne: number | null;
  niveau: 'bloquant' | 'alerte' | 'info';
  message: string;
}

export interface AnalyseImport {
  fichier: string;
  feuille: string;
  feuilles: string[];
  ligne_entete: number;
  colonnes: { champ: string; libelle: string; index: number; entete: string }[];
  colonnes_ignorees: string[];
  presence_colonne: boolean;
  valeurs: Partial<Record<Domaine | 'ENTITE', ValeurImport[]>>;
  personnes: PersonneImport[];
  sessions: { cle: string; date: string; themes: string[]; lieu: string; formateurs: string[]; nb_participants: number; lignes: number[] }[];
  anomalies: AnomalieImport[];
  stats: Record<string, number>;
  deja_importe: { le: string | null; id: string } | null;
}

export interface ImportFormation {
  id: string;
  fichier_nom: string;
  statut: 'ANALYSE' | 'IMPORTE' | 'ABANDONNE';
  nb_lignes: number;
  created_at: string | null;
  importe_le: string | null;
  stats: Record<string, number> | null;
  resultat: Record<string, number> | null;
  auteur: string | null;
  analyse?: AnalyseImport;
}

// ----------------------------------------------------------------- helpers
export const STATUT_LIBELLES: Record<StatutSession, string> = {
  PLANIFIEE: 'Planifiée',
  REALISEE: 'Réalisée',
  CLOTUREE: 'Clôturée',
  ANNULEE: 'Annulée',
  ARCHIVEE: 'Archivée',
};

/** Statut affiché : « Présences à saisir » pour une planifiée déjà passée. */
export function statutAffiche(s: { statut: StatutSession; a_saisir?: boolean }): { code: string; label: string } {
  if (s.statut === 'PLANIFIEE' && s.a_saisir) return { code: 'A_SAISIR', label: 'Présences à saisir' };
  return { code: s.statut, label: STATUT_LIBELLES[s.statut] ?? s.statut };
}

export function dateFr(iso: string | null | undefined): string {
  if (!iso) return '—';
  const [y, m, d] = iso.slice(0, 10).split('-');
  return `${d}/${m}/${y}`;
}

export function dateHeureFr(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  return `${d.toLocaleDateString('fr-FR')} ${d.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })}`;
}

export function dateLongue(iso: string | null | undefined): string {
  if (!iso) return '—';
  return new Date(`${iso.slice(0, 10)}T12:00:00`).toLocaleDateString('fr-FR', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });
}

export function jourMois(iso: string): { jour: string; mois: string; annee: string } {
  const d = new Date(`${iso.slice(0, 10)}T12:00:00`);
  return {
    jour: String(d.getDate()).padStart(2, '0'),
    mois: d.toLocaleDateString('fr-FR', { month: 'short' }).replace('.', ''),
    annee: String(d.getFullYear()),
  };
}

export function taux(v: number | null | undefined): string {
  return v === null || v === undefined ? '—' : `${v.toLocaleString('fr-FR', { maximumFractionDigits: 1 })} %`;
}

export function initiales(nom: string | null | undefined): string {
  return (nom || '?')
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((m) => m[0]!.toUpperCase())
    .join('');
}

/** Paramètres HTTP sans valeurs vides. */
export function nettoyer(v: Record<string, unknown>): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [k, val] of Object.entries(v)) {
    if (val === null || val === undefined || val === '' || val === false) continue;
    out[k] = String(val);
  }
  return out;
}

export function telecharger(blob: Blob, nom: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = nom;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1500);
}

export function normaliser(s: string | null | undefined): string {
  return (s || '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, ' ')
    .trim();
}

export function correspond(texte: string, q: string): boolean {
  const t = normaliser(texte);
  return normaliser(q)
    .split(' ')
    .filter(Boolean)
    .every((j) => t.includes(j));
}

export const ANNEE_COURANTE = new Date().getFullYear();
