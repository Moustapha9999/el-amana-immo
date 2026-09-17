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

Source canonique : `backend/`.

- **Presentation** : `backend/app/api/v1`
- **Application** : `backend/app/services`
- **Domain** : règles dans services + modèles (`backend/app/models`)
- **Infrastructure** : `backend/app/db`, Redis, Celery, stockage fichiers

Référentiel plan comptable : `backend/app/data/el_amana_referentiel.py`.
Socle Login 1 / Login 2 : [socle-bea-digital.md](socle-bea-digital.md).
