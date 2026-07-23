# Cahier des charges — synthèse

Document de référence aligné sur la spécification métier fournie (immobilisations bancaires, plan comptable mauritanien).

## Modules fonctionnels

1. Authentification (JWT, refresh, mot de passe oublié, 2FA optionnelle)
2. Utilisateurs, rôles, permissions (RBAC)
3. Référentiels organisationnels (agences, directions, départements, centres de coût)
4. Immobilisations (CRUD, import/export, pièces jointes, QR/code-barres)
5. Paramétrage amortissement (linéaire, dégressif, prorata, périodicité)
6. Calcul & validation amortissements + écritures comptables
7. Cessions, rebuts, réévaluations, ajustements
8. Inventaire physique
9. Dashboard & rapports (PDF/Excel)
10. Audit & notifications

## Architecture backend

- **Presentation** : `app/api/v1`
- **Application** : `app/services`
- **Domain** : règles dans services + modèles (`app/models`)
- **Infrastructure** : `app/db`, Redis, Celery, stockage fichiers

## Prochaines implémentations

- Tables `cessions`, `rebuts`, `reevaluations`, `ajustements`, `notifications`
- Workers Celery pour calculs de masse et exports
- Middleware audit sur toutes les mutations
- Intégration plan comptable bancaire El Amana : voir `app/data/el_amana_referentiel.py`, migration `20260723_el_amana`, script `scripts/seed_plan_comptable_el_amana.py`
