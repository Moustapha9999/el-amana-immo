# Département Audit, Contrôle & Conformité

Espace BEA DIGITAL `audit-controle-conformite` (route `/audit-controle-conformite`).
Créé par la migration `backend/alembic/versions/20261003_acc_departement.py`
(données insérées une fois, **non verrouillées** : CORE ADMIN reste la source de vérité).

## Arborescence

```text
Audit, Contrôle & Conformité            (plateforme_espaces)
├── Audit interne                        domaine — bientôt
├── Contrôle permanent & périmètre op.   domaine — bientôt
├── Conformité & sécurité financière     domaine — actif
│   ├── KYC                              sous-domaine — actif
│   │   └── Gestion des Entrées en Relation (module eer) — en développement
│   ├── Formation & Sensibilisation (module formation) — actif
│   └── LBC-FT, FATCA, Gestion des dossiers clients, Demandes de prêt,
│       Déclarations BCM, Correspondants bancaires,
│       Vérification des procurations    sous-domaines — bientôt (CORE ADMIN, 04/10/2026)
├── Organisation & Processus             domaine — bientôt
└── Management & Qualité                 domaine — bientôt
```

Aucun module fictif pour les domaines en attente : leur carte affiche le statut
réel et le message d’attente saisi dans CORE ADMIN.

## Décisions

| Sujet | Décision |
|-------|----------|
| Code / route | `audit-controle-conformite` (`/audit` est un segment racine réservé à l’immo) |
| Hiérarchie | Table `plateforme_domaines` (`parent_id`, 2 niveaux max) + `plateforme_modules.domaine_id` nullable |
| Droits | Un domaine **n’ouvre aucun droit**. Chaîne inchangée : espace → module → permission |
| Module | Code `eer`, URLs `/eer/...`, permissions `eer.*`, rôles `eer.lecteur` / `eer.analyste` / `eer.superviseur` / `eer.admin` |
| Documents KYC | Uniquement via `eer.document.*` ; aucun rôle EER ne reçoit `ged.*` (ACL GED par espace trop large pour des pièces KYC) |
| Sécurité V1 | Contrôle backend strict (permissions + agence + GED cloisonnée). Pas de RLS en V1 |

## Administration (CORE ADMIN, `core.admin.departments`)

- Fiche département : icône (nom de glyphe Material Icons), statut, ordre, description,
  panneau **Domaines** (créer, éditer, activer/désactiver, supprimer).
- Fiche module : icône, domaine (filtré par département), statut dont « En développement ».
- Garde-fous backend : domaine et module dans le même département ; pas de 3ᵉ niveau ;
  suppression refusée s’il reste sous-domaines ou modules ; département non supprimable
  tant qu’il a des domaines. Un domaine inactif masque ses sous-domaines et modules du hub
  (les grants utilisateurs sont conservés).

API : `GET|POST /api/v1/plateforme/admin/domaines`, `GET|PATCH|DELETE /domaines/{id}`,
`POST /domaines/{id}/activate|deactivate` (audités, entité `domaine`).

## RLS — phase 2 (documenté, non activé)

Le rôle PostgreSQL applicatif est superuser : une politique RLS serait contournée.
Pré-requis avant d’activer RLS sur les tables EER : rôle applicatif dédié non superuser,
`SET LOCAL app.user_id / app.agence_id` par transaction, politiques testées sur une copie
de la base. D’ici là, FastAPI reste le seul point de contrôle
([core-admin.md](../core-admin.md)).

## Fichier source analysé

`Suivi-entre-en-relation.xlsx` : 16 colonnes de suivi. La colonne
« CONFORMITE DU FLUX » dépend d’un classeur externe (`[1]FLUX!`) absent :
`Z:\Conformite\Conformité AML\Analyse Conformité\TABLEAU DE SUIVI EER 2026 v2.xlsx`
(colonnes B, E, O, S, T). Sa structure **n’est pas inventée** ; le reporting EER est
calculé depuis PostgreSQL et sera rapproché de FLUX après récupération du fichier.

## À fournir par le métier (avant l’étape modèle EER)

