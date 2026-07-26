export interface ArchiveDossier {
  id: string;
  annee: number;
  libelle: string | null;
  created_at: string;
  nb_fichiers: number;
  nb_lignes: number;
  natures: string[];
}

export interface ArchiveFichier {
  id: string;
  kind: string;
  filename: string;
  mime_type: string | null;
  size_bytes: number;
  nature_code: string | null;
  parse_status: string;
  parse_error: string | null;
  lines_count: number;
  created_at: string;
}

export interface ArchiveDossierDetail extends ArchiveDossier {
  fichiers: ArchiveFichier[];
}

export interface ArchiveLigne {
  id: string;
  categorie_code: string;
  feuille: string | null;
  row_number: number;
  date_acquisition: string | null;
  quantite: number;
  designation: string;
  valeur_brute: number;
  taux: number | null;
  amt_n1: number;
  dotation: number;
  amt_fin: number;
  vnc: number;
  agence_label: string | null;
  is_report: boolean;
  source_kind: string;
}

export interface ArchiveTotaux {
  valeur_brute: number;
  amt_n1: number;
  dotation: number;
  amt_fin: number;
  vnc: number;
  nb_lignes: number;
}

export interface ArchiveNatureGroupe {
  nature_code: string;
  nature_label: string;
  lignes: ArchiveLigne[];
  totaux: ArchiveTotaux;
}

export interface ArchiveAcquisitions {
  annee: number;
  groupes: ArchiveNatureGroupe[];
  totaux: ArchiveTotaux;
}

export interface ArchiveNatureFolder {
  code: string;
  libelle: string;
  nb_fichiers: number;
  nb_lignes: number;
  valeur_brute: number;
  has_data: boolean;
}
