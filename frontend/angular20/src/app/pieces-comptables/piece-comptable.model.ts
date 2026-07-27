export interface PieceComptable {
  id: string;
  immobilisation_id: string;
  filename: string;
  mime_type: string | null;
  size_bytes: number;
  is_photo: boolean;
  type_piece: string;
  date_journee: string;
  reference: string | null;
  libelle: string | null;
  montant: number | string | null;
  created_at: string | null;
  code_inventaire: string | null;
  designation: string | null;
}