- Formulaires KYC : personne physique, personne morale, association.
- Seuil validé de bénéficiaire effectif.
- Règle d’accès inter-agences.
- Source `[1]FLUX!`.

## Module EER — architecture métier (étape 2, en validation)

- [eer-architecture-metier.md](eer-architecture-metier.md) : modèle, relations, tables,
  moteur de checklist, règles (conformité, PPE, FATCA, LBC-FT, mandataires, actionnariat, BE),
  anomalies, compléments, versions, reporting, `[1]FLUX`, plan migrations, plan tests.
- [eer-matrices.md](eer-matrices.md) : matrices Type client → Profil → Formulaire → Checklist →
  Documents → Contrôles → Workflow, mapping Excel, questions ouvertes.

## Statut (05/10/2026)

Module `eer` fonctionnellement complet côté application : dossiers, workflow, checklist,
contrôles automatiques, anomalies, compléments, avis, versions, reporting, pièces GED
cloisonnées, notifications, échéances (job de fond `EER_ECHEANCES_INTERVAL_HEURES`) et exports
PDF / Excel (détail : [eer-architecture-metier.md](eer-architecture-metier.md) §21 et §23 bis).
L’ouverture (statut `actif`) reste une décision CORE ADMIN.

Reste dépendant du métier ou de l’exploitation :

- **Source `[1]FLUX`** (`TABLEAU DE SUIVI EER 2026 v2.xlsx`) : rapprochement du reporting
  historique (§22, test `test_eer_suivi_excel.py` prêt, sauté sans le fichier).
