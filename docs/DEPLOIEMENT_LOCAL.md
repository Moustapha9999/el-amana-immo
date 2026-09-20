# Déploiement local Docker (machine du comptable)

Produit : **BEA DIGITAL** — premier module Immobilisations & Amortissements.
Démarrage générique et restore non destructif : [demarrer.md](demarrer.md),
[base-de-donnees-unique.md](base-de-donnees-unique.md).

Instance temporaire pour la saisie des acquisitions 2026, en attendant le serveur DSI.
La migration vers le serveur banque se fera par dump PostgreSQL + copie des documents, avec rapprochement.

## Règles

- Ne **jamais** lancer `docker compose down -v` (le `-v` efface PostgreSQL).
- Ne **pas** recalculer l'exercice 2025 ni modifier l'archive 2025.
- Les secrets sont dans `.env.docker` (non versionné), jamais dans le code.
- PostgreSQL n'écoute que sur `localhost`.
- L'utilisateur ouvre uniquement **http://localhost**.

## Stack réelle du projet

| Composant | Technologie | Remarque |
|-----------|-------------|----------|
| Frontend | Angular 20 + nginx | `http://localhost` proxifie `/api/` vers le backend |
| Backend | FastAPI (Python 3.13) | Auth JWT interne + 2FA TOTP |
| Base | PostgreSQL 17 | Volume Docker `bea_postgres_data`, base `bea_digital` |
| Documents | fichiers locaux | `storage/uploads` (bind mount) |
| Auth cloud | **non utilisé** | Pas de Supabase Auth |
| Storage cloud | **non utilisé** | Pas de Supabase Storage |

Supabase n'est utilisé aujourd'hui que comme **PostgreSQL hébergé**. L'instance locale s'en affranchit.

Redis / Celery existent en développement (`docker-compose.dev.yml`) mais ne sont **pas** nécessaires au comptable.

## Pré-requis

1. Windows + Docker Desktop démarré
2. Droits administrateur pour l'installation Docker
3. Navigateur

Vérification :

```powershell
docker --version
docker compose version
```

## Transfert vers le PC du comptable (kit USB)

On ne copie pas les conteneurs en cours d'exécution. On exporte les **images** déjà construites, plus le dump et les documents.

### Sur cette machine (préparation)

```powershell
.\scripts\export-kit-comptable.ps1
```

Cela crée `dist\kit-comptable\` (environ 1,5 Go d'images + dump + pièces).

Copier **tout** ce dossier sur une clé USB, **sans** le fichier `.env` de développement.

### Sur le PC du comptable

1. Installer **Docker Desktop**, le démarrer, attendre l'état Running.
2. Copier le kit vers `C:\bea-digital` (chemin sans espace de préférence).
3. PowerShell dans ce dossier :

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install-on-comptable.ps1
```

4. Ouvrir **http://localhost**

Internet n'est pas nécessaire après l'installation de Docker Desktop : les images sont chargées depuis `images\bea-digital-stack.tar`.

Usage quotidien : `.\scripts\start-local.ps1` (pas `-Build`).  
Sauvegarde : `.\scripts\backup-local.ps1`.  
**Interdit :** `docker compose down -v`.

## Étape A — Backup de la base actuelle (obligatoire)

À faire **avant** le premier `docker compose up`, pendant que `.env` pointe encore vers la base cloud.

```powershell
.\scripts\backup-from-supabase.ps1
```

Contrôler `backups\` : un fichier `.dump`, une copie `uploads-…` si des pièces existent, un `manifest-…`.
Copier `backups\` vers un support externe si la politique de la banque l'autorise.

Ne supprimer **aucune** archive ni donnée tant que ce dump n'a pas été restauré avec succès.

## Étape B — Démarrer l'instance locale

```powershell
.\scripts\start-local.ps1
```

Cela crée `.env.docker` (secrets aléatoires) si besoin, construit les images et démarre postgres + backend + frontend.

Ouvrir http://localhost

Arrêt (données conservées) :

```powershell
.\scripts\stop-local.ps1
```

## Étape C — Restaurer le dump dans PostgreSQL local

```powershell
.\scripts\restore-local.ps1 -DumpFile backups\supabase-public-YYYYMMDD-HHMMSS.dump -RestoreUploads backups\uploads-YYYYMMDD-HHMMSS
```

Puis :

```powershell
.\scripts\check-local.ps1
```

Vérifier : tables, exercices 2025 (archivé / non recalculé) et 2026 ouvert, agences, pièces.

## Étape D — Sauvegardes pendant la saisie

Quotidien :

```powershell
.\scripts\backup-local.ps1
```

Conserver plusieurs dumps. Tester une restauration sur une copie si possible.

## Commandes Docker utiles

```powershell
docker compose --env-file .env.docker ps
docker compose --env-file .env.docker logs -f --tail=100
```

Redémarrage des conteneurs (sans perte) : redémarrer Docker Desktop ou le PC. `restart: unless-stopped` relance les services.

## Migration vers le serveur banque

1. Bloquer les nouvelles saisies sur le PC du comptable.
2. `.\scripts\backup-local.ps1` (dump final + documents).
3. Déployer la même stack Docker (ou le standard DSI) sur le serveur.
4. Restaurer le dump et `storage/uploads`.
5. Rapprocher : nombre d'immobilisations, acquisitions 2026, agences, soldes 142/148, dotations 2026, cumul, VNC, pièces, utilisateurs.
6. Valider avec la comptabilité et la DSI.
7. Ouvrir la saisie sur le serveur. Conserver le PC local jusqu'à validation définitive.

## Mise à jour du logiciel (PC déjà installé)

Voir `docs/MISE_A_JOUR_COMPTABLE.md`.

Sur la machine de développement (kit USB unique) :

```powershell
.\scripts\export-kit-comptable.ps1
```

Résultat : `dist\kit-comptable\` — à copier sur clé USB puis vers `C:\immo`.

Sur le PC comptable (après copie USB) :

- Déjà installé → double-clic **`MettreAJour.cmd`**
- Première install → double-clic **`Installer.cmd`**

Lanceurs quotidiens : `Demarrer.cmd`, `Arreter.cmd`, `Sauvegarder.cmd`, `Verifier.cmd`.

## Développement (cette machine, pas le comptable)

Uvicorn + base cloud restent pilotés par `.env`.
Compose de dev (hot-reload) :

```powershell
docker compose -f docker-compose.dev.yml up
```

## Serveur banque (cible GitLab)

Le kit USB ci-dessus reste le chemin **comptable**. Pour le serveur DSI / production :

- [deployment/README.md](deployment/README.md) — architecture GitLab + Runner + inventaire IT
- [`deployment/`](../deployment/) — compose prod, scripts backup/deploy/rollback
- [`.gitlab-ci.yml`](../.gitlab-ci.yml) — pipeline (approval manuelle)
