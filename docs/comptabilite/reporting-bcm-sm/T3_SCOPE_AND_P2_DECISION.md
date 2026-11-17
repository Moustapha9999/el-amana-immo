# T3 — Périmètre autorisé et décision P2

**Date :** 16/11/2026  
**Branche :** `feat/reporting-bcm-sm-t3`  

## 1. Conflit de périmètre (identifié, non tranché silencieusement)

| Source | Périmètre T3 |
|--------|----------------|
| `T2_dossier_conception.md` §3 / §14 | T3 = **socle** (accueil, campagnes, permissions, audit) ; imports/moteur = T4+ |
| `T3_IMPLEMENTATION_PLAN.md` | Socle uniquement ; exclus : imports, mapping, moteur, Excel, workflow complet |
| `T3_PRE_IMPLEMENTATION_REVIEW.md` | OPTION 2 — démarrage partiel T3-A |
| **Prompt d’implémentation du 16/11/2026** | « Implémentation complète » modules A–J (campagnes → exports) |

**Conséquences :** le prompt élargit T3 au chantier complet anciennement T3–T15.  
**Résolution appliquée :** suivre le prompt d’autorisation explicite (développement complet), tout en respectant les **décisions métier ouvertes** (D01–D22) : pas d’activation silencieuse, pas de constantes ECART, mapping en `A_VALIDER`, B/C provisoires, PDF bloqué sans DSI.

Les documents historiques T2/T3 **ne sont pas réécrits** ; ce fichier trace le conflit.

## 2. P1 — Code module

**Confirmé par le prompt :** `reporting-bcm-sm`.  
Le placeholder catalogue `reporting-compta` (statut `bientot`, sans `entry_path`) est **conservé** tel quel (reporting transverse générique) — pas de fusion silencieuse.

## 3. P2 — Unicité des campagnes (choix d’implémentation)

**Choix technique (aligné T2 dossier §4.2) :**

1. Contrainte SQL : `UNIQUE (bank_code, period_year, period_month, campaign_version)`.
2. Réouverture : nouvelle ligne avec `campaign_version = N+1`, `reopened_from_id` = ancienne campagne ; ancienne version figée lecture seule (`CLOTUREE` / historique).
3. Règle métier service : **au plus une campagne non clôturée** par `(bank_code, period_year, period_month)`.
4. Concurrence : contrainte UNIQUE + gestion `IntegrityError` → erreur métier 409 `DUPLICATE` / code dédié.

**Conséquences :**

- Les versions légitimes d’une même période restent possibles.
- Une contrainte `UNIQUE(bank, year, month)` seule aurait été incorrecte.
- Validation formelle Comptabilité/Archi toujours souhaitable ; en attendant, ce choix est celui du dossier T2 validé.

## 4. Environnement DEV (constat audit)

- Docker Desktop **non démarré** au moment de l’audit → `alembic current` / `upgrade` **non exécutables**.
- Head fichiers dépôt : `20261105_mg_stock_mvt_ref_uq` (mono-head).
- Production `v1.0.0` : **hors périmètre** (aucune connexion, migration, déploiement).

La migration `rbcm_01` est créée dans le dépôt ; son `upgrade` attend un PostgreSQL DEV disponible.
