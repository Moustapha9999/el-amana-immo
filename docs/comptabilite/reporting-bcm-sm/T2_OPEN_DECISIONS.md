# T2 — Décisions ouvertes

Reporting BCM SM (Comptabilité). Ne pas confondre avec BCM Clientèle.

Légende échéance : **B-T3** bloquant avant code T3 · **B-T4** avant imports/moteur · **B-PROD** avant mise en production · **FUTUR** amélioration.

| ID | Sujet | Responsable | Impact | Échéance | Bloque |
|----|-------|-------------|--------|----------|--------|
| P1 | Confirmer code module `reporting-bcm-sm` (vs `reporting-compta`) | Produit / Comptabilité | Catalogue, routes, perms | **B-T3** | Oui T3 |
| P2 | Une campagne active / période **ou** versions à chaque réouverture | Comptabilité / Archi | Unicité `rbcm_campaign` | **B-T3** | Oui schéma T3 minimal |
| D15 | Nature TOTDEB/TOTCRE (soldes individuels vs mouvements) | DSI / Comptabilité | Toutes règles D/C | **B-T4** | Moteur |
| D01 | Arbitrages mapping (202300/202400, 218000, 402, 913*, 580/585, 590/590200, 426, 122000) | Comptabilité | 115 règles | **B-PROD** (T6) | Activation mapping |
| D02 | Formaliser ECART / « selon le solde » | Comptabilité | COD / D38 | **B-PROD** | Activation ECART |
| D04 | Sources des 8 paramètres | Comptabilité / DSI | Params | **B-T4+** | Cellules mixtes |
| D05 | Listes publics / projets | Comptabilité | 322/323/403 | **B-T4+** | Idem |
| D06 | Traitement des 67 rubriques sans règle | Comptabilité | Finalisation | **B-PROD** | Gate BCM |
| D08 | Provisions 290000 / 356000 | Comptabilité | 131 / ratios | **B-PROD** | |
| D09 | Fichier crédits / dépôts | Comptabilité / DSI | ETAT B/C | **B-PROD** non forfaitaire | B/C réels |
| D10–D14 | Canevas / double comptage / FPN / circuit dépôt BCM | Conformité / DSI | Livrable | **B-PROD** | |
| D16–D17 | Résidence / correspondants | Comptabilité / Conformité | Colonnes SM | **B-PROD** | |
| D18–D22 | Liquidité, zéro, maturité, contrôles, conflit mapping | Conformité / Comptabilité | Ratios / contrôles | **B-PROD** | |
| REF-223 | Écart classes 1–8 oct. = 2 873 223 (COND) | Comptabilité | ECART période | Documenté T1 | Réf. historique |
| REF-218 | 2 873 218 non prouvé | Comptabilité | Clarifier | **FUTUR** / ticket | Non bloquant conception |
| DSI-LO | LibreOffice headless pour recalcul Excel | DSI | Formules classeur | **FUTUR** | Pas V1 |
| DSI-PDF | Conversion PDF approuvée | DSI | Livrable PDF | **FUTUR** | Pas V1 |
| DSI-SRV | Migration stockage hors `release-source` → `/srv` | DSI / Exploit | Fichiers | **B-T4** recommandé | Avant volumes SM |
| MATRICE | `Matrice_SM_cellule_regle_source.xlsx` | Claude / Comptabilité | 115 règles compte×cellule | **B-T6** | Précision mapping |
| SEPT | BAL + SM septembre | Comptabilité | Non-régression | **B-PROD** | Recette |
| ALEMBIC | `alembic heads` / `current` sur DB **dev** | Dev | 1ʳᵉ migration | **B-T3** exécution | Avant `upgrade` |

## Hypothèses de conception (non validées métier)

- `Numeric(18, 2)` pour montants MRU (aligné immobilisations) — **à confirmer** si devises exigent plus de décimales en stockage brut DET.
- SD/SC « métier » définis **par règle** (pas `MAX` global) — valeurs exactes après D15.
- Réouverture = nouvelle `campaign_version` liée à `reopened_from_id` — **P2**.

Ces hypothèses ne doivent pas être présentées comme décisions métier validées.
