# Dossier de transmission — BEA DIGITAL (13 novembre 2026)

**Source :** [`BEA_DIGITAL_Dossier_transmission_deploiement_2026-11-13.docx`](../../BEA_DIGITAL_Dossier_transmission_deploiement_2026-11-13.docx)  
**État de référence documenté :** version `v1.0.0`  
**Complète :** [09-proces-verbal-premiere-installation.md](09-proces-verbal-premiere-installation.md) (install du 9/11 sur `srv-classification`)

Aucun secret n’est recopié ici : pas de valeur `SECRET_KEY`, pas de contenu `.env.production`, pas de secret TOTP / codes MFA.

---

## 1. Verdict

`v1.0.0` est la version **active et saine** au 13/11/2026 sur le serveur inventorié. Backend, worker, PostgreSQL et Redis étaient healthy ; `/health/ready` = ok (`database=ok`, `redis=ok`).

La tentative de passage à `v1.0.1` **n’a pas abouti** (images absentes). Aucun déploiement `v1.0.1` n’est à considérer comme réalisé.

Objectif immédiat : **stabiliser et préserver** `v1.0.0`, documenter les montages persistants, puis seulement préparer une release avec artefacts vérifiés.

---

## 2. Distinction des environnements

| Environnement | Identification | Notes |
|---------------|----------------|-------|
| Serveur inventorié le 13/11 | `srvsuividep-virtual-machine`, `192.168.1.55/24`, dossier `/opt/bea-digital` | Contenu de ce dossier de transmission |
| Première install (PV 09) | `srv-classification`, `192.168.1.22`, dossier `/home/moustapha/bea-digital` | Ne pas confondre avec le relevé du 13/11 |
| Poste de développement | Machine locale Cursor / Docker local | Bases, volumes et chiffres locaux ≠ serveur bancaire |

En cas de contradiction entre ce document et l’état réel du serveur, **l’état observé sur le serveur prévaut** après vérification, puis ce dossier doit être mis à jour.

---

## 3. Ce qui a été fait le 13 novembre 2026

- Inventaire hôte, réseau, Docker, volumes, montages, secrets, MFA.
- Renforcement des contrôles `SECRET_KEY` (une entrée, 64 hex, empreinte verrouillée `deployment/state/secret_key.sha256`).
- MFA administrateur réactivé par l’utilisateur (Google Authenticator) — **ne pas réinitialiser** dans un déploiement normal.
- Dump pré-réinitialisation MFA conservé sous `/srv/bea-digital/backups/mfa-recovery/` (permissions 600, `pg_restore --list` OK).
- Copies de sécurité des scripts (`deploy.sh`, `lib.sh`) sous `/opt/bea-digital/backups/script-safety/`.
- Nettoyage **non destructif** : `apt-get clean/autoclean`, `journalctl --vacuum-time=14d`, suppression image `hello-world` uniquement. **Aucun** volume, conteneur, sauvegarde ou image BEA DIGITAL supprimé.
- Santé revalidée après nettoyage.

---

## 4. État serveur documenté (13/11/2026)

| Élément | Valeur observée |
|---------|-----------------|
| Hôte | `srvsuividep-virtual-machine` (VMware, Ubuntu 22.04.5 LTS, x86-64) |
| IP | `192.168.1.55/24`, passerelle `192.168.1.253` (privée) |
| Ressources | 4 vCPU Xeon Gold 5218, ~15 GiB RAM, disque `/dev/sda2` ~2 To (~14 Go utilisés) |
| Logiciels | Docker 29.9.3, Compose 5.7.1, Nginx 1.18.0, Python 3.10.12, Git 2.34.1 |
| Accès distant | AnyDesk ; SSH signalé inactif ; UFW signalé inactif — ne pas modifier sans IT |
| Conteneurs | `bea-frontend`, `bea-backend`, `bea-worker`, `bea-postgres`, `bea-redis`, `bea-pgadmin` |
| Images | `bea-digital/frontend:v1.0.0`, `bea-digital/backend:v1.0.0`, `postgres:17`, `redis:7-alpine`, `dpage/pgadmin4:latest` |
| Ports | Nginx `0.0.0.0:80` / `:443` ; frontend `127.0.0.1:8080` ; pgAdmin `127.0.0.1:5050` |
| Config | `/opt/bea-digital/.env.production` (mode 600) |
| Verrou SECRET_KEY | `/opt/bea-digital/deployment/state/secret_key.sha256` (mode 600, répertoire `700`) |
| Empreinte SECRET_KEY (verrou) | `239783b50c81c0ac90bbd774f91b3a835bd5da0bf07cbf0571d1966440b6f96b` — vérif uniquement, ne reconstitue pas la clé |
| Certificats | `/etc/bea-digital/certs/fullchain.pem` + `privkey.pem` (ne jamais partager la clé) |
| `/version` observé | `service=BEA DIGITAL`, `version=v1.0.0`, `git_sha=unknown`, `env=production` |

Périmètre : CORE ADMIN = même application. ORION hors périmètre. EER désactivé ; Clientèle / Réclamations à confirmer / valider avant présentation comme matrice officielle.

---

## 5. Volumes et montages — à préserver

| Volume / chemin | Rôle |
|-----------------|------|
| `bea_postgres_data` | Base PostgreSQL — **ne jamais supprimer** |
| Volume Redis anonyme | `/data` dans `bea-redis` — conserver tant que la persistance n’est pas revue |
| `bea_pgadmin_data` | Config pgAdmin |
| GED / uploads / backups | Montés depuis `/opt/bea-digital/import/incoming/release-source/...` |

