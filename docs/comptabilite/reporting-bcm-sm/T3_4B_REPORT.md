# T3.4-B — Refonte UI/UX et complétude fonctionnelle

Branche : `feat/reporting-bcm-sm-t3` · **Aucun commit / push / déploiement.**

Audit préalable : `T3_4B_AUDIT.md` · Base métier : T3.4-A2 (BAL DET source unique).

## Verdict

Refonte UI/UX livrée sur DEV pour les écrans du module. KPI Accueil alignés BAL DET (front + API). CRUD / actions critiques câblés côté API. Tests automatisés module : **21 passed, 1 skipped**. Tests métier manuels exhaustifs **non démarrés** (attente validation UI).

## Audit initial → corrections

| Écran | Objectif | Corrections T3.4-B | État |
|-------|----------|--------------------|------|
| Accueil | Pilotage | En-tête / 8 KPI / 6 étapes / graphiques réels / activité DET | OK DEV |
| Campagnes | CRUD | Liste filtrée, ⋮ Supprimer si BROUILLON, delete-check backend | OK (à valider delete vide) |
| Nouvelle | Création | `bea-mg__field`, mois select | OK |
| Fiche | Hub | Sections métier, export+download, lien Archives COND | OK |
| Imports | DET seul | Upload DET, analyse, historique paginé, pas d’upload COND | OK |
| BAL DET | Lecture | Recherche / filtres / pager backend, lien Imports | OK (debounce restant) |
| Contrôles | DET interne | UI Contrôles, CSV via ApiService | OK (pager issues restant) |
| Paramètres | 8 fiches | Drawer bea-mg, propose→confirm caisse | OK |
| Correspondances | Lecture | `{items,total}`, pager, 242 A_VALIDER | OK |
| Archives COND | Lecture hors workflow | Route conservée, hors nav, lien fiche | OK |

## Pages / composants harmonisés

- Chrome `bea-mg` / `bea-fx` (pas de nouveau design system).
- `ViewEncapsulation.None` + styles RBCM partagés (grille formulaire, champs).
- Nav : Accueil, Campagnes, Imports, BAL DET, Contrôles, Paramètres, Correspondances — **pas de BAL COND**.
- Feedback : FeedbackService / UiDialogService (pas d’`alert`).

## Accueil — vérifié DEV

Campagne `11/2026 · v1 · Calculée` :

- **BAL DET OK = 1** (DB : 1 DET VALIDATED + 1 COND VALIDATED archives).
- Donut imports : **BAL DET (1)** uniquement.
- Derniers imports : DET seul (« Confirmé »).
- Mapping : **A_VALIDER (242)**.
- Progression campagne affichée (6 étapes).
- KPI backend filtrés DET (`imports_validated`, anomalies, évolution mensuelle).

## CRUD / suppressions

| Action | Backend | UI | Note |
|--------|---------|----|------|
| Créer campagne | Oui | Nouvelle + Accueil | Formulaire harmonisé |
| Voir / Fiche | Oui | Liste + Accueil | Sections |
| Modifier / version / réouvrir | Endpoints | Partiel | Motifs selon statut |
| Archiver | Oui | Menu | |
| Supprimer | `delete-check` + DELETE | Menu si BROUILLON | Décision backend ; dépendances affichées si refus |
| Historique | Audit conservé | Fiche | Pas de contournement |

## Imports / BAL DET / Contrôles

- Workflow : Analyser → prévisualiser → confirmer → détails / anomalies / historique / download / remplacement contrôlé.
- BAL DET : pagination backend, lecture seule des lignes.
- Contrôles : contrôles internes DET (pas de rapprochement DET/COND actif).

## Drawers / pagination / responsive

- Drawers paramètres / détails : contexte liste conservé à la fermeture.
- Pagers : campagnes, imports, BAL DET, mapping (total API).
- Responsive multi-largeurs : **à revalider manuellement** (1920→768) après rebuild.
- Animations sobres + `prefers-reduced-motion` dans styles partagés.

## Graphiques Accueil

- Campagnes par statut (labels FR).
- Imports validés (DET).
- Mapping (A_VALIDER).
- Évolution mensuelle DET.
- Anomalies (codes contrôles).
- Activité récente campagnes + imports DET.

## Tests

```
21 passed, 1 skipped  (test_reporting_bcm_sm.py via /tmp — tests exclus de l’image Docker)
```

Vérifs UI DEV faites : Accueil KPI DET, Campagnes liste, Imports DET-only.

**Non rejoué exhaustivement** (attente validation UI) : suppression BROUILLON vide, refus avec dépendances, export Excel fichier, propose/apply caisse, CSV contrôles auth, matrix responsive, Playwright.

## Problèmes restants (transparents)

> **T3.4-C** traite ou documente ces points : voir `T3_4C_REPORT.md`.

1. Boutons workflow métier — verrouillés UI avec D01/D02 (T3.4-C).
2. Debounce recherche BAL DET / Imports — T3.4-C.
3. Preview analyse Imports structurée — T3.4-C.
4. Pagination issues Contrôles — T3.4-C.
5. Playwright DEV — `e2e/reporting-bcm-sm/` (T3.4-C).
6. KPI « Ouvertes » / `CALCULEE` — corrigé T3.4-C.
7. Captures avant/après non archivées en fichiers dédiés (vérif navigateur DEV uniquement).

## Migrations / données

Aucune migration destructive T3.4-B. Mapping list shape évolutive `{items,total,…}`. Historique COND et audit conservés.

## État Git

Branche dirty `feat/reporting-bcm-sm-t3`. Pas de commit. Images DEV rebuild frontend + backend après correctifs KPI Accueil.
