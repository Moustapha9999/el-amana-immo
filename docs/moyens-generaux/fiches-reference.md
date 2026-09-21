# Fiches papier — références design

Sources métier Banque El Amana (Service Moyens Généraux). Les écrans digitaux
reprennent la structure (en-tête BEA, tableaux, zones de visa) et l’améliorent
(sélections agences, calculs auto, charts).

## Assets

| Fichier | Usage |
|---------|--------|
| [references/logo-bea.jpg](references/logo-bea.jpg) | Charte / PDF |
| [references/fiche-expression-besoin.jpg](references/fiche-expression-besoin.jpg) | Demande de fourniture (Phase 1) |
| [references/fiche-note-de-frais.jpg](references/fiche-note-de-frais.jpg) | Notes de frais (Phase 2) |
| [references/fiche-bon-de-commande.jpg](references/fiche-bon-de-commande.jpg) | Achats / BC (Phase 2) |

## Mapping

| Fiche papier | Module digital |
|--------------|----------------|
| Expression de besoin / Bon de sortie | Stock — Demandes de fourniture (Phase 1) |
| Note de frais | Notes de frais (Phase 2) |
| Bon de commande | Achats & Approvisionnements (Phase 2) |

## Design

- Couleurs plateforme BEA (navy / brand existant dans `plateforme-ui.css`).
- Pas de Material / Tailwind supplémentaires dans `plateforme/` ou le shell stock.
- Dashboard : graphiques SVG/CSS simples (même esprit que CORE ADMIN charts).
