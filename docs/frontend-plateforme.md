# Front plateforme — une seule application Angular

BEA DIGITAL est **greffée** sur `frontend/angular20/`. Il n’y a pas de second
front, pas de rewrite React/Next, pas de dépendance ajoutée au `package.json`
pour le chrome.

## Contrat de routes des modules (figé)

Source de vérité code : `plateforme/module-routing.contract.ts`.

| Module | Stratégie | URLs | Entrée Login 2 | Logout module → |
|--------|-----------|------|----------------|-----------------|
| `immobilisations` | `legacy-root` | racine (`/dashboard`, `/immobilisations`, …) | `/dashboard` | `/comptabilite` |
| `credit` | `prefixed` | `/credit/...` | `/credit` | `/credit` |
| `rh` | `prefixed` | `/rh/...` | `/rh` | `/rh` |
| `tickets-si` | `prefixed` | `/tickets-si/...` | `/tickets-si` | `/informatique` |
| `demandes-achat` | `prefixed` | `/demandes-achat/...` | `/demandes-achat` | `/achats` |

Futurs modules encore **bientôt** (pas de shell métier) — détail processus :
[catalogue-modules-futurs.md](catalogue-modules-futurs.md).

Règles :

1. **Ne jamais** déplacer l’immo sous `/comptabilite/immobilisations/` (liens absolus + notifications).
2. **Ne jamais** réutiliser à la racine les segments de `LEGACY_ROOT_PATH_SEGMENTS` pour un autre module.
3. Pour un nouveau module : ajouter une entrée dans `MODULE_ROUTE_CONTRACTS`, un bloc
   `path: '{code}'` + `moduleGuard('{code}')` dans `app.routes.ts` (shell dédié ou lazy),
   et un `entry_path` en base / catalogue.
4. Plateforme (`/accueil`, `/comptabilite`, `/admin`, `/modules/:code/acces`) reste hors shell métier.

## Chrome

Dossier : `frontend/angular20/src/app/plateforme/`

| Fichier | Rôle |
|---------|------|
| `module-routing.contract.ts` | Contrat URLs modules (legacy-root vs prefixed) |
| `espaces-metiers.ts` | Types + libellés fil d’Ariane immo — **pas** le catalogue (API) |
| `chrome/bea-chrome.component.ts` | Bandeau BEA DIGITAL (pages Accueil / Comptabilité) |
| `fil-ariane/fil-ariane.component.ts` | Miettes dans le **shell** du module immo |
| `accueil/accueil.component.ts` | Cartes départements via `GET /plateforme/espaces` |
| `espace-hub/espace-hub.component.ts` | Hub département dynamique `/{code}` |
| `espace-hub.guard.ts` | Refuse segments réservés (immo / admin) |
| `plateforme.routes.ts` | Accueil, hubs, Login 2, CORE ADMIN |
| `plateforme-ui.css` | Jetons (bleus institutionnels des graphiques immo) |

## Accueil & hubs départements (dynamiques)

- Accueil : `GET /plateforme/espaces` (DB live, pas un catalogue front figé).
- Hub : `/{code}` via `EspaceHubComponent` (ex. `/comptabilite`, `/credit`).
  Segments réservés (immo + admin) exclus par `espaceHubCanMatch`.
- Création CORE ADMIN d’un département → route défaut `/{code}` → carte Accueil
  (statut actif + grant utilisateur, ou superuser).
- Module `bientot` : carte non ouvrable. Module `actif` : Login 2 ; shell métier
  seulement pour Immobilisations tant que les ateliers n’ont pas abouti.

Catalogue espaces/modules : seed backend `plateforme_catalogue.py` → tables
`plateforme_espaces` / `plateforme_modules` → API. Aucun doublon hardcodé dans le front.

Voir [catalogue-modules-futurs.md](catalogue-modules-futurs.md).

Standalone Angular 20, `OnPush`, sans Material / Tailwind / police d’icônes
supplémentaires dans ce dossier.

## Câblage des routes (`app.routes.ts`)

1. Login / forgot / reset inchangés (`guestGuard`).
2. `{ path: '', pathMatch: 'full', redirectTo: 'accueil' }`.
3. `...PLATEFORME_ROUTES` **avant** la route `''` de `ShellComponent`
   (sinon le prefix matching du shell avale `accueil` / `comptabilite`),
   avec `canActivate: [authGuard]`.
4. Bloc `ShellComponent` + enfants **tels quels** (mêmes paths module immo, `legacy-root`).
5. Futurs modules : blocs `path: 'credit'` (etc.) **à côté**, jamais dans le shell immo.
6. `**` → `accueil` (plus `dashboard`).

Après login → `/accueil`. `guestGuard` (déjà connecté) → `/accueil`.

## Fil d’Ariane — dans le shell, pas au-dessus

Le shell est en `height: 100vh`. Un bandeau empilé **au-dessus** pousserait
le contenu hors écran.

`<bea-fil-ariane>` est inséré **dans** `shell.component.html`, sous la topbar.

Miettes (génériques) : `Accueil → {espace} → {module}` (+ écran courant).
Titres et routes viennent de `PlateformeContextService` (API Login 2 /
`GET /plateforme/modules/{code}`), pas de chaînes hardcodées « Comptabilité ».

`app-shell__main` : `min-height: calc(100vh - 4rem - 2.5rem)`
(topbar 4rem + fil d’Ariane 2.5rem).

Déconnexion module : retour via `espace_route` du contexte / contrat
(`module-routing.contract.ts`) — jamais Login 1.

## Pourquoi on ne préfixe PAS sous `/comptabilite/immobilisations/`

La hiérarchie produit est :

```text
BEA DIGITAL → Comptabilité → Immobilisations & Amortissements
```

Les chemins d’URL du module restent `/dashboard`, `/immobilisations`,
`/amortissements`, `/archives`, etc.

Raisons :

- environ **60 liens absolus** dans le front (`routerLink="/immobilisations"`, …) ;
- des **liens de notification** produits par le backend et ouverts via
  `router.navigateByUrl(link)` — déjà stockés / générés sans préfixe plateforme.

Re-préfixer casserait des flux métier et des liens déjà en base. La hiérarchie
= navigation + fil d’Ariane, pas le chemin d’URL.

Les URLs API `/api/v1/...` restent inchangées.
