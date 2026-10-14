# Référentiel organisationnel central (organigramme BEA)

Source : *Organigramme présentation BEA – juillet 2024* (PDF). Le référentiel fait partie du **CORE** :
il n’est pas un module métier. Administration dans **CORE ADMIN** (`/admin/organigramme`, Login 1,
permission `core.admin.organisation`) ; lecture par tous les modules via `/api/v1/organisation/*`.

## Modèle

| Notion | Table | Remarques |
|--------|-------|-----------|
| Entité (conseil, comité, DG, direction, département, service, section, cellule) | `departements` (évoluée) | Hiérarchie libre `parent_id` (profondeur variable). Réutilisée car déjà référencée par immobilisations, centres de coût, achats, demandes employés, lots, GED. Classe Python : `OrgEntite` (alias de `Departement`). |
| Poste / fonction | `org_postes` | Fonction ≠ personne : `titulaire_user_id` optionnel, jamais de nom importé. |
| Affectation d’un utilisateur | `org_affectations` | Une **principale** active (index unique), secondaires / intérim. Clôture = `actif=false` + `date_fin` (historique conservé). |
| Agence physique | `agences` (inchangée) | `agences.org_entite_id` : rattachement hiérarchique facultatif. |
| Direction legacy | `directions` | Conservée, non utilisée par le référentiel (la DG importée garde `metadonnees.legacy_direction_id`). |

Pourquoi deux nouvelles tables seulement : aucune table existante ne portait les postes ni les
affectations datées utilisateur ↔ entité (`users.agence_id` reste l’agence, inchangée).

Colonnes ajoutées à `departements` : `type_entite`, `parent_id`, `cle` (clé normalisée calculée en base),
`sigle`, `description`, `ordre`, `alias[]`, `a_confirmer`, `note_confirmation`, `source`,
`metadonnees`, `created_by_id`, `updated_by_id`.

Garanties en base (migration `20261015_org_01`) :

- pas de cycle (déclencheur `trg_departements_sans_cycle`, contrainte `ck_departements_sans_cycle`) ;
- pas de doublon de libellé sous un même parent (`uq_departements_parent_cle`, entités non supprimées) ;
- clés étrangères **sans cascade** (`RESTRICT` / `SET NULL`) : désactiver une entité ne supprime aucun
  dossier, document, opération ni écriture ;
- normalisation unique `org_cle(text)` (accents, casse, ponctuation) partagée par SQL et Python.

## Ambiguïtés de l’organigramme (marquées « À confirmer »)

Signalées dans les données (`a_confirmer`, `note_confirmation`) et listées dans CORE ADMIN → Contrôles :

- mentions « (2) » (effectif ou doublon de service ?) ;
- Service Monétique présent sous les Opérations domestiques **et** sous la DSI ;
- postes et cellules rattachés directement à la DG (Cash Payment, Qualité, comités) ;
- niveau des départements Informatique (DSI) et Comptable & Financier (DCF) : direction ou département ;
- rattachement des agences : seules AGENCE CENTRALE ENTREPRISES (00005 → Clientèle Entreprises) et
  AGENCE CENTRALE PARTICULIERS (00001 → Clientèle Retail) sont rattachées ; les autres restent à confirmer.

## Reprise des données existantes

- Saisies libres conservées telles quelles (`departement` texte des tables MG). Colonne `org_entite_id`
  ajoutée à côté.
- Rattachement automatique **uniquement** sur correspondance exacte normalisée et unique (libellé ou
  alias). Aucune correspondance approximative n’est appliquée sans validation.
- Le reste apparaît dans CORE ADMIN → Correspondances, avec des suggestions ; l’administrateur valide,
  la valeur devient un alias et les saisies futures identiques sont rattachées automatiquement
  (déclencheur `trg_{table}_org`).
- Réclamations (`reclamation_unites`) et Formation (`formation_entites`) : même principe, les unités
  locales restent la référence de leurs workflows ; `org_entite_id` les relie à l’organigramme.

## Droits : rôle, permission, périmètre

| Couche | Où | Effet |
|--------|----|-------|
| Rôle / permissions module | inchangé (`roles`, `permissions`) | Ce que l’utilisateur peut **faire**. |
| Affectation | `org_affectations` | Où il se situe dans l’organigramme. **Aucun droit en soi.** |
| Périmètre | `org_affectations.perimetre` | `PERSONNEL` (défaut) · `ENTITE` · `ENTITE_ET_SOUS_ENTITES`. Élargit les dossiers **visibles**. Jamais élargi automatiquement. |
| Global | permission `org.scope.all` (ou superuser) | Toutes entités, pour les modules qui appliquent le périmètre. |