- **RLS** : rôle PostgreSQL applicatif non superuser à créer (section ci-dessus).
- **Questions ouvertes** : [eer-matrices.md §7](eer-matrices.md#7-questions-ouvertes).

## Base clientèle (08/10/2026, en construction)

- [phase0-audit-referentiel-clients.md](phase0-audit-referentiel-clients.md) : audit de l'existant.
- [clientele-phase1.md](clientele-phase1.md) : modèle CLIENT (racine ORION) / COMPTE / RIB,
  migration `20261008_clientele_01` (appliquée sur copie de test uniquement).
- [clientele-phase2.md](clientele-phase2.md) : import État des comptes ORION, vue Situation PP / PM
  (sources de colonnes, sans copie ni invention), module `clientele`.
- [clientele-phase4.md](clientele-phase4.md) : rapprochement d'imports, classification configurable,
  filtrage / alertes (phases 4–6). Migration `20261008_clientele_03` (copie de test uniquement).
- [clientele-moteur-scoring.md](clientele-moteur-scoring.md) : CDC 1.0, moteur SCORE uniquement,
  INTERDIT bloquant, référentiel maître LOT 1. Migrations `06`/`07` (test/recette, pas de
  classification massive, aucune valeur ACTIVE).
- [roadmap-indicateurs-bcm.md](roadmap-indicateurs-bcm.md) : **ordre révisé** après BCM
  (moteur **fait** → reporting **fait** → EER racine **fait** → Déclaration BCM **fait**).
  Déclaration : `/clientele/declarations`, snapshot à la validation, pas d’invention de formules.
  Ne pas exécuter les anciens prompts « 28 rapports » / « reporting BCM PDF ».
  Pont EER : `GET /api/v1/eer/clientele/{racine}`, préremplissage ORION sans écrasement.

## Module Formation & Sensibilisation (07/10/2026)

Remplace le fichier Excel de suivi des formations. Code `formation`, URLs `/formation/...`,
API `/api/v1/formation/...`, migration `20261007_formation_module` (tables `formation_*`,
référentiels initiaux issus de l’Excel, ligne `plateforme_modules`).

| Sujet | Décision |
|-------|----------|
| Employé | Nom, Prénom, Fonction, Entité, Périmètre (déduit de l’entité), Email, Téléphone. Doublons bloqués (clé d’identité : mots normalisés, ordre indifférent) ; création forcée seulement après confirmation explicite |
| Formation | Date*, Thème(s)*, Lieu*, Formateur(s)*, participants multi-sélection. Aucun présent par défaut |
| Présence | `PRESENT` / `ABSENT` uniquement ; saisie impossible avant la date ; correction d’une présence existante = motif obligatoire |
| Statuts | `PLANIFIEE` → `REALISEE` (toutes présences saisies) → `CLOTUREE` ; `ANNULEE` (motif) ; `ARCHIVEE`. Suppression définitive réservée à `formation.admin` (voir « Suppressions administrateur ») |
| Concurrence | Champ `revision` : toute écriture concurrente renvoie `409 CONFLIT_REVISION` |
| Historique | Fonction / entité / périmètre figés sur la participation à la date de la formation |
| Référentiels | Thèmes, Formateurs, Lieux, Fonctions, Périmètres, Entités : modifiables, désactivables, fusionnables ; une valeur utilisée ne se supprime pas (sauf `formation.admin`) |
| Import Excel | Analyse → aperçu → correspondances → découpage Nom/Prénom **proposé puis vérifié** (case obligatoire) → confirmation. Ré-import du même fichier détecté (SHA-256), sans doublon de participation |
| Exports | Feuille de présence PDF/Excel (en-tête BANQUE EL AMANA, N° / Nom et prénom / Signature) ; `Rapport_Formation.pdf` et `Rapport_Formation.xlsx` (8 onglets). Pas de CSV |
| Droits | `formation.view`, `create`, `update`, `cancel`, `close`, `employees.*`, `attendance.*`, `references.*`, `import.*`, `reporting.*`, `admin` ; rôles `formation.lecteur`, `formation.gestionnaire`, `formation.admin` |
| Audit | Toute action (y compris exports) dans `audit_logs` (`module_code = formation`), consultable dans Historique → Journal d’audit |
| Feuille signée (GED) | Scan PDF / image déposé sur la fiche formation → `ged_documents` (module `formation`, entité `formation_session`, type `FEUILLE_PRESENCE_SIGNEE`, OCR). Dépôt dès que la date est passée (planifiée, réalisée, clôturée) ; retrait avec motif tant qu’elle n’est pas clôturée (corbeille GED). Droit `formation.attendance.manage`. Liste : colonne et filtre « Feuille signée manquante » |

### Suppressions administrateur (`formation.admin`, superuser implicite)

L’administrateur supprime définitivement, à tout moment et quel que soit le statut. Chaque
suppression passe par une confirmation, et l’audit « avant » garde le détail complet.

| Objet | Écran | API | Effet |
|-------|-------|-----|-------|
| Formation (même clôturée / archivée, présences saisies) | Liste (sélection multiple, icône par ligne) et fiche | `POST /sessions/{id}/supprimer`, `POST /sessions/suppression-multiple {ids, motif}` | Participants et présences effacés, feuilles signées en corbeille GED. Motif obligatoire. En suppression multiple, un échec n’annule pas les autres |
| Participant d’une formation clôturée | Fiche formation | `POST /sessions/{id}/participants/{pid}/retrait` | Motif si présence saisie |
| Employé | Liste et fiche employé | `POST /employes/{id}/supprimer {motif}` | Employé et toutes ses participations supprimés, statut des formations ouvertes recalculé |
| Valeur de référentiel utilisée | Référentiels | `DELETE /referentiels/{id}?forcer=true` | Thème / formateur retiré des formations, fonction / périmètre mis à vide sur employés et participations, lieu retiré des entités. Lieu d’une formation ou périmètre d’une entité : refus `REFERENTIEL_OBLIGATOIRE` (fusionner d’abord) |
| Entité utilisée | Référentiels → Entités | `DELETE /entites/{id}?forcer=true` | Employés et participations rattachés sans entité |
| Feuille signée (formation clôturée) | Fiche formation | `POST /sessions/{id}/documents/{did}/retrait` | Corbeille GED, motif obligatoire |
| Ligne d’historique d’import | Import Excel | `DELETE /imports/{id}` | Les données importées restent, le fichier n’est plus signalé « déjà importé » |

Hors périmètre V1 : évaluations, attestations, QR codes.
