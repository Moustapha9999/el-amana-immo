# Dossier d’architecture — BEA DIGITAL

Documentation d’architecture destinée au DSI de Banque El Amana. Produite le **22 octobre 2026**
par audit en lecture seule du dépôt. **Elle ne remplace pas** les documents opérationnels existants
(`docs/securite-bea-digital.md`, `docs/deployment/`, `docs/core-*.md`, `docs/conformite/`).

## Point d’entrée

**[architecture-generale.md](architecture-generale.md)** — document principal (page de garde,
résumé exécutif, quinze sections).

**[couches.md](couches.md)** — lecture rapide par couche : Frontend, API, Backend, Docker, Base.

## Détails

| Document | Contenu |
|---|---|
| [architecture-fonctionnelle.md](architecture-fonctionnelle.md) | Espaces, modules, matrice, rôles |
| [couches.md](couches.md) | Frontend, API, Backend, Docker, Base (et le reste) |
| [architecture-technique.md](architecture-technique.md) | Conteneurs, versions, frontend, backend, tests |
| [architecture-securite.md](architecture-securite.md) | Auth, RBAC, réseau, secrets, audit |
| [architecture-donnees.md](architecture-donnees.md) | Domaines de données, tables, conservation |
| [architecture-deploiement.md](architecture-deploiement.md) | Environnements, CI/CD, scripts |
| [flux-integrations.md](flux-integrations.md) | ORION, BCM, SMTP, ClamAV, Studio |
| [risques-et-recommandations.md](risques-et-recommandations.md) | 18 risques sourcés |

## Diagrammes

Sources éditables Mermaid dans [diagrams/](diagrams/). Chaque schéma est aussi recopié dans le
document qui le commente (rendu GitHub / GitLab).

| Fichier | Vue C4 |
|---|---|
| [01-contexte.mmd](diagrams/01-contexte.mmd) | Contexte |
| [02-conteneurs.mmd](diagrams/02-conteneurs.mmd) | Conteneurs |
| [03-composants-backend.mmd](diagrams/03-composants-backend.mmd) | Composants backend |
| [04-fonctionnel.mmd](diagrams/04-fonctionnel.mmd) | Architecture fonctionnelle |
| [05-securite.mmd](diagrams/05-securite.mmd) | Sécurité |
| [06-deploiement.mmd](diagrams/06-deploiement.mmd) | Déploiement |
| [07-flux-integrations.mmd](diagrams/07-flux-integrations.mmd) | Flux et intégrations |
| [08-domaines-donnees.mmd](diagrams/08-domaines-donnees.mmd) | Domaines de données |
| [09-couches.mmd](diagrams/09-couches.mmd) | Couches Frontend / API / Backend / Docker / Base |

Convention : **vert** = existant vérifié ; **orange pointillé** = partiel / à confirmer ; **gris** =
prévu ou inactif ; **rouge** = point d’exposition. Trait plein = flux constaté ; pointillé = flux
manuel, conditionnel ou cible.

## Version imprimable

`pandoc` n’est pas installé sur le poste d’audit. Pour produire un PDF :

```powershell
# Après installation de pandoc + un moteur PDF (wkhtmltopdf ou LaTeX) :
pandoc docs/architecture/architecture-generale.md -o docs/architecture/BEA-DIGITAL-architecture-generale.pdf --from markdown --toc
```

En attendant, le fichier Markdown ci-dessus s’imprime depuis GitHub, GitLab ou un éditeur
Markdown (Cursor, VS Code) via « Imprimer » / « Exporter PDF ».

## Conventions de statut

| Libellé | Signification |
|---|---|
| **Vérifié** | Constaté dans le code, la configuration ou en fonctionnement local le 22/10/2026 |
| **Déclaré** | Présent dans un fichier de dépendances ou une documentation ; non relancé par l’audit |
| **Partiel** | Implémenté de façon incomplète, optionnelle ou non configurée |
| **Non vérifié** | Présent, mais aucun parcours ni test n’a été exécuté ici |
| **À confirmer (DSI)** | Hors dépôt : infrastructure, procédure, décision |

## Règles de lecture

- Une fonction n’est jamais déclarée opérationnelle sur la seule présence d’un menu.
- Un secret, un mot de passe, un jeton ou une donnée nominative n’apparaît pas dans ces pages.
- Les statuts de module sont ceux de l’**instance locale** du 22/10/2026 ; CORE ADMIN peut les
  changer.
