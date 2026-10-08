/** EER — Gestion des Entrées en Relation (Conformité & sécurité financière → KYC). */

export interface EerPerimetre {
  user_id: string;
  agence_id: string | null;
  perimetre: 'TOUTES_AGENCES' | 'AGENCE' | 'AUCUN';
  roles: string[];
  permissions: string[];
  capacites: Record<string, boolean>;
}

export interface EerDossierLigne {
  id: string;
  reference: string;
  statut: string;
  etape: string | null;
  operation_type: string;
  agence_id: string;
  agence_code: string;
  agence_libelle: string;
  type_client: string;
  profil: string;
  client_nom: string;
  racine_client: string | null;
  risque: string | null;
  decision: string | null;
  avis_requis: boolean;
  analyste_id: string | null;
  analyste_nom: string | null;
  version_courante: number;
  revision: number;
  date_eer: string;
  soumis_le: string | null;
  valide_le: string | null;
  created_at: string;
  updated_at: string;
  sous_profil: string | null;
  ppe: boolean;
  fatca: boolean;
  etat_compte: string | null;
  conformite_physique: string | null;
  conformite_systeme: string | null;
  conformite_excel: EerClassement;
  code_conforme: number;
  code_non_conforme: number;
  conformite_bea: EerClassement;
}

/** Classement dérivé (jamais saisi) : référence Excel M/N ou décision BEA-DIGITAL. */
export type EerClassement = 'CONFORME' | 'NON_CONFORME' | 'NON_EVALUE';

export const CLASSEMENTS: Record<EerClassement, string> = {
  CONFORME: 'Conforme',
  NON_CONFORME: 'Non conforme',
  NON_EVALUE: 'Non évalué',
};

export const ETATS_COMPTE: Record<string, string> = {
  ACTIF: 'Actif',
  INACTIF: 'Inactif',
  BLOQUE: 'Bloqué',
  FERME: 'Fermé',
};

export interface EerPage<T> {
  items: T[];
  total: number;
  page: number;
  size: number;
}

export interface EerPartie {
  dossier_partie_id: string;
  partie_id: string;
  role: string;
  nature: string;
  nom: string;
  ordre: number;
  ppe: boolean | null;
  fatca_indice: boolean | null;
  risque_lbcft: string | null;
  be_source: string | null;
  be_pourcentage_calcule: string | null;
}

export interface EerDossier {
  id: string;
  reference: string;
  statut: string;
  etape: string | null;
  operation_type: string;
  agence_id: string;
  type_client: string;
  profil: string;
  sous_profil: string | null;
  risque: string | null;
  ppe: boolean;
  fatca: boolean;
  avis_requis: boolean;
  conformite_physique: string | null;
  conformite_systeme: string | null;
  conformite_coherence: string | null;
  decision: string | null;
  etat_compte: string | null;
  conformite_excel: EerClassement;
  code_conforme: number;
  code_non_conforme: number;
  conformite_bea: EerClassement;
  divergence: boolean;
  version_courante: number;
  revision: number;
  nb_relances: number;
  motif_abandon: string | null;
  parametres_snapshot: Record<string, unknown>;
  created_by_id: string;
  analyste_id: string | null;
  controleur_id: string | null;
  date_eer: string;
  soumis_le: string | null;
  valide_le: string | null;
  archived_at: string | null;
  created_at: string;
  updated_at: string;
  racine_client: string | null;
  numero_compte: string | null;
  parties: EerPartie[];
  transitions_possibles: string[];
}

export interface EerMutation {
  id: string;
  statut: string;
  etape: string | null;
  revision: number;
  version_courante: number;
  message: string;
}

export interface EerChecklistItem {
  id: string;
  regle_code: string;
  regle_version: number;
  dossier_partie_id: string | null;
  libelle: string;
  categorie: string;
  axe: string;
  nature: string;
  obligatoire: boolean;
  ordre: number;
  statut: string;
  presence: string | null;
  motif: string | null;
  motif_code: string | null;
  neutralise_auto: boolean;
  derogation_acceptee: boolean;
  raison_applicabilite: string[];
  document_id: string | null;
  pointe_le: string | null;
  controle_le: string | null;
  donnee_connue: boolean | null;
}

export interface EerChecklist {
  dossier_id: string;
  etape: string | null;
  revision: number;
  items: EerChecklistItem[];
  non_pointes: number;
}

export interface EerFicheChamp {
  chemin: string;
  libelle: string;
  section: string | null;
  obligatoire: boolean;
  etat: string;
  valeur: unknown;
  bloquant: boolean;
  source?: string | null;
}

export interface EerControle {
  id: string;
  item_id: string | null;
  code: string;
  type_controle: string;
  resultat: string;
  detail: Record<string, unknown>;
  version: number;
  execute_par_id: string | null;
  execute_le: string;
}

export interface EerDecision {
  id: string;
  version: number;
  resultat: string;
  conformite_physique: string;
  conformite_systeme: string;
  conformite_coherence: string;
  explication: string[];
  decide_le: string;
}

