# Front plateforme — une seule application Angular

BEA DIGITAL est **greffée** sur `frontend/angular20/`. Il n’y a pas de second
front, pas de rewrite React/Next, pas de dépendance ajoutée au `package.json`
pour le chrome.

## Chrome

Dossier : `frontend/angular20/src/app/plateforme/`

| Fichier | Rôle |
|---------|------|
| `espaces-metiers.ts` | Catalogue : Comptabilité actif + module immo actif ; Crédit / RH / IT / Achats = bientôt |
| `chrome/bea-chrome.component.ts` | Bandeau BEA DIGITAL (pages Accueil / Comptabilité) |
| `fil-ariane/fil-ariane.component.ts` | Miettes dans le **shell** du module immo |
| `accueil/accueil.component.ts` | Cartes des espaces métiers |
| `comptabilite/comptabilite.component.ts` | Carte Immobilisations & Amortissements → `/dashboard` |
| `plateforme.routes.ts` | Routes `accueil` et `comptabilite` |
| `plateforme-ui.css` | Jetons (vert banque, or accent) |

Standalone Angular 20, `OnPush`, sans Material / Tailwind / police d’icônes
supplémentaires dans ce dossier.

## Câblage des routes (`app.routes.ts`)

1. Login / forgot / reset inchangés (`guestGuard`).
2. `{ path: '', pathMatch: 'full', redirectTo: 'accueil' }`.
3. `...PLATEFORME_ROUTES` **avant** la route `''` de `ShellComponent`
   (sinon le prefix matching du shell avale `accueil` / `comptabilite`),
   avec `canActivate: [authGuard]`.
4. Bloc `ShellComponent` + enfants **tels quels** (mêmes paths module).
5. `**` → `accueil` (plus `dashboard`).

Après login → `/accueil`. `guestGuard` (déjà connecté) → `/accueil`.

## Fil d’Ariane — dans le shell, pas au-dessus

Le shell est en `height: 100vh`. Un bandeau empilé **au-dessus** pousserait
le contenu hors écran.

`<bea-fil-ariane>` est inséré **dans** `shell.component.html`, sous la topbar.

Miettes : `Accueil → Comptabilité → Immobilisations & Amortissements`
(+ écran courant du module le cas échéant).

`app-shell__main` : `min-height: calc(100vh - 4rem - 2.5rem)`
(topbar 4rem + fil d’Ariane 2.5rem).

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
