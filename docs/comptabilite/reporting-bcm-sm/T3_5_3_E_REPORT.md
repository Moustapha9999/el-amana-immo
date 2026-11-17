# T3.5-3-E — Livraison UI documents

**DEV Docker local.** Pas de phase F. Pas de commit.

Date : 17/11/2026. Branche `feat/reporting-bcm-sm-t3` @ `091b57c`.

## Réalisé

- Section **Documents** dans le détail de SM (`bea-rbcm-campagne-documents`).
- WORK courant avec bandeau **DOCUMENT DE TRAVAIL — NON VALIDÉ**.
- Historique SUPERSEDED et exports GENERATED séparés.
- Téléchargement via `GET .../documents/{id}/download` uniquement (pas de régénération).
- Permissions UI : `view` pour consulter, `export` pour télécharger (backend autoritaire).
- Champ additif API D : `created_by_name` (affichage auteur).

## Tests

- `ng build` development : OK.
- Karma (Edge Headless) : **14 SUCCESS** (`rbcm-documents.spec` + `api-error.spec`).
- Image frontend DEV reconstruite.

## Hors périmètre (inchangé)

F (décisions), mapping, portes métier, PDF, `runner.py`, SM BEA 01/2026 et 11/2026.

**STOP. Attendre autorisation avant T3.5-3-F.**
