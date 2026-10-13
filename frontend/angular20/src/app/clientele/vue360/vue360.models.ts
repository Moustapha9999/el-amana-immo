import { dateHeureFr } from '../clientele.models';

export type EtatChargement = 'chargement' | 'ok' | 'erreur';
export type Vue360 = 'synthese' | 'profilage' | 'filtrage' | 'listes' | 'alertes' | 'recherche' | 'journal';

export const VUES_360: { code: Vue360; libelle: string; icone: string }[] = [
  { code: 'synthese', libelle: 'Vue 360°', icone: 'dashboard' },
  { code: 'profilage', libelle: 'Profilage & classification', icone: 'leaderboard' },
  { code: 'filtrage', libelle: 'Filtrage réglementaire', icone: 'policy' },
  { code: 'listes', libelle: 'Listes d’interdiction', icone: 'gpp_maybe' },
  { code: 'alertes', libelle: 'Centre d’alertes', icone: 'notification_important' },
  { code: 'recherche', libelle: 'Recherche & fiche 360°', icone: 'person_search' },
  { code: 'journal', libelle: 'Historique & audit', icone: 'history' },
];

/** Filtres portés par l’URL : un lien depuis un KPI ouvre la liste déjà filtrée. */
export interface Filtres360 {
  periode?: string; du?: string; au?: string;
  profil?: string; agence?: string; niveau?: string; profilage?: string; filtrage?: string;
  anomalie?: string; coherence?: string; completude?: string; q?: string; classe_periode?: string;
  groupe?: string; source?: string; assignee?: string; anciennete_min?: string; tri?: string; periode_alertes?: string;
}

export const CLES_POPULATION = ['profil', 'agence', 'niveau', 'profilage', 'filtrage', 'anomalie', 'coherence', 'completude', 'q'] as const;
export const CLES_FILTRES: (keyof Filtres360)[] = [
  'periode', 'du', 'au', ...CLES_POPULATION, 'classe_periode',
  'groupe', 'source', 'assignee', 'anciennete_min', 'tri', 'periode_alertes',
];

export const PERIODES = [
  { code: 'jour', libelle: 'Aujourd’hui' }, { code: '7j', libelle: '7 jours' }, { code: '30j', libelle: '30 jours' },
  { code: 'trimestre', libelle: 'Trimestre en cours' }, { code: 'annee', libelle: 'Année en cours' },
  { code: 'perso', libelle: 'Personnalisée' },
];
export const NIVEAUX_360 = [
  { code: 'FAIBLE', libelle: 'Faible' }, { code: 'MOYEN', libelle: 'Moyen' }, { code: 'ELEVE', libelle: 'Élevé' },
  { code: 'INTERDIT', libelle: 'Interdit' }, { code: 'NON_EVALUE', libelle: 'Non évalué' },
];
export const PROFILAGES = [
  { code: 'EXPLOITABLE', libelle: 'Classification enregistrée' }, { code: 'NON_PROFILE', libelle: 'Non profilé' },
  { code: 'A_ARBITRER', libelle: 'Bloqué (conflit de référentiel)' },
];
/** Regroupements d’affichage des statuts existants du workflow d’alerte (aucun statut créé). */
export const GROUPES_ALERTE = [
  { code: 'A_EXAMINER', libelle: 'Correspondance potentielle à examiner', statuts: 'NOUVELLE · A_ANALYSER' },
  { code: 'EN_ANALYSE', libelle: 'En cours d’analyse (décision attendue)', statuts: 'EN_INVESTIGATION' },
  { code: 'CONFIRMEE', libelle: 'Correspondance confirmée', statuts: 'CONFIRMEE' },
  { code: 'ECARTEE', libelle: 'Écartée après examen', statuts: 'FAUX_POSITIF · REJETEE' },
  { code: 'CLOTUREE', libelle: 'Clôturée', statuts: 'CLOTUREE' },
];
export const FILTRAGES = [
  { code: 'SANS', libelle: 'Aucune correspondance' }, { code: 'AVEC', libelle: 'Au moins une correspondance' },
  ...GROUPES_ALERTE.map((g) => ({ code: g.code, libelle: g.libelle })),
];
export const LIB_NIVEAU: Record<string, string> = Object.fromEntries(NIVEAUX_360.map((x) => [x.code, x.libelle]));
export const LIB_PROFIL: Record<string, string> = { PP: 'Personne physique', PM: 'Personne morale', NON_IDENTIFIE: 'Non identifié' };

export interface Paire { valeur: number; precedente: number; }
export interface Anomalie360 { code: string; libelle: string; definition: string; famille: 'PROFILAGE' | 'COHERENCE' | 'DONNEES'; clients: number; }

export interface Synthese360 {
  reference: { stock_au: string | null; periode: { code: string; du: string; au: string; jours: number; precedente: { du: string; au: string } }; fuseau: string; genere_le: string; note: string };
  autorisations: { classification: boolean; audit: boolean };
  clients: { total: number; pp: number; pm: number; non_identifies: number };
  profilage: { exploitables: number; non_profiles: number; a_arbitrer: number; a_verifier: number; incomplets: number; dernier_classement: string | null; derniere_evaluation: string | null } | null;
  risque: Record<string, number> | null;
  risque_par_profil: { profil: string; niveau: string; clients: number }[] | null;
  filtrage: { clients_avec_correspondance: number; clients_sans_correspondance: number; clients_a_examiner: number; alertes: Record<string, number> };
  reexamens_ouverts: number | null;
  anomalies: Anomalie360[];
  alertes: {
    total: number; ouvertes: number; ouvertes_non_attribuees: number; en_attente_decision: number;
    par_statut: Record<string, number>; par_groupe: Record<string, number>; par_motif: Record<string, number>;
    par_source: Record<string, number>; anciennete_ouvertes: Record<string, number>; plus_ancienne_ouverte: string | null;
    priorite: { statut: string; message: string }; delais: { statut: string; message: string };
  };
  activite: {
    alertes_creees: Paire; decisions_alertes: Paire; classifications_enregistrees: Paire | null;
    premieres_classifications: Paire | null; changements_de_classe: Paire | null; note: string;
  };
  historique: { pas: string; classifications?: { jour: string; source: string; ecrits: number; premieres: number; changements: number }[]; alertes: { jour: string; creees: number; decisions: number }[] };
  sources_filtrage: SourcesFiltrage;
}