**Point critique :** `/srv/bea-digital/{GED,uploads,backups}` existe sur l’hôte mais les conteneurs montent encore `import/incoming/release-source`. Ne pas supprimer `release-source` tant que la migration n’est pas faite et testée. Voir [11-migration-stockage-persistant.md](11-migration-stockage-persistant.md).

---

## 6. Règles absolues

- Ne jamais : `docker compose down -v`, `docker volume prune`, `docker system prune -a`.
- Ne jamais supprimer `.env.production`, `secret_key.sha256`, certificats, dumps, GED/uploads montés.
- Ne jamais régénérer `SECRET_KEY` pour « réparer » MFA ou un déploiement (casse le chiffrement existant).
- Ne jamais réinitialiser le MFA admin dans une opération de déploiement standard.
- Ne pas exposer publiquement pgAdmin (`127.0.0.1:5050`) ni le frontend interne sans validation sécurité.
- Ne pas déployer une version dont les images / checksums sont absents.

---

## 7. Diagnostic lecture seule (15/11/2026)

### 7.1 Depuis le poste de développement

| Contrôle | Résultat |
|----------|----------|
| Ping `192.168.1.55` | Timeout (2/2 perdus) |
| HTTPS distant | Timeout — réseau banque / AnyDesk uniquement |

### 7.2 Sur le serveur (AnyDesk) — 2026-11-15T12:36:26Z

Exécuté sur `srvsuividep-virtual-machine`. Première tentative : script collé dans le shell → `Racine=/` et faux « absent » pour `.env.production` (chercher sous `/opt/bea-digital`, pas `/`). Les contrôles Docker / santé restent valides.

| Contrôle | Résultat 15/11 | vs dossier 13/11 |
|----------|----------------|------------------|
| Hôte | `srvsuividep-virtual-machine` | conforme |
| Disque `/` | 17 Go utilisés / 2,0 To (1 %) | ~14–15 Go → légère hausse |
| RAM | 4,5 Gi utilisés / 15 Gi ; swap ~2 Mi | conforme |
| Uptime | 2 jours | — |
| Conteneurs | 6 Up ; backend/worker/postgres/redis **healthy** ; frontend + pgAdmin Up | conforme (`v1.0.0`) |
| Volumes | `bea_postgres_data`, `bea_pgadmin_data`, volume Redis anonyme | inchangés — **préservés** |
| Docker df | 5 images, 6 conteneurs, 3 volumes, 0 reclaimable | conforme |
| `/health/ready` | `status=ok`, database ok, redis ok | conforme |
| `/version` | `v1.0.0`, `env=production`, `git_sha=unknown` | conforme |
| Montages GED/uploads/backups | toujours sous `…/import/incoming/release-source/…` | **alerte confirmée** |
| Taille GED montée (`release-source/.../ged`) | `0` | aucun fichier métier encore |
| Taille uploads montée (`release-source/.../uploads`) | `0` | aucun fichier métier encore |
| `/srv/bea-digital/uploads` | `304K` | **non monté** par les conteneurs (divergence) |
| `/srv/bea-digital/GED` | absent ou vide (pas listé par `du`) | non monté |

**Verdict serveur au 15/11 :** `v1.0.0` toujours actif et sain. Pas de données GED/uploads dans les montages actifs → risque de perte immédiat faible. La bascule vers `/srv` reste **obligatoire avant la prochaine release** (sinon le jour où des fichiers arriveront sous `release-source`, un remplacement de ce dossier les effacera). Les `304K` sous `/srv/.../uploads` ne sont pas vus par l’appli aujourd’hui. Ne pas toucher aux volumes.

Vérification fichiers sensibles (15/11, depuis `/opt/bea-digital`) :

| Fichier | Résultat |
|---------|----------|
| `.env.production` | présent, mode `600`, 2973 o, 13/11 17:04 |
| `deployment/state/secret_key.sha256` | présent, mode `600`, 65 o, 13/11 19:46 |
| `deployment/state/version_courante` | **absent** au premier contrôle ; **créé le 15/11** (`echo 'v1.0.0'`, mode `600`) |

L’absence initiale de `version_courante` n’empêchait pas l’appli de tourner (`/version` = `v1.0.0`). Elle indiquait seulement que l’état géré par `deploy.sh` n’avait pas été initialisé. Création effectuée le 15/11 sans toucher à la clé ni au MFA.

Ne **pas** coller le contenu du script diagnostic dans le terminal interactif. Relancer ensuite :

```bash
cd /opt/bea-digital && bash deployment/scripts/diagnose-readonly.sh
```

---

## 8. À confirmer avec IT / Sécurité / Conformité

- IP fixe vs réservation DHCP, DNS, hostname officiel clients
- Pare-feu, politique AnyDesk, accès d’administration
- Expiration / renouvellement certificats TLS
- Sauvegardes hors machine, chiffrement, rétention, tests de restauration
- Cible permanente GED / uploads / backups (`/srv` vs `release-source`)
- Matrice modules (EER, Clientèle, Réclamations)
- Supervision, rotation logs, politique de patch des images (`postgres:17`, `pgadmin:latest`)

---

## 9. Suite avant toute mise à jour

1. Relancer `diagnose-readonly.sh` **sur** la VM et archiver la sortie.
2. Stabiliser les chemins persistants ([doc 11](11-migration-stockage-persistant.md)).
3. Préparer une release seulement avec `images.tar` + `.sha256` + `manifest.json` complets.
4. Laisser `deploy.sh` appliquer la [porte de release](08-livraison-et-mises-a-jour.md#porte-de-release) (images, checksum, `SECRET_KEY`, montages, sauvegarde).
5. Ne pas déployer « pour tester » sur la machine bancaire.
)