export interface EerConstat {
  code: string;
  type_controle: string;
  resultat: string;
  message: string;
  item_id: string | null;
  detail: Record<string, unknown>;
}

export interface EerAnomalie {
  id: string;
  item_id: string | null;
  champ: string | null;
  type_code: string;
  gravite: string;
  description: string;
  observation: string | null;
  action_attendue: string | null;
  statut: string;
  justification: string | null;
  version_detection: number;
  version_resolution: number | null;
  created_at: string;
}

export interface EerComplement {
  id: string;
  numero: number;
  origine: string;
  consigne: string | null;
  echeance: string | null;
  statut: string;
  version_demande: number;
  recu_le: string | null;
  created_at: string;
  elements: Array<{ id: string; item_id: string | null; anomalie_id: string | null; champ: string | null; fourni: boolean }>;
}

export interface EerVisa {
  id: string;
  user_id: string;
  fonction: string;
  avis: string;
  commentaire: string | null;
  version: number;
  vise_le: string;
}

export interface EerVersionLigne {
  id: string;
  numero: number;
  evenement: string;
  empreinte: string;
  cree_par_id: string | null;
  cree_le: string;
}

export interface EerVersion extends EerVersionLigne {
  contenu: Record<string, unknown>;
  empreinte_verifiee: boolean;
}

export interface EerHistorique {
  id: string;
  action: string;
  de_statut: string | null;
  vers_statut: string | null;
  etape: string | null;
  version: number;
  motif: string | null;
  details: Record<string, unknown>;
  acteur_id: string | null;
  cree_le: string;
}

export interface EerDocument {
  id: string;
  filename: string;
  title: string | null;
  doc_type: string | null;
  mime_type: string | null;
  size_bytes: number;
  version: number;
  created_at: string;
  elements: string[];
}

export interface EerTypeDocument {
  code: string;
  libelle: string;
}

export type EerFormatExport = 'pdf' | 'xlsx';

export interface EerAudit {
  id: string;
  action: string;
  user_id: string | null;
  created_at: string;
  after: Record<string, unknown> | null;
}

export interface EerRepartition {
  code: string | null;
  libelle: string | null;
  total: number;
}

export interface EerTableauDeBord {
  total: number;
  en_cours: number;
  brouillons: number;
  a_affecter: number;
  affectes: number;
  en_controle: number;
  non_conformes: number;
  a_completer: number;
  conformes: number;
  avis_en_attente: number;
  valides: number;
  abandonnes: number;
  delai_moyen_jours: number | null;
  par_statut: Record<string, number>;
  par_agence: EerRepartition[];
  par_profil: EerRepartition[];
  par_type_client: EerRepartition[];
  par_risque: EerRepartition[];
}

export interface EerConformite {
  dossier_id: string;
  version_courante: number;
  revision: number;
  conformite_physique: string | null;
  conformite_systeme: string | null;
  conformite_coherence: string | null;
  reference_excel: {
    classement: EerClassement;
    code_conforme: number;
    code_non_conforme: number;
    cellule_m: string | null;
    cellule_n: string | null;
  };
  decision_bea: string | null;
  conformite_bea: EerClassement;
  anomalies_bloquantes: Array<{ id: string; type_code: string; description: string; statut: string }>;
  divergence: boolean;
  explication_ecart: string[];
  observations: string | null;
  derniere_decision: EerDecision | null;
}

/** Taux = conformes / (conformes + non conformes) en % ; null = non calculable (aucun classé). */
export interface EerKpiConformite {
  total: number;
  conformes: number;
  non_conformes: number;
  non_evalues: number;
  taux: string | null;
}

export interface EerKpiBloc {
  total: number;
  excel: EerKpiConformite;
  bea: EerKpiConformite;
  divergences: number;
}

export interface EerKpiGlobal extends EerKpiBloc {
  nature: string;
  flux: {
    recus: number;
    brouillons: number;
    en_cours: number;
    a_completer: number;
    abandonnes: number;
    abandonnes_apres_reception: number;
    taux_abandon: string | null;
  };
}

export interface EerKpiLigne extends EerKpiBloc {
  code: string | null;
  libelle: string | null;
  agence_id?: string | null;
  profil_technique?: string | null;
}

export interface EerKpiRepartition {
  nature: string;
  dimension?: string | null;
  lignes: EerKpiLigne[];
  total: EerKpiBloc;
}

export interface EerKpiEtatsCompte {
  nature: string;
  lignes: Array<{ code: string; libelle: string; nombre: number; pourcentage: string | null }>;
  total: number;
  non_renseignes: number;
}

export interface EerKpiSerie {
  nature: string;
  granularite: string;
  lignes: Array<EerKpiBloc & { periode: string }>;
}

