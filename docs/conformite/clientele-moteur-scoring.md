# Moteur de classification LBC/FT — CDC 1.0

Date : 08/10/2026. Migrations `20261008_clientele_06` et `07` **uniquement**
sur `bea_digital_clientele_test` / `bea_digital_recette`. Base réelle
`bea_digital` inchangée. **Aucune classification massive. Aucune valeur ACTIVE.**

## Noms des sources

| Code interne (base, API) | Nom affiché |
| --- | --- |
| `MATRICE_V1`, `niveau_matrice`, `SOURCE_V1` | **Matrice des risques LBC/FT BEA** |
| `SCORING_V4`, `niveau_v4`, `SOURCE_V4` | **Fiche de scoring** |

Les codes restent stables (historique, migrations). Les textes renvoyés par
l’API passent par `app/data/clientele_sources.py` ; le front utilise
`SOURCES_LBC` / `STATUTS_REGLE` (`clientele.models.ts`).

## Écrans

- **Classification** : sous-onglets Clients classés, Simulation, Référentiel
  maître, Critères, Divergences, Versions (`?onglet=`).
- **Importer** (`/clientele/imports?source=`) :
  - `orion` — État des comptes ORION (assistant existant) ;
  - `situation` — classeur Situation des comptes PP & PM : reprise de la
    classe de risque (source `EXCEL_CONFORMITE`) ;
  - `liste` — tout fichier avec une colonne Racine client : contrôle
    (reconnue / inconnue / invalide / doublon), évaluation moteur (simulation,
    ≤ 2 000 racines), classement moteur ou niveau du fichier (motif
    obligatoire, manuels préservés sauf choix explicite), export.
  Fichier temporaire sur disque (`uploads/clientele/lots`, 7 jours), pas de
  table. API `/api/v1/clientele/lots/...`. Une racine absente n’est jamais créée.

## Décision de conception

```text
MATRICE DES RISQUES LBC/FT BEA  +  FICHE DE SCORING
        ↓
RÉFÉRENTIEL UNIQUE BEA DIGITAL (LOT 1)
        ↓
MOTEUR SCORE  (additif, une seule mécanique)
```

- **SCORE uniquement.** Pas de moteur concurrent `MAX_NIVEAU`.
- **INTERDIT** = blocage métier (`BLOCKING`), distinct de ÉLEVÉ = 100 000.
  Le score reste calculable ; le dossier est signalé bloquant.
- Une donnée absente n’est **jamais** FAIBLE.
- Un conflit V1/V4 n’est **jamais** fusionné silencieusement : identifié,
  documenté, exclu de la somme jusqu’à arbitrage.
- Classification permanente du client ≠ évaluation d’une opération.

## Seuils (CDC §4 — défaut Excel C39 corrigé)

| Score | Niveau |
|-------|--------|
| 0 critère évalué | NON CLASSÉ |
| score < 10 000 | FAIBLE |
| 10 000 ≤ score < 100 000 | MOYEN |
| score ≥ 100 000 | ÉLEVÉ |
| critère INTERDIT V1 | INTERDIT (blocage) |

Échelle de référence : FAIBLE = 100, MOYEN = 10 000, ÉLEVÉ = 100 000.

## Quatre familles

CLIENT · GÉOGRAPHIE · PRODUIT/SERVICE/OPÉRATION · CANAL

Le score client permanent additionne Client + géographie client.
Produit / canal / provenance / destination n’entrent dans le score
permanent que lorsqu’une source opérationnelle validée existe (aujourd’hui
`NON_DISPONIBLE`).

## Référentiel maître (LOT 1)

Chaque ligne : **Dimension → Critère → Valeur → Score V1 → Niveau V1 →
Score V4 → Niveau V4 → Score retenu → Niveau retenu → Source → Version →
Conflit → Statut → actif=false**.

- Géographie et 119 sous-secteurs : **V1** est le référentiel métier.
  V4 est un contrôle, jamais un remplacement silencieux.
- Canaux supplémentaires (DIGITAL, APPLICATION, WEB, INTERMEDIAIRE, AUTRE) :
  prévus techniquement, **aucun score inventé** (`A_CONFIGURER`).
- PM privée / SARL : **A_ARBITRER** (V1 MOYEN vs V4 100).

API : `GET /api/v1/clientele/classification/valeurs`

## Moteur

`backend/app/services/clientele/scoring.py`

1. Charger les données client (racine 6 chiffres).
2. Évaluer chaque critère (EVALUE / NON_DISPONIBLE / NON_APPLICABLE / A_VERIFIER).
3. Exclure de la somme : `A_ARBITRER`, `A_CONFIGURER`, `A_VERIFIER`, poids 0.
4. Additionner les scores des critères retenus, par famille.
5. Appliquer les seuils CDC.
6. Si un critère INTERDIT V1 matche → niveau final INTERDIT (score conservé).
7. Générer le motif à partir des règles réellement utilisées.
8. Enregistrer le snapshot (`clientele_classif_evaluations`) **sans écraser**
   la classification retenue.

## Ce que le moteur ne fait pas

- Inventer un niveau quand Matrice et V4 divergent.
- Traiter une donnée absente comme Faible.
- Classer FAIBLE s’il n’y a aucun critère évalué.
- Activer les valeurs du référentiel maître.
- Écrire une classification de production depuis `POST /classification/evaluer`.
- Charger 119 secteurs + 247 pays comme règles ACTIVE de production.

## Livrables

- `backend/app/data/clientele_classif_referentiel.json` : extraction brute.
- `backend/app/data/clientele_classif_matrice.py` : catalogue des critères.
- `backend/app/data/clientele_classif_valeurs.py` : référentiel maître LOT 1.
- `backend/app/services/clientele/scoring.py` : moteur SCORE.
- Tables : `clientele_classif_dimensions`, `_valeurs`, `_pays`, `_secteurs`,
  `_formes`, `_divergences`, `_evaluations`.
- API : `GET .../matrice`, `/valeurs`, `/divergences`, `POST /evaluer`, `/backtest`.

## Lots suivants (non activés)

LOT 2 Client · LOT 3 Géographie opérationnelle · LOT 4 Produit/opération ·
LOT 5 Canaux · LOT 6 snapshot/historique complet · LOT 7 administration
(versions, conflits, simulation) · LOT 8 reporting / BCM.
