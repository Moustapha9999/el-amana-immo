# T3 — État d’avancement (implémentation)

**Branche :** `feat/reporting-bcm-sm-t3`  
**Commit de base (HEAD Git) :** `091b57c`  
**Mise à jour documentation :** 18/11/2026 (mécanisme Structure NCG + orientations — phases 1–6 DEV)

Le code T3 / NCG (rbcm_01–06, services, front) est dans le working tree, **non commité**.

## Conflit de périmètre

Voir [T3_SCOPE_AND_P2_DECISION.md](T3_SCOPE_AND_P2_DECISION.md).

## Alembic — état réel (SELECT uniquement, 16/11/2026)

| Base | `alembic_version` | Tables `rbcm_*` |
|------|-------------------|-----------------|
| `bea_digital` (DEV métier) | **`20261118_rbcm_06`** | tables 01–06 (+ `rbcm_ncg_orientation`) |
| `bea_digital_test` | (selon copie locale) | schéma test à vérifier avant pytest DB |

Production : non interrogée. Migrations `rbcm_*` appliquées **uniquement** sur `bea_digital` locale DEV.

Les mentions antérieures « `rbcm_01` non appliquée / Docker arrêté » décrivaient T3.2. Elles sont **obsolètes** pour `bea_digital`.

## Phases

| Phase | Statut | Notes |
|-------|--------|-------|
| T3.1 Socle catalogue / routes / UI | **Fait (code, non commité)** | Module, perms, Angular, API |
| T3.2 Modèle + migration | **Fait et appliqué en DEV** | `rbcm_01` → head **`rbcm_05`** sur `bea_digital` |
| T3.3 Campagnes / imports / params | **Fait (code)** | |
| T3.4 Mapping / moteur / ECART | **Partiel** | 242 `A_VALIDER`, 0 `ACTIVE`, ECART inactif |
| T3.5-1 Fiche + responsable | **Fait DEV** | `rbcm_02` |
| T3.5-2 Contrôles A/B/C/D | **Fait DEV** | `rbcm_03` + `rbcm_04` |
| T3.5-3-A Conception documentaire | **Fait (docs)** | Révision + levée D1–D9 ; **pas de code** |
| T3.5-3-B `rbcm_05` + seed template | **Fait DEV** | Voir `T3_5_3_B_REPORT.md` ; revue `VALIDABLE SOUS RÉSERVE` |
| T3.5-3-C WORK + graphe Decimal | **Fait DEV** | Voir `T3_5_3_C_REPORT.md` ; clés `C:STRUCT:F44/F46/F48` |
| T3.5-3-D API documents WORK | **Fait DEV** | Voir `T3_5_3_D_REPORT.md` ; liste / détail / download |
| T3.5-3-E UI documents WORK | **Fait DEV** | Voir `T3_5_3_E_REPORT.md` ; section Documents dans le détail SM ; pas d’API F |
| T3.5-3-F | **Non commencée** | Décisions / corrections documentaires |
| T3.6 Exports / recette | **Partiel** | Export technique ≠ canevas officiel ; PDF bloqué |
| Structure NCG + orientations (P1–P6) | **Fait DEV** | Comparaison BAL DET, revue Comptabilité, `rbcm_06`, catalogue 89 règles ; **pas de déploiement** — voir `NCG_STRUCTURE_ET_ORIENTATIONS.md` |

## Tests (historique)

Tests T3.5-3-B : `test_reporting_bcm_sm_t35_3_b.py` — **10 passed** (16/11/2026).  
Tests T3.5-3-C : `test_reporting_bcm_sm_t35_3_c.py` — **5 passed** (16/11/2026).  
Tests T3.5-3-D : `test_reporting_bcm_sm_t35_3_d.py` — **4 passed** (16/11/2026).  
Tests T3.5-3-E : `rbcm-documents.spec.ts` + `api-error.spec.ts` — **14 SUCCESS** (17/11/2026).  
Tests NCG (structure / orientation / phase3 / revue) : **36 passed** (18/11/2026).

## Décisions métier toujours ouvertes

D01, D02, D04, D05, D06, D09, D15, D16–D22, MATRICE, SEPT, DSI-PDF, DSI-SRV.  
P1 / P2 inchangés.

## Prochaine étape

1. **Validation Comptabilité** du parcours Structure / Revue NCG (guide `GUIDE_TEST_COMPTABILITE_NCG.md`) — cas 847000 sans cellule forcée.
2. Ensuite seulement : préparation de livraison / déploiement (autorisation explicite).
3. T3.5-3-F (décisions documentaires) : attendre autorisation séparée.
