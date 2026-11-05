# Numérotation des références (mouvements, demandes)

Règle actuelle, figée jusqu’à validation métier d’une autre politique.

## Attribution

`app/services/sequences.py` — `prochain_numero` :

1. Verrou de transaction PostgreSQL (`pg_advisory_xact_lock`) par préfixe et année
   (`ENT-2026`, `DEM-2026`, …). Deux processus uvicorn ne lisent pas le même rang.
2. Rang = plus grand suffixe numérique déjà présent + 1 (pas `COUNT + 1`).
   Une suppression ne réattribue pas un numéro ; les trous sont conservés.

Utilisé pour les mouvements de stock, les demandes de fournitures et les
demandes employés / regroupements.

## Dernière ligne de défense

Le verrou applicatif **ne remplace pas** une contrainte d’unicité :

| Objet | Index UNIQUE |
|---|---|
| `mg_stock_mouvements.reference` | `uq_mg_stock_mouvements_reference` |
| `mg_employee_requests.request_number` | `ix_mg_employee_requests_number` |

Une course qui échapperait au verrou se traduit par un 409 `DUPLICATE`, pas par
deux lignes portant le même numéro.

## Séquence PostgreSQL (plus tard)

Une `SEQUENCE` accélérerait l’attribution sous forte concurrence et garantirait
l’unicité. Elle **n’interdit pas les trous** (un `nextval` consommé par une
transaction annulée n’est pas rendu). À n’adopter qu’après validation des
règles de numérotation bancaire BEA DIGITAL. D’ici là : verrou + UNIQUE.
