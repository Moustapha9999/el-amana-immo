/** Formats de pièces jointes acceptés dans toute la plateforme (miroir de backend/app/core/fichiers.py). */
export const PIECES_EXTENSIONS = ['pdf', 'doc', 'docx', 'xls', 'xlsx', 'jpg', 'jpeg', 'png', 'webp', 'gif', 'tif', 'tiff'] as const;

export const PIECES_ACCEPT = PIECES_EXTENSIONS.map((e) => `.${e}`).join(',');

export const PIECES_FORMATS_LABEL = 'PDF, Word, Excel ou image scannée';

export const PIECES_TAILLE_MAX = 25 * 1024 * 1024;

export type PieceNature = 'pdf' | 'word' | 'excel' | 'image' | 'autre';

export function extensionFichier(nom: string | null | undefined): string {
  const m = /\.([a-z0-9]+)$/i.exec(nom ?? '');
  return m ? m[1].toLowerCase() : '';
}

export function naturePiece(nom: string | null | undefined, mime?: string | null): PieceNature {
  const ext = extensionFichier(nom);
  const m = (mime ?? '').toLowerCase();
  if (ext === 'pdf' || m === 'application/pdf') return 'pdf';
  if (['doc', 'docx'].includes(ext) || m.includes('word')) return 'word';
  if (['xls', 'xlsx'].includes(ext) || m.includes('excel') || m.includes('spreadsheet')) return 'excel';
  if (m.startsWith('image/') || ['jpg', 'jpeg', 'png', 'webp', 'gif', 'tif', 'tiff'].includes(ext)) return 'image';
  return 'autre';
}

export function iconePiece(nom: string | null | undefined, mime?: string | null): string {
  return { pdf: 'picture_as_pdf', word: 'article', excel: 'table_chart', image: 'image', autre: 'description' }[
    naturePiece(nom, mime)
  ];
}

/** Message d'erreur prêt à afficher, ou null si le fichier est acceptable. */
export function verifierPieceJointe(file: File): string | null {
  if (!(PIECES_EXTENSIONS as readonly string[]).includes(extensionFichier(file.name))) {
    return `Format refusé. Formats acceptés : ${PIECES_FORMATS_LABEL} (${PIECES_EXTENSIONS.map((e) => '.' + e).join(', ')}).`;
  }
  if (file.size === 0) return 'Fichier vide.';
  if (file.size > PIECES_TAILLE_MAX) return 'Fichier trop volumineux (25 Mo maximum).';
  return null;
}
