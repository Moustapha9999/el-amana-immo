# Pipeline GitLab

Fichier : [`.gitlab-ci.yml`](../../.gitlab-ci.yml).

## Stages

```text
validate → test → security → build → publish
  → deploy_production (manual)
```

Sous-étapes documentées du déploiement (exécutées par les scripts sur le serveur) :

```text
backup → pull/recreate → migrate (si activé) → healthcheck → finalize
```

## Jobs (résumé)

| Stage | Contenu |
|-------|---------|
| validate | Présence `backend/`, `frontend/`, Dockerfiles |
| test | `pytest` dans `backend/` ; build Angular |
| security | Contrôles basiques secrets / fichiers sensibles |
| build | `docker build` backend + frontend |
| publish | Push registry sur tags `v*` (+ SHA) |
| deploy_production | `when: manual`, runner tag `bea-prod` ; SSH → `backup-pre-deploy.sh` puis `deploy.sh` |

## Règles

- Pas de déploiement automatique vers la prod sans clic d’approbation.
- Publish release lié aux **tags** SemVer `v*`.
- CI GitHub (`.github/workflows/ci.yml`) reste active tant que le remote GitHub est utilisé.

## Runner

- Tag recommandé : `bea-prod`.
- Emplacement : réseau interne BEA (voir architecture).
- Variables : [03-secrets-et-environnements.md](03-secrets-et-environnements.md).

## Rollback images

Sur le serveur : [`deployment/scripts/rollback.sh`](../../deployment/scripts/rollback.sh) avec l’ancien `BEA_VERSION`.

Restauration DB = procédure manuelle + backup vérifié — **pas** de restore destructif automatique depuis le pipeline.