export interface SourcesFiltrage {
  dernier_scan: { le: string | null; par: string | null; alertes_creees: number | null } | null;
  clients_crees_depuis_scan: number | null;
  orion: { date_extraction: string | null; codes: { code: string; clients: number; comptes: number }[]; note: string };
  listes: { id: string; code: string; libelle: string; source: string; actif: boolean; entrees: number; creee_le: string | null; derniere_entree: string | null; preuve_import: boolean }[];
  note_listes: string;
}

export interface Client360 {
  racine_client: string; nom: string; prenoms: string | null; profil: string; code_agence: string | null; agence: string | null;
  nb_comptes: number; etat_client: string;
  classification: {
    niveau: string | null; source: string | null; mode_decision: string | null; score_enregistre: number | null; niveau_propose: string | null;
    motif_enregistre: string | null; motif_champ: string | null; classifie_le: string | null; version_regles: string | null;
    derniere_evaluation: { statut: string | null; niveau: string | null; score: number | null; le: string | null };
  } | null;
  completude: 'COMPLET' | 'INCOMPLET'; coherence: 'OK' | 'A_VERIFIER' | 'NON_EVALUE' | null; anomalies: string[];
  alertes: { a_examiner: number; en_analyse: number; confirmees: number; ecartees: number; cloturees: number; total: number };
  reexamens: number | null;
}

export interface PageClients360 { total: number; page: number; taille: number; items: Client360[]; }

export interface Alerte360 {
  id: string; racine_client: string; raison_sociale: string; profil: string; code_agence: string | null; statut: string; motif: string;
  source: 'ORION' | 'LISTE'; score: number; precedent_faux_positif: boolean; assignee: string | null; assignee_id: string | null;
  created_at: string | null; updated_at: string | null; derniere_action: string | null; anciennete_jours: number | null;
  correspondance: Record<string, unknown>;
}
export interface PageAlertes360 { total: number; page: number; taille: number; items: Alerte360[]; par_statut: Record<string, number>; par_groupe: Record<string, number>; }
export interface Agent { id: string; nom: string; }

export const LIB_MOTIF_CHAMP: Record<string, string> = {
  motif_decision_manuelle: 'décision manuelle', motif_moteur: 'moteur', motif_source: 'fichier source',
  motif_risque: 'motif de risque', motif_classement: 'motif de classement',
};

export function pct(v: number | null | undefined, total: number | null | undefined): string {
  if (!total) return '—';
  return `${(((v ?? 0) / total) * 100).toLocaleString('fr-FR', { maximumFractionDigits: 1 })} %`;
}

export function variation(p: Paire | null | undefined): string {
  if (!p) return '';
  const d = p.valeur - p.precedente;
  if (!p.precedente) return p.valeur ? 'aucune donnée sur la période précédente' : 'identique à la période précédente';
  return `${d > 0 ? '+' : ''}${d.toLocaleString('fr-FR')} vs période précédente`;
}

export function jour(iso: string | null | undefined): string {
  return iso ? dateHeureFr(iso).split(' ')[0] : '—';
}

export function heure(iso: string | null | undefined): string {
  return iso ? dateHeureFr(iso).split(' ').slice(1).join(' ') : '';
}

/** Retire les clés vides pour l’URL et les appels API. */
export function nettoyer(f: Filtres360): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [k, v] of Object.entries(f)) if (v !== undefined && v !== null && v !== '') out[k] = String(v);
  return out;
}

/** Bornes identiques à `resoudre_periode` côté serveur (jours UTC = Africa/Nouakchott). */
export function bornesPeriode(f: Filtres360, aujourdhui = new Date()): { du: string; au: string } | null {
  const iso = (d: Date) => d.toISOString().slice(0, 10);
  const j = new Date(Date.UTC(aujourdhui.getUTCFullYear(), aujourdhui.getUTCMonth(), aujourdhui.getUTCDate()));
  const moins = (jours: number) => new Date(j.getTime() - jours * 86_400_000);
  switch (f.periode) {
    case 'perso': return f.du && f.au ? { du: f.du, au: f.au } : null;
    case 'jour': return { du: iso(j), au: iso(j) };
    case '7j': return { du: iso(moins(6)), au: iso(j) };
    case 'trimestre': return { du: iso(new Date(Date.UTC(j.getUTCFullYear(), 3 * Math.floor(j.getUTCMonth() / 3), 1))), au: iso(j) };
    case 'annee': return { du: iso(new Date(Date.UTC(j.getUTCFullYear(), 0, 1))), au: iso(j) };
    default: return { du: iso(moins(29)), au: iso(j) };
  }
}

export function filtresPopulation(f: Filtres360): Record<string, string> {
  const out: Record<string, string> = {};
  for (const k of CLES_POPULATION) if (f[k]) out[k] = f[k]!;
  return out;
}
