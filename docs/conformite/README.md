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
