# Désactivation du module EER (réversible)

Décision : cahier des charges « Simplification de la Base Clientèle et du module de classification ».
Le module EER est **désactivé**, pas supprimé. Aucune table, aucune donnée, aucun fichier GED n’est effacé.

## Ce qui change

| Élément | État après désactivation |
| --- | --- |
| `plateforme_modules` (code `eer`) | `statut = 'inactif'`, `is_active = false` (migration `20261020_clientele_14`) |
| Catalogue (`backend/app/data/plateforme_catalogue.py`) | `statut: "inactif"` + message « Module désactivé — données conservées » ; la synchronisation `scripts/sync_catalogue_mg.py` ne le réactive pas |
| Menu et accès | Le module disparaît du menu ; `require_module_access` renvoie 403 sur `/api/v1/eer/...` |
| Rappels d’échéances | `_boucle_echeances_eer` (`backend/app/main.py`) ne fait plus aucune passe tant que le module n’est pas `actif` |
| Tables `eer_*`, triggers d’immuabilité, GED `module_code=eer` | **Conservés** à l’identique |
| Permissions `eer.*` et rôles `eer.*` | Conservés (inopérants tant que le module est inactif) |

## Dépendances conservées (lecture seule, hors module)

Ces lectures continuent de fonctionner parce que les tables existent toujours. Elles ne passent pas par les routes
`/eer/...`, donc la désactivation ne les casse pas.

| Fichier | Usage | Comportement si les tables étaient un jour supprimées |
| --- | --- | --- |
| `backend/app/services/clientele/sic.py` | SQL sur `eer_dossiers`, `eer_parties`, `eer_parties_physiques` : sexe et téléphone du client pour la déclaration SIC | **Erreur SQL** : à adapter avant toute suppression |
| `backend/app/services/clientele/indicateurs.py` | `EerDossier` : indicateur « EER du mois » et sa population (reporting / BCM) | Protégé par `to_regclass('public.eer_dossiers')` : indicateur à 0 |
| `backend/app/data/clientele_indicateurs.py`, `backend/app/data/clientele_bcm.py` | Définitions d’indicateurs qui citent `eer_dossiers` comme source | Libellés seulement |
| `backend/app/services/clientele/classification.py` | Lecture optionnelle du dernier dossier EER du client (données déclarées) lors de l’évaluation, sous `try/except` | Données EER absentes, pas d’erreur |
| `backend/app/services/clientele/bcm_calcul.py` | Couverture « EER du mois » (racines avec dossier réalisé) dans le contrôle BCM | Protégé par `to_regclass` : couverture vide |

## Réactiver

1. CORE ADMIN (`/admin`, `core.admin.access`) : réactiver le module `eer`, **ou** en SQL :
   `UPDATE plateforme_modules SET statut = 'actif', is_active = true WHERE code = 'eer';`
2. Remettre `statut: "actif"` dans `plateforme_catalogue.py` (sinon la prochaine synchronisation le repasse inactif).
3. Redémarrer le backend : la boucle de rappels reprend au prochain cycle.

Le `downgrade` de la migration `20261020_clientele_14` remet aussi le module actif.

## Suppression définitive (hors périmètre, non faite)

Ne rien supprimer sans validation explicite et analyse d’impact. Étapes minimales le jour venu :

1. Sauvegarde complète (`pg_dump`) et export GED du module.
2. Adapter `sic.py` (source alternative du sexe / téléphone).
3. Retirer les indicateurs EER ou accepter la valeur 0.
4. Seulement ensuite : migration de suppression des tables `eer_*` (triggers d’immuabilité à lever explicitement).