Contrôle **côté backend uniquement** : `app.services.org_referentiel.charger_perimetre(db, user)` renvoie
un `PerimetreOrg` (`global_`, `entites`, `entite_principale_id`, `couvre_entite()`, `condition()`).

Login 1 et Login 2 inchangés : `/api/v1/organisation/*` accepte les deux sessions (`get_current_user`) ;
l’administration exige Login 1 + `core.admin.organisation`.

## Brancher un module (actuel ou futur)

1. **Clé étrangère** : `org_entite_id UUID REFERENCES departements(id) ON DELETE RESTRICT` (ou
   `departement_id` si la colonne existe déjà). Jamais de liste locale de directions / services.
2. **Lecture** : `GET /api/v1/organisation/entites` (`type_entite`, `racine_id`, `q`, `inclure_inactives`),
   `GET /api/v1/organisation/entites/{id}/sous-arbre`, `GET /api/v1/organisation/agences`,
   `GET /api/v1/organisation/mon-perimetre`.
3. **Filtre « par direction / département / service »** : `org_referentiel.sous_arbre(db, entite_id)` puis
   `colonne.in_(ids)` — une direction inclut ses départements, services et sections.
4. **Périmètre** : `perimetre = await charger_perimetre(db, user)` puis
   `query.where(perimetre.condition(Table.org_entite_id, Table.created_by_id))`, combiné aux permissions du
   module (`exiger(...)`). Le périmètre n’ouvre jamais une action.
5. **Front** : `OrgEntiteSelectComponent` (`core/org/org-entite-select.component.ts`, `<select>` natif,
   `ngModel` ou `formControlName`, entrées `types`, `exclure`, `entites`, `placeholder`) et
   `OrgReferentielService` (`core/org/org-referentiel.service.ts`).
6. **Workflow** : router vers le **poste responsable** de l’entité (`org_postes.est_responsable`,
   `titulaire_user_id`), pas vers un nom en dur.
7. Déclarer la table dans `LIAISONS` (`app/services/org_referentiel.py`) pour qu’elle apparaisse dans les
   compteurs « données conservées » et, si elle a une ancienne saisie texte, dans les correspondances.

## État par module

| Module | Liaison | Intégration |
|--------|---------|-------------|
| Immobilisations, centres de coût | `departement_id` (existant) | Pointe désormais vers les entités de l’organigramme ; URLs et règle VNC inchangées. |
| Achats (demandes d’achat) | `departement_id` (existant) | Idem. |
| Bons de commande, lignes BC | `org_entite_id` + texte `departement` conservé | Rattachement exact automatique + correspondances. |
| Stock (mouvements), demandes de fournitures | idem | idem. |
| Notes de frais | idem | idem. |
| Demandes employés, lots d’approvisionnement | `department_id` (existant) | Liste des entités actives avec leur chemin (`/me/requests/refs`). |
| GED / Archives | `department_id` (existant) | Pointe vers les entités. |
| Réclamations | `reclamation_unites.org_entite_id` | Unités reliées ; filtre « Organigramme » (sous-arbre) sur la liste, les exports et le reporting ; périmètre organisationnel = consultation élargie ; workflow et historique inchangés. |
| Formation | `formation_entites.org_entite_id` | Entités du siège reliées (API `EntiteIn.org_entite_id`). |
| EER, Clientèle | agences ORION | Inchangé (pas de notion de direction / service). |
| CORE ADMIN utilisateurs | `org_affectations` | Fiche utilisateur → panneau « Organigramme — affectations ». |

## API d’administration (CORE ADMIN)

Préfixe `/api/v1/plateforme/admin/organisation`, Login 1 + `core.admin.organisation` :
`entites` (GET, POST), `entites/{id}` (GET, PATCH), `entites/{id}/desactiver|reactiver`,
`entites/{id}/postes`, `postes/{id}`, `affectations` (GET `?user_id=`, POST), `affectations/{id}`
(PATCH), `affectations/{id}/cloturer`, `controles`, `correspondances`, `correspondances/{liaison}`,
`agences`, `agences/{id}`, `historique`. Chaque écriture est auditée (`audit_logs`, actions `org.*`).

Tests : `backend/tests/test_org_referentiel.py`.
