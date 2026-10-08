export const CL_BASE = '/clientele';

export const MATRICE_LBC = 'Matrice des risques LBC/FT BEA';
export const FICHE_SCORING = 'Fiche de scoring';

export const SOURCES_LBC: Record<string, string> = {
  MATRICE_V1: MATRICE_LBC,
  SCORING_V4: FICHE_SCORING,
  SCORING_V4_LISTE: `${FICHE_SCORING} (listes)`,
  SCORING_V4_PAYS_ENG_FR: `${FICHE_SCORING} (pays)`,
  PROPOSITION_BEA_DIGITAL: 'Proposition BEA DIGITAL',
};

export const STATUTS_REGLE: Record<string, string> = {
  ALIGNEE: 'Alignée',
  SOURCE_V1: 'Matrice seule',
  SOURCE_V4: 'Fiche seule',
  A_ARBITRER: 'À arbitrer',
  A_CONFIGURER: 'À configurer',
  A_VERIFIER: 'À vérifier',
  VALIDEE_CDC: 'Validée CDC',
};

export function libSource(code: string | null | undefined): string {
  if (!code) return '—';
  return code.split('+').map((c) => SOURCES_LBC[c] ?? c).join(' + ');
}

export interface Capacites {
  voir: boolean;
  imports_voir: boolean;
  imports_executer: boolean;
  rapprochement_voir: boolean;
  rapprochement_executer: boolean;
  classif_voir: boolean;
  classif_executer: boolean;
  classif_admin: boolean;
  filtrage_voir: boolean;
  filtrage_executer: boolean;
  filtrage_decider: boolean;
  reporting_voir: boolean;
  bcm_voir: boolean;
  bcm_preparer: boolean;
  bcm_valider: boolean;
  bcm_cloturer: boolean;
  exporter: boolean;
  admin: boolean;
}

export interface SourceColonne {
  colonne: string;
  source: string;
  champ: string | null;
  detail: string;
}

export interface AgenceRef {
  code: string;
  libelle: string;
}

export interface ClConfig {
  capacites: Capacites;
  sources: SourceColonne[];
  agences: AgenceRef[];
}

export interface TableauBord {
  nb_clients: number;
  nb_comptes: number;
  pp: number;
  pm: number;
  non_identifies: number;
  ouverts: number;
  clotures: number;
  sources: SourceColonne[];
}

export interface SituationLigne {
  racine_client: string;
  nom_client: string;
  prenoms: string | null;
  nationalite: string | null;
  statut_resident: string | null;
  nni: string | null;
  nif: string | null;
  categorie_juridique: string | null;
  agent_economique: string | null;
  profil_derive: string;
  etat_client: string;
  date_ouverture: string | null;
  code_agence: string | null;
  agence: string | null;
  nb_comptes: number;
  nb_comptes_ouverts: number;
  nb_agences: number;
}

export interface PageSituation {
  total: number;
  page: number;
  taille: number;
  items: SituationLigne[];
}

export interface CompteFiche {
  compte: string;
  rib: string;
  etat_compte: string;
  devise: string;
  ncg: string | null;
  code_agence: string | null;
  agence: string | null;
  date_ouverture: string | null;
  ddc: string | null;
  ddd: string | null;
  conformite_compte: string | null;
}

export interface FicheClient {
  client: Record<string, string | null>;
  situation: SituationLigne | null;
  comptes: CompteFiche[];
  dernier_import: { id: string; fichier_nom: string; importe_le: string | null } | null;
  classification: {
    niveau: string; source: string; motif_risque: string | null; motif_classement: string | null;
    motifs: { critere?: string; libelle?: string; motif?: string }[]; classifie_le: string | null;
  } | null;
  alertes_ouvertes: { id: string; statut: string; motif: string; precedent_faux_positif: boolean }[];
  sources: SourceColonne[];
}

export interface ColonneMapping {
  champ: string;
  libelle: string;
  entete: string;
  obligatoire: boolean;
}

export interface AnalyseImport {
  feuille: string;
  ligne_entete: number;
  mapping: Record<string, string>;
  colonnes: ColonneMapping[];
  colonnes_ignorees: string[];
  colonnes_manquantes: string[];
  champs_disponibles: string[];
  apercu: Record<string, string | number>[];
  stats: Record<string, number | Record<string, number>>;
  apercu_ecriture: {
    clients_a_creer: number;
    clients_a_mettre_a_jour: number;
    comptes_a_creer: number;
    comptes_a_mettre_a_jour: number;
    comptes_absents_du_fichier: number;
  };
  deja_importe: { id: string; le: string | null } | null;
}

export interface ImportClientele {
  id: string;
  fichier_nom: string;
  statut: string;
  nb_lignes: number;
  nb_clients: number;
  nb_comptes: number;
  nb_rejets: number;
  nb_anomalies: number;
  clients_crees: number | null;
  clients_maj: number | null;
  comptes_crees: number | null;
  comptes_maj: number | null;
  created_at: string | null;
  importe_le: string | null;
  auteur: string | null;
  resultat: Record<string, number> | null;
  stats: Record<string, number> | null;
  analyse?: AnalyseImport;
}

export interface AnomaliePage {
  total: number;
  page: number;
  taille: number;
  items: { numero: number; racine_client: string | null; code: string; message: string; bloquante: boolean }[];
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

export function n(v: number | null | undefined): string {
  return (v ?? 0).toLocaleString('fr-FR');
}

export function valeurIndic(statut: string, valeur: number | null | undefined): string {
  if (statut === 'A_CONFIGURER' || valeur === null || valeur === undefined) return 'À CONFIGURER';
  return n(valeur);
}

export function telecharger(blob: Blob, nom: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = nom;
  a.click();
  URL.revokeObjectURL(url);
}