export const STATUTS: Record<string, string> = {
  BROUILLON: 'Brouillon',
  SOUMIS: 'Soumis',
  A_AFFECTER: 'À affecter',
  AFFECTE: 'Affecté',
  EN_CONTROLE: 'En contrôle',
  CONFORME: 'Conforme',
  NON_CONFORME: 'Non conforme',
  A_COMPLETER: 'À compléter',
  RESOUMIS: 'Resoumis',
  AVIS_CONFORMITE: 'Avis Conformité KYC',
  VALIDE: 'Validé',
  CLOTURE: 'Clôturé',
  ARCHIVE: 'Archivé',
  ABANDONNE: 'Abandonné',
};

export const ETAPES: Record<string, string> = {
  CHECKLIST: 'Checklist',
  CHECKLIST_VALIDEE: 'Checklist validée',
  FICHES: 'Fiches',
  CONTROLES: 'Contrôles',
};

export const TYPES_CLIENT: Record<string, string> = {
  PP: 'Personne physique',
  PM_PRIVEE: 'Personne morale privée',
  PM_PUBLIQUE: 'Personne morale publique',
  ASSOCIATION: 'Association / ONG',
};

export const ELEMENT_STATUTS: Record<string, string> = {
  NON_CONTROLE: 'Non contrôlé',
  EN_COURS: 'En cours',
  CONFORME: 'Conforme',
  NON_CONFORME: 'Non conforme',
  MANQUANT: 'Manquant',
  NON_APPLICABLE: 'Non applicable',
  A_VERIFIER: 'À vérifier',
};

export const ROLES_PARTIE: Record<string, string> = {
  CLIENT: 'Client',
  MANDATAIRE: 'Mandataire',
  SIGNATAIRE_COMPTE: 'Signataire du compte',
  GERANT: 'Gérant',
  CO_GERANT: 'Co-gérant',
  SIGNATAIRE_ASSOCIATION: 'Signataire (association)',
  CO_SIGNATAIRE_ASSOCIATION: 'Co-signataire (association)',
  MEMBRE_DIRECTION: 'Membre de direction',
  ACTIONNAIRE: 'Actionnaire',
  BENEFICIAIRE_EFFECTIF: 'Bénéficiaire effectif',
  CONTACT_URGENCE: 'Contact d’urgence',
};

/** Actions de workflow simples (révision + motif facultatif) → route API et libellé. */
export const ACTIONS_WORKFLOW: Record<string, { route: string; label: string; icon: string; motif?: 'requis' | 'facultatif' }> = {
  SOUMIS: { route: 'submit', label: 'Soumettre au contrôle', icon: 'send' },
  EN_CONTROLE: { route: 'start-control', label: 'Démarrer le contrôle', icon: 'play_arrow' },
  AVIS_CONFORMITE: { route: 'request-avis', label: 'Demander l’avis KYC', icon: 'gavel' },
  RESOUMIS: { route: 'resubmit', label: 'Resoumettre (nouvelle version)', icon: 'replay' },
  CLOTURE: { route: 'close', label: 'Clôturer', icon: 'task_alt' },
  ARCHIVE: { route: 'archive', label: 'Archiver', icon: 'inventory_2' },
  ABANDONNE: { route: 'abandon', label: 'Abandonner', icon: 'block', motif: 'requis' },
};

/** Tonalité des badges `bea-ct-badge` existants pour un statut EER ou d'élément. */
export function eerTone(statut: string | null | undefined): string {
  switch (statut) {
    case 'VALIDE':
    case 'CONFORME':
    case 'CLOTURE':
    case 'FAVORABLE':
    case 'CORRIGEE':
    case 'CLOSE':
    case 'ACCEPTEE':
    case 'RECU':
      return 'ACTIF';
    case 'NON_EVALUE':
      return 'EXPIRE';
    case 'NON_CONFORME':
    case 'ABANDONNE':
    case 'MANQUANT':
    case 'DEFAVORABLE':
    case 'BLOQUANTE':
    case 'OUVERTE':
      return 'CRITIQUE';
    case 'A_COMPLETER':
    case 'A_AFFECTER':
    case 'AVIS_CONFORMITE':
    case 'A_VERIFIER':
    case 'MAJEURE':
    case 'EN_COMPLEMENT':
    case 'OUVERT':
      return 'ATTENTION';
    case 'ARCHIVE':
    case 'NON_APPLICABLE':
    case 'ANNULEE':
    case 'ANNULE':
      return 'EXPIRE';
    default:
      return 'INFO';
  }
}

export function libelle(table: Record<string, string>, code: string | null | undefined): string {
  if (!code) return '—';
  return table[code] ?? code;
}

export function telechargerBlob(blob: Blob, nom: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = nom;
  a.click();
  URL.revokeObjectURL(url);
}

export function dateFr(iso: string | null | undefined, heure = false): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return heure
    ? d.toLocaleString('fr-FR', { dateStyle: 'short', timeStyle: 'short' })
    : d.toLocaleDateString('fr-FR');
}

export function valeurAffichee(v: unknown): string {
  if (v === null || v === undefined || v === '') return '—';
  if (typeof v === 'boolean') return v ? 'Oui' : 'Non';
  return String(v);
}
