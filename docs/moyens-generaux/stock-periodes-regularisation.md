# Stock & Fournitures — réouverture de période et régularisation rétroactive

Module `stock-fournitures` (Moyens Généraux). Permet à un administrateur du stock de rouvrir une
période clôturée, d’y saisir ou corriger des mouvements datés dans le passé, puis de la clôturer
à nouveau — sans supprimer d’historique ni modifier silencieusement une période clôturée.

## Statuts de période

| Statut | Saisie | Qui |
|---|---|---|
| `OUVERTE` | oui (dates de la période, jamais dans le futur) | tout profil avec la saisie stock |
| `ROUVERTE` | oui, régularisation | `mg.stock.period.reopen` uniquement |
| `CLOTUREE` | non (`PERIODE_CLOTUREE`) | — |

- Plusieurs périodes peuvent être non clôturées en même temps. Une seule peut être `ROUVERTE`.
- Les clôtures suivent l’ordre chronologique : la plus ancienne période non clôturée d’abord.
- Rouvrir une période ne modifie **pas** le statut des périodes suivantes (l’ancien comportement
  les clôturait d’office et effaçait `cloture_at`).

## Permissions (contrôlées côté backend)

| Code | Effet |
|---|---|
| `mg.stock.period.view` | liste des périodes, soldes, historique des clôtures |
| `mg.stock.period.close` | clôture / nouvelle clôture |
| `mg.stock.period.reopen` | aperçu et réouverture ; saisie, modification ou suppression en période `ROUVERTE` ; dates antérieures à la période courante |

Chaque refus (permission absente, motif manquant, contrôle bloquant…) est journalisé
(`mg_stock_periode_evenements`, résultat `ECHEC`, et `audit_logs`) avant le renvoi de l’erreur.

## API (`/api/v1/mg/stock`)

| Méthode | Route | Rôle |
|---|---|---|
| GET | `/periodes` | statut, clôture initiale, dernière clôture, dernière réouverture, motif, nombre de réouvertures |
| GET | `/periodes/active` | période courante + `periodes_non_cloturees` |
| GET | `/periodes/{id}/preview-reouverture` | conséquences, périodes suivantes touchées, blocages |
| POST | `/periodes/{id}/rouvrir` | `{ "motif": "…" }` (5 caractères minimum, obligatoire) |
| GET | `/periodes/{id}/preview-cloture` | contrôles, corrections, articles modifiés, périodes recalculées |
| POST | `/periodes/{id}/cloturer` | refusée (`CLOTURE_BLOQUEE`) si un contrôle bloquant échoue |
| GET | `/periodes/{id}/historique` | clôtures, réouvertures et refus successifs |

Les mouvements (`POST /entrees`, `/sorties`, `/mouvements` pour les ajustements) acceptent `date_mouvement`
(date réelle) et `doublon_confirme`. La date d’enregistrement (`created_at`) est toujours
conservée à part. Le mouvement est exposé avec `date_enregistrement`, `periode_statut` et
`saisie_retroactive` (= date du mouvement antérieure au jour d’enregistrement).

Codes d’erreur de saisie : `MVT_DATE_FUTURE`, `PERIODE_INEXISTANTE`, `PERIODE_CLOTUREE`,
`PERIODE_ROUVERTE_RESERVEE`, `STOCK_NEGATIF_HISTORIQUE`, `DOUBLON_PROBABLE` (409 ; à confirmer
avec une observation).

## Base de données

Migration additive `20261102_mg_stock_periodes_02` (après `20261026_auth_01`, retour arrière
compatible) :

- `mg_stock_periodes` : `premiere_cloture_at`, `premiere_cloture_by`, `nb_reouvertures` ;
- table `mg_stock_periode_evenements` (jamais purgée, FK `RESTRICT`) : action, résultat,
  statut avant/après, motif, utilisateur (id + nom figé), détails JSON (instantané de
  réouverture, corrections, reports) ;
- reprise depuis `audit_logs` des clôtures / réouvertures déjà tracées, y compris les clôtures
  d’office imposées par l’ancienne réouverture (`CLOTURE_OFFICE` / `REOUVERTURE_OFFICE`) ;
