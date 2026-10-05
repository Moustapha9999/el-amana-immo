/** Impression navigateur d'un tableau (même rendu pour listes et rapports). */

export type Cellule = string | number | null | undefined;

const esc = (v: string) => v.replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;');

export function celluleTexte(c: Cellule): string {
  if (c === null || c === undefined) return '';
  if (typeof c === 'number') {
    return c.toLocaleString('fr-FR', { minimumFractionDigits: Number.isInteger(c) ? 0 : 2, maximumFractionDigits: 2 });
  }
  return c;
}

/** Retourne false si le navigateur a bloqué la fenêtre d'impression. */
export function imprimerTableau(titre: string, entetes: string[], lignes: Cellule[][], sousTitre?: string): boolean {
  const popup = window.open('', '_blank');
  if (!popup) return false;
  const head = entetes.map((h) => `<th>${esc(h)}</th>`).join('');
  const body = lignes
    .map((row) => `<tr>${row.map((c) => `<td${typeof c === 'number' ? ' class="n"' : ''}>${esc(celluleTexte(c))}</td>`).join('')}</tr>`)
    .join('');
  const sub = `${sousTitre ? esc(sousTitre) + ' · ' : ''}${lignes.length} ligne(s) · édité le ${new Date().toLocaleString('fr-FR')}`;
  popup.document.write(`<!DOCTYPE html><html><head><meta charset="utf-8"><title>${esc(titre)}</title>
    <style>@page{size:landscape;margin:12mm}body{font-family:sans-serif;padding:1rem;color:#0f172a}h1{font-size:16px;color:#1a5278;margin:0 0 4px}
    p{font-size:11px;color:#64748b;margin:0 0 10px}table{border-collapse:collapse;width:100%}td,th{border:1px solid #cbd5e1;padding:4px 6px;font-size:10.5px}
    th{background:#eef4f9;text-align:left}td.n{text-align:right;white-space:nowrap}tr:nth-child(even) td{background:#f8fafc}</style></head>
    <body><h1>BEA DIGITAL — ${esc(titre)}</h1><p>${sub}</p><table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>
    <script>window.onload=function(){window.print()}<\/script></body></html>`);
  popup.document.close();
  return true;
}
