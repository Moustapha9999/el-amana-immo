# T2 — Validation finale

**Module :** Reporting BCM SM (Comptabilité) — distinct du BCM Clientèle  
**Date :** 16/11/2026  
**Branche de travail :** `chore/audit-nettoyage-pre-deploiement`  
**Commit de départ :** `091b57cf6cdd1a0ddbbb6171eda801df3b1b1a32`  
**Working tree initial :** propre  

## Documents consultés

- Rapport T0 (audit dépôt, accepté)
- Rapport T1 (consolidation métier, accepté)
- Brief T2 + corrections A–I (finalisation)
- Code réel : `backend/app/models/` (mixins, `Numeric(18,2)` immo, `clientele_declarations_bcm`, `ged_documents`, imports `fichier_sha256`), `api/deps.py`, `plateforme_catalogue.py`, `module-routing.contract.ts`, `FeedbackService`
- Fichiers métier oct. 2026 (BAL DET/COND, canevas, Correspondance, Maquette) — analyses T1

## Corrections intégrées dans le dossier T2 révisé

| Point | Correction |
|-------|------------|
| **A. Soldes** | D/C/SD/SC/solde signé distingués ; pas de généralisation `MAX(...)` ; bases **configurables** par règle ; D15 ouverte |
| **B. Décisions** | `rbcm_cell_decision` strictement append-only ; `supersedes_decision_id` ; pas de `superseded_at` mutatif |
| **C. ECART** | Calculé **par campagne** ; 2 873 223 / 2 873 218 = références historiques, **pas** constantes codées ; inactif sans D02 |
| **D. Excel** | Moteur Python = vérité ; openpyxl écrit cellules saisie seulement ; pas de recalcul formules ; pas de PDF natif sans DSI |
| **E. Workflow** | Préparateur / Contrôleur / Approbateur ; anti auto-approbation ; Login 2 + permissions CORE uniquement |
| **F. Données** | Un seul champ de cycle de vie mapping (`lifecycle_status`) ; campagnes versionnées à la réouverture ; `Numeric(18,2)` aligné immo (justifié) ; FK `RESTRICT` sur historiques ; SHA-256 + idempotence |
| **G. Imports** | Période/type/empreinte/version ; streaming DET ; rapprochements persistés ; import validé non écrasé |
| **H. Mapping** | 115 × `A_VALIDER` ; 67 ≠ zéro auto ; 3 sources + divergences D01 visibles |
| **I. Paramètres** | 8 codes ; pas de reconduction ; historique + justification |

## Points validés (conception)

- Intégration native BEA DIGITAL, code module `reporting-bcm-sm`, espace `comptabilite`
- Préfixe tables `rbcm_`, API `/api/v1/reporting-bcm-sm/`, UI `/reporting-bcm-sm/...`
- Réutilisation CORE (auth, Login 2, MFA existant, audit, GED) — aucun parallèle
- Distinction explicite BCM Clientèle
- Socle T3 limité (catalogue, hub, campagnes, perms, audit) clairement séparé des phases imports/moteur

## Points non résolus (voir T2_OPEN_DECISIONS.md)

- D01, D02, D04, D05, D09, D15 (et suite) — métier / Conformité / DSI
- LibreOffice / PDF — DSI
- Alignement `alembic current` vs head dépôt sur la DB de **développement** — à vérifier avant 1ʳᵉ migration T3 (`revision: str =` dans les fichiers ; tip probable `20261105_mg_stock_mvt_ref_uq`)
- Matrice compte×cellule Excel Claude encore absente

## Risques résiduels

| Risque | Niveau | Mitigation |
|--------|--------|------------|
| Activer mapping avant arbitrage D01 | Élevé | Statut forcé `A_VALIDER` ; gate workflow |
| ECART codé en dur | Élevé | Stockage run/campagne calculé ; refs historiques documentées seulement |
| Confusion BCM Clientèle | Moyen | Docs + codes perms séparés |
| Stockage `release-source` en prod | Moyen | T3 n’écrit pas encore de gros volumes ; migration `/srv` avant T4 massif |
| Multi-heads Alembic non vérifié sur DB | Moyen | Contrôle `alembic heads` / `current` avant migration |

## Tests exécutés dans cette mission

Aucun test applicatif lancé (mission documentaire).  
Contrôles réalisés : lecture conventions code, inventaire docs, cohérence interne dossier T2 révisé.

## Décision

# T2 VALIDÉ (conception)

Le dossier T2 révisé est **cohérent** avec le code réel BEA DIGITAL et les décisions métier confirmées pour la conception.

**T3 est prêt à démarrer** après **validation explicite** de l’utilisateur.  
Cette mission **ne commence pas** l’implémentation T3 (pas de modification `backend/` / `frontend/` applicatifs).

Si des amendements métier contredisent les points A–I, repasser T2 en `NON VALIDÉ` avant code.
