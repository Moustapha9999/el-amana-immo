# Sources éditables des diagrammes d’architecture

Fichiers Mermaid (`.mmd`), éditables dans tout outil compatible (GitHub, GitLab, mermaid.live,
extension VS Code / Cursor). Ils sont recopiés dans les documents Markdown correspondants.

| Fichier | Titre | Document |
|---|---|---|
| `01-contexte.mmd` | Contexte général (C4-1) | architecture-generale.md |
| `02-conteneurs.mmd` | Conteneurs techniques (C4-2) | architecture-technique.md |
| `03-composants-backend.mmd` | Composants FastAPI (C4-3) | architecture-technique.md |
| `04-fonctionnel.mmd` | Modules et socle | architecture-fonctionnelle.md |
| `05-securite.mmd` | Frontières de confiance | architecture-securite.md |
| `06-deploiement.mmd` | Local constaté vs cible TEST/PROD | architecture-deploiement.md |
| `07-flux-integrations.mmd` | Flux et intégrations | flux-integrations.md |
| `08-domaines-donnees.mmd` | Domaines de données | architecture-donnees.md |
| `09-couches.mmd` | Frontend, API, Backend, Docker, Base | couches.md |

## Convention graphique

| Style | Signification |
|---|---|
| Fond vert, trait plein | Existant, vérifié dans le code ou en fonctionnement local |
| Fond orange, trait pointillé | Partiel, documenté, usage à confirmer |
| Fond gris, trait pointillé fin | Prévu, inactif ou non configuré |
| Fond rouge | Point d’exposition ou donnée sensible |
| Flèche pleine | Flux constaté |
| Flèche pointillée | Flux manuel, conditionnel ou cible |

Ne pas ajouter de serveur, d’adresse IP, de certificat ou de lien qui n’existerait que par
hypothèse. Si un flux n’est pas démontré, le tracer en pointillé et le commenter.
