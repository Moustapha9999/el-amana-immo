import { UserProfile } from '../../core/services/auth.service';

export type InventaireStatut = 'BROUILLON' | 'EN_COURS' | 'A_CONTROLER' | 'VALIDE' | 'AJUSTE' | 'ARCHIVE' | 'ANNULE';
export type LigneStatut = 'NON_COMPTE' | 'CONFORME' | 'ECART_NEGATIF' | 'ECART_POSITIF' | 'EXCLU';
export type LigneFiltre =
  | '' | 'non_compte' | 'compte' | 'conforme' | 'negatif' | 'positif' | 'ecart' | 'exclu'
  | 'a_regulariser' | 'ajustement';

export interface InventaireStats {
  total: number;
  a_compter: number;
  comptes: number;
  non_comptes: number;
  exclus: number;
  sans_ecart: number;
  ecarts_negatifs: number;
  ecarts_positifs: number;
  total_theorique: number;
  total_physique: number;
  ecart_net: number;
  progression: number;
  total_systeme: number;
  total_retenu: number;
  ajustement_net: number;
  ajustements_prevus: number;
  a_regulariser: number;
  ecart_a_regulariser: number;
  rapprochement: boolean;
}

export interface RapprochementMeta {
  fichier?: string;
  source_officielle?: string | null;
  source_libelle?: string;
  date_inventaire?: string | null;
  date_comptage?: string | null;
  charge_at?: string;
  attendu?: Record<string, unknown>;
  controle?: { ok: boolean; echecs: string[]; at: string };
}

export interface Controle {
  code: string;
  libelle: string;
  attendu: number | string;
  obtenu: number | string;
  ok: boolean;
  en_attente: boolean;
}

export interface EcartARegulariser {
  ligne_id: string;
  code: string;
  designation: string;
  theorique_reference: number;
  stock_retenu: number;
  stock_physique: number;
  ecart: number;
  statut: 'A_REGULARISER';
  decision: string;
}

export interface Rapprochement {
  controles: Controle[];
  ok: boolean;
  en_attente: boolean;
  registre_ecarts: EcartARegulariser[];
}

export interface Inventaire {
  id: string;
  reference: string;
  libelle: string;
  date_debut: string;
  date_fin: string | null;
  annee: number | null;
  mois: number | null;
  periode_libelle: string | null;
  agence_id: string | null;
  agence_libelle: string | null;
  famille_id: string | null;
  famille_libelle: string | null;
  responsable_id: string | null;
  responsable_nom: string | null;
  statut: InventaireStatut;
  observation: string | null;
  source: 'MANUEL' | 'IMPORT_EXCEL';
  import_meta: {
    fichier?: string;
    resume?: Record<string, number>;
    importe_at?: string;
    rapprochement?: RapprochementMeta;
  } | null;
  snapshot_at: string | null;
  created_at: string | null;
  created_by_nom: string | null;
  updated_at: string | null;
  valide_at: string | null;
  valide_by_nom: string | null;
  validation_forcee: boolean;
  ajustements_at: string | null;
  ajustements_by_nom: string | null;
  cloture_at: string | null;
  annule_at: string | null;
  motif_annulation: string | null;
  stats: InventaireStats;
  mouvements_depuis: number;
  nb_ajustements: number;
}

export interface InventaireLigne {
  id: string;
  article_id: string;
  stock_theorique: number;
  stock_physique: number | null;
  ecart: number | null;
  ecart_absolu: number | null;
  ecart_pourcentage: number | null;
  observation: string | null;
  sort_order: number;
  statut_comptage: 'NON_COMPTE' | 'COMPTE' | 'EXCLU';
  statut_ligne: LigneStatut;
  compte_par_nom: string | null;
  compte_at: string | null;
  stock_theorique_source: number | null;
  theorique_reference: number | null;
  stock_cible: number | null;
  ajustement_prevu: number | null;
  ecart_a_regulariser: number | null;
  a_regulariser: boolean;
  ancienne_agence: boolean;
  donnees_source: Record<string, string | number | boolean | null> | null;
  ajout_manuel: boolean;
  updated_at: string | null;
  article_code: string | null;
  article_reference: string | null;
  article_designation: string | null;
  famille_libelle: string | null;
  unite: string | null;
  emplacement: string | null;
}

