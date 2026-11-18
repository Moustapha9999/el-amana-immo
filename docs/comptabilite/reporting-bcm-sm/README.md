# Reporting BCM SM — Situation Mensuelle (Comptabilité)

Module **Reporting BCM SM** : reporting réglementaire mensuel de la **Comptabilité** BEA DIGITAL.

**Distinct** du BCM Clientèle (Conformité / LBC-FT : `clientele_declarations_bcm`, permissions `clientele.bcm.*`).  
Voir `docs/conformite/` pour le BCM Clientèle — ne pas confondre.

| Élément | Valeur cible |
|---------|----------------|
| Code module | `reporting-bcm-sm` |
| Espace | `comptabilite` → hub `/comptabilite` |
| Routes UI | `/reporting-bcm-sm/...` |
| API | `/api/v1/reporting-bcm-sm/` |
| Tables | préfixe `rbcm_` |
| Statut chantier | **T3 en cours** (DEV). Alembic head DEV : **`20261118_rbcm_06`** (orientations NCG). Catalogue moteur : **89** règles (`ALL_RULES`). Structure NCG + Revue Comptabilité livrés en DEV — **validation métier en attente** ; pas de déploiement. T3.5-3-F documentaire **non commencée**. |

## Documents

| Document | Contenu |
|----------|---------|
| [T2_dossier_conception.md](T2_dossier_conception.md) | Dossier T2 **révisé** (conception technique complète) |
| [T2_FINAL_VALIDATION.md](T2_FINAL_VALIDATION.md) | Validation T2, corrections, risques, décision |
| [T2_OPEN_DECISIONS.md](T2_OPEN_DECISIONS.md) | Décisions ouvertes classées par échéance |
| [T3_IMPLEMENTATION_PLAN.md](T3_IMPLEMENTATION_PLAN.md) | Plan d’implémentation T3 (socle — historique) |
| [T3_ACCEPTANCE_CRITERIA.md](T3_ACCEPTANCE_CRITERIA.md) | Critères d’acceptation T3 |
| [T3_PRE_IMPLEMENTATION_REVIEW.md](T3_PRE_IMPLEMENTATION_REVIEW.md) | Revue pré-démarrage |
| [T3_SCOPE_AND_P2_DECISION.md](T3_SCOPE_AND_P2_DECISION.md) | Conflit de périmètre + choix P2 |
| [T3_PHASE_STATUS.md](T3_PHASE_STATUS.md) | Avancement d’implémentation |
| [T3_2_MAPPING_AUDIT.md](T3_2_MAPPING_AUDIT.md) | Audit 115/242 + seed correspondances DEV |
| [T3_2_MAPPING_SEED_CANDIDATES.jsonl](T3_2_MAPPING_SEED_CANDIDATES.jsonl) | Règles candidates (A_VALIDER) |
| [T3_4B_REPORT.md](T3_4B_REPORT.md) | Refonte UI T3.4-B |
| [T3_4C_REPORT.md](T3_4C_REPORT.md) | Terminologie SM + finalisation UI T3.4-C |
| [T3_5_WORKFLOW_CONCEPTION.md](T3_5_WORKFLOW_CONCEPTION.md) | T3.5 — workflow guidé et canevas SM (audit, pas d’implémentation) |
| [T3_5_1_REPORT.md](T3_5_1_REPORT.md) | T3.5-1 — fiche guidée + responsable du reporting |
| [T3_5_2_REPORT.md](T3_5_2_REPORT.md) | T3.5-2 — contrôles métier + file A/B/C/D |
| [T3_5_2_REVIEW_COMPLEMENTAIRE.md](T3_5_2_REVIEW_COMPLEMENTAIRE.md) | Revue complémentaire T3.5-2 — permissions, concurrence, caisse |
| [T3_5_3_T0_AUDIT.md](T3_5_3_T0_AUDIT.md) | T3.5-3 T0 — audit du canevas officiel et plan d’intégration |
| [T3_5_3_T0_COMPLEMENT.md](T3_5_3_T0_COMPLEMENT.md) | T3.5-3 T0 — complément : 663 formules, faux zéro, modèles |
| [T3_5_3_A_AUDIT_ETAT_REEL.md](T3_5_3_A_AUDIT_ETAT_REEL.md) | T3.5-3-A — audit Git, migrations, modèles réels |
| [T3_5_3_A_MODELE_DOCUMENTAIRE.md](T3_5_3_A_MODELE_DOCUMENTAIRE.md) | T3.5-3-A — modèle documentaire cible **révisé** |
| [T3_5_3_A_DECISIONS_ET_POINTS_A_VALIDER.md](T3_5_3_A_DECISIONS_ET_POINTS_A_VALIDER.md) | T3.5-3-A — arbitrages R1–R15 / Q1–Q12 / D1–D9 |
| [T3_5_3_A_REVISION_DOCUMENTAIRE.md](T3_5_3_A_REVISION_DOCUMENTAIRE.md) | T3.5-3-A — rapport de révision documentaire |
| [T3_5_3_A_REVUE_FINALE.md](T3_5_3_A_REVUE_FINALE.md) | T3.5-3-A — revue finale (verdict historique `VALIDABLE SOUS RÉSERVE`) |
| [T3_5_3_A_LEVEE_RESERVES_D1_D9.md](T3_5_3_A_LEVEE_RESERVES_D1_D9.md) | T3.5-3-A — levée des réserves D1–D9 |
| [T3_5_3_A_CLOTURE_CONCEPTION.md](T3_5_3_A_CLOTURE_CONCEPTION.md) | T3.5-3-A — clôture conception (B n’est pas autorisée par ce doc) |
| [T3_5_3_B_REPORT.md](T3_5_3_B_REPORT.md) | T3.5-3-B — migration `rbcm_05` + seed canevas (DEV) |
| [T3_5_3_B_REVUE_FINALE.md](T3_5_3_B_REVUE_FINALE.md) | T3.5-3-B — revue finale (`VALIDABLE SOUS RÉSERVE`) |
| [T3_5_3_C_REPORT.md](T3_5_3_C_REPORT.md) | T3.5-3-C — graphe Decimal + génération WORK (DEV) |
| [T3_5_3_D_REPORT.md](T3_5_3_D_REPORT.md) | T3.5-3-D — API liste / détail / téléchargement WORK (DEV) |
| [T3_5_3_E_REPORT.md](T3_5_3_E_REPORT.md) | T3.5-3-E — UI consultation et téléchargement WORK (DEV) |
| [GUIDE_UTILISATEUR.md](GUIDE_UTILISATEUR.md) | Guide utilisateur (SM) |
| [GUIDE_TEST_COMPTABILITE_NCG.md](GUIDE_TEST_COMPTABILITE_NCG.md) | Guide test Comptabilité — Structure NCG & orientations |
| [NCG_STRUCTURE_ET_ORIENTATIONS.md](NCG_STRUCTURE_ET_ORIENTATIONS.md) | Synthèse technique mécanisme NCG (phases 1–6, DEV) |

## Références amont

- T0 : audit technique dépôt (conversation / rapport accepté)
- T1 : consolidation métier balances + mapping (conversation / rapport accepté)
- Fichiers métier : BAL DET/COND oct. 2026, canevas `BEA-SM-10-2026.xlsx`, Correspondance, Maquette RC, analyse Claude

## Règles d’or

- Pas de float métier → `Decimal` / `Numeric`
- Catalogue central unique (`rules_catalog` / `ALL_RULES`) ; orientations `VALIDE_ACTIF` fusionnées au calcul uniquement
- Aucune activation automatique d’orientation NCG ; séparation propose / validate
- Mapping historique UI en `A_VALIDER` tant que D01 non tranché
- 67 rubriques sans règle ≠ zéro automatique
- Paramètres mensuels non reconduits
- ECART calculé par période, inactif sans D02
- Production intacte jusqu’à procédure de release explicite