- libellé de `mg.stock.period.reopen` mis à jour.

Aucune ligne existante n’est supprimée. Seules les nouvelles colonnes sont renseignées.

## Méthode de recalcul

Les soldes restent exacts, mouvement par mouvement, sans recalcul global approximatif :

1. un mouvement rétroactif met à jour le solde de **sa** période (entrées / sorties /
   ajustements) sous verrou ;
2. son effet (`+q` entrée, `−q` sortie, `±q` ajustement) est **reporté** sur chaque période
   suivante (`propager_report`) : `stock_initial += delta`. Si la période a un comptage physique,
   l’écart est recalculé, sinon `stock_final += delta`. Un solde absent est créé à 0 puis reporté ;
3. avant validation, le stock est rejoué jour par jour depuis le début de la période : aucun
   solde de **fin de journée** ne doit devenir négatif (`STOCK_NEGATIF_HISTORIQUE`). La saisie
   ne portant que sur le jour, l'ordre des mouvements d'une même journée n'est pas pris en
   compte (une livraison enregistrée à 15 h couvre une sortie du même jour). Une sortie
   enregistrée ensuite reste couverte ;
4. à la réouverture, un instantané par article (`final`, `theorique`, `ecart`, `chaine`) est
   stocké dans l’événement. La nouvelle clôture compare l’état réel à cet instantané.

### Contrôles de nouvelle clôture

| Contrôle | Bloquant |
|---|---|
| Soldes = somme des mouvements de la période (articles régularisés) | oui |
| Stock jamais négatif, date par date | oui |
| Écarts d’inventaire inchangés (sinon saisir un ajustement) | oui |
| Stock actuel cohérent avec la fin de chaîne des soldes | oui |
| Ordre chronologique des clôtures | oui |
| Doublons probables | avertissement |
| Comptages physiques des périodes suivantes recalculés | avertissement |

La synthèse (corrections avec leurs deux dates, articles modifiés avant / après, périodes
suivantes recalculées) est enregistrée dans l’événement `CLOTURE` (`recloture: true`).

## Concurrence

- Réouverture, clôture et création de période : `pg_advisory_xact_lock` commun.
- Clôture : `SELECT … FOR UPDATE` sur la période. Mouvement : `FOR SHARE` sur sa période
  (relecture forcée). Une clôture attend donc les saisies en cours, et une saisie arrivée après
  une clôture concurrente est refusée.

## Procédure d’utilisation

1. **Stock & Fournitures → Paramètres** (`/stock-fournitures/parametres`), bloc des périodes.
2. Sur la période clôturée : **Rouvrir**. L’aperçu montre les conséquences et les périodes
   suivantes concernées. Saisir le motif, puis confirmer.
3. Saisir l’entrée, la sortie ou l’ajustement en choisissant la **date du mouvement** dans la
   période rouverte. Le journal affiche « Saisi le … » pour une saisie rétroactive.
4. **Clôturer de nouveau** : vérifier les contrôles, les corrections et les périodes recalculées.
   Corriger tout contrôle bloquant (par exemple en saisissant un ajustement), puis valider.
5. **Historique** : consulter les clôtures et réouvertures successives, avec auteur et motif.

## Tests

- `backend/tests/test_mg_stock_regularisation_db.py` : 22 tests sur une base PostgreSQL isolée
  `bea_digital_stock_test` (données synthétiques). Ils sont ignorés sur toute autre base.
- `backend/tests/sql/mg_stock_periodes_reprise_fixture.sql` : jeu synthétique pour vérifier la
  reprise de la migration.
- `frontend/angular20/src/app/stock-fournitures/stock-date-mouvement.spec.ts`.

## Risques et limites

- La migration n’a été jouée que sur la base de test isolée. Elle doit être revue puis appliquée
  sur une copie de TEST avant tout environnement partagé.
- Les comptages physiques des périodes suivantes ne sont pas refaits : leur écart est recalculé
  et signalé en avertissement.
- La reprise d’historique dépend des traces `audit_logs` existantes. Une clôture non auditée
  n’apparaît qu’à travers `cloture_at`.