export interface InventaireHistorique {
  id: string;
  created_at: string;
  action: string;
  entity: string;
  user_nom: string | null;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
}

export interface InventaireSynthese {
  dernier: Inventaire | null;
  en_cours: Inventaire | null;
  nb_en_cours: number;
  nb_a_controler: number;
  nb_total: number;
}

export interface ValidationPreview {
  total: number;
  a_compter: number;
  comptes: number;
  non_comptes: number;
  exclus: number;
  ecarts: number;
  ecarts_negatifs: number;
  ecarts_positifs: number;
  ecart_net: number;
  mouvements_depuis: number;
  peut_valider: boolean;
  peut_forcer: boolean;
  message: string | null;
}

export interface Ajustement {
  id: string;
  reference: string;
  date_mouvement: string;
  quantite: number;
  article_code: string;
  article_designation: string;
  observation: string | null;
}

export interface Paginated<T> {
  items: T[];
  total: number;
  page: number;
  size: number;
}

export interface RefOption {
  id: string;
  libelle: string;
}

export const STATUT_LABELS: Record<InventaireStatut, string> = {
  BROUILLON: 'Brouillon',
  EN_COURS: 'En cours',
  A_CONTROLER: 'À contrôler',
  VALIDE: 'Validé',
  AJUSTE: 'Ajusté',
  ARCHIVE: 'Archivé',
  ANNULE: 'Annulé',
};

export const STATUT_ICONS: Record<InventaireStatut, string> = {
  BROUILLON: 'edit_note',
  EN_COURS: 'fact_check',
  A_CONTROLER: 'rule',
  VALIDE: 'verified',
  AJUSTE: 'published_with_changes',
  ARCHIVE: 'inventory_2',
  ANNULE: 'block',
};

export const LIGNE_LABELS: Record<LigneStatut, string> = {
  NON_COMPTE: 'Non compté',
  CONFORME: 'Conforme',
  ECART_NEGATIF: 'Écart négatif',
  ECART_POSITIF: 'Écart positif',
  EXCLU: 'Exclu',
};

export const ACTION_LABELS: Record<string, string> = {
  create: 'Création',
  import_excel: 'Import Excel',
  update: 'Modification',
  demarrer: 'Démarrage du comptage',
  soumettre: 'Soumis au contrôle',
  reprendre: 'Renvoyé en comptage',
  valider: 'Validation',
  generer_ajustements: 'Ajustements générés',
  archiver: 'Archivage',
  annuler: 'Annulation',
  delete: 'Suppression',
  saisie_physique: 'Saisie du stock physique',
  ajout_ligne: 'Article ajouté',
  suppression_ligne: 'Article retiré',
  chargement_reference: 'Référence de rapprochement chargée',
  rapprochement: 'Rapprochement du stock',
};

export const MOIS = [
  'Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin',
  'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre',
];

export const VERROUILLES: ReadonlySet<InventaireStatut> = new Set(['VALIDE', 'AJUSTE', 'ARCHIVE', 'ANNULE']);
export const MSG_VERROU = 'Cet inventaire est clôturé. Les données ne peuvent plus être modifiées.';

export const PERM = {
  saisie: 'mg.stock.inventory',
  validation: 'mg.stock.inventory.validate',
  ajustement: 'mg.stock.inventory.adjust',
  gestion: 'mg.stock.inventory.manage',
  export: 'mg.stock.export',
} as const;

/** Miroir de `user_has_permission_codes` : `*`, superuser, code exact ou `<segment>.admin`. */
export function aPermission(user: UserProfile | null, code: string): boolean {
  if (!user) return false;
  if (user.is_superuser) return true;
  const codes = user.permission_codes ?? [];
  return codes.includes('*') || codes.includes(code) || codes.includes(`${code.split('.')[0]}.admin`);
}

export function signe(n: number | null | undefined): string {
  if (n == null) return '—';
  const v = Number(n);
  return v > 0 ? `+${v.toLocaleString('fr-FR')}` : v.toLocaleString('fr-FR');
}

export function pourcentage(p: number | null | undefined): string {
  if (p == null) return 'n/d';
  return `${p > 0 ? '+' : ''}${p.toLocaleString('fr-FR', { maximumFractionDigits: 2 })} %`;
}

export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
