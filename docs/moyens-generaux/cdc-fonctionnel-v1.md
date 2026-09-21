# Cahier des charges fonctionnel — Moyens Généraux

**Version :** 1.1  
**Plateforme :** BEA-DIGITAL  
**Département :** Moyens Généraux  
**Contact métier (stock) :** Fatimata DIOP — Chef section logistique & moyens généraux — fatimatadiop@bea.mr

ORION reste le core banking. BEA DIGITAL digitalise les processus internes MG (formulaires, Excel, e-mails).

## Architecture

```text
BEA-DIGITAL
└── MOYENS GÉNÉRAUX (/moyens-generaux)
    ├── Dashboard département
    ├── 01 Achats & Approvisionnements   (actif)
    ├── 02 Stock & Fournitures           (actif)
    ├── 03 Notes de Frais                (actif)
    ├── 04 Contrats & Échéances          (actif)
    └── 05 Archives MG                   (actif)
```

Services CORE : utilisateurs, départements, agences, rôles, permissions, notifications, GED, audit, reporting.

## Principes transverses

1. **Référentiels** : sélections uniquement (`agences`, `users`, `departements`, `fournisseurs`) — pas de texte libre pour ces entités.
2. **Snapshot documentaire** : FK + copie figée (libellé / adresse) au moment de la génération PDF.
3. **GED** : documents via `ged_documents` (pas d’URL publique).
4. **Archives MG** : vue centralisée des documents des 4 autres modules.
5. **Routes** : modules préfixés `/{code}/...` (jamais les URLs racine Immobilisations).
6. **Permissions** : `mg.stock.*`, `mg.purchase.*`, `mg.notes.*`, `mg.contrats.*`, `mg.archives.*`.

## Module 02 — Stock & Fournitures

Demande initiale Fatimata DIOP : suivi entrées/sorties, familles, quantités temps réel, rapports conso, UI simple.

Détail : [conception-technique-stock.md](conception-technique-stock.md).

## Modules 01 / 03 / 04 / 05

| Module | Code | Entry | API |
|--------|------|-------|-----|
| Achats (BC) | `achats-appro` | `/achats-appro/bons` | `/api/v1/mg/achats` |
| Notes de frais | `notes-frais` | `/notes-frais/notes` | `/api/v1/mg/notes-frais` |
| Contrats | `contrats-echeances` | `/contrats-echeances/liste` | `/api/v1/mg/contrats` |
| Archives | `archives-mg` | `/archives-mg/registre` | `/api/v1/mg/archives` |

Détail : [conception-technique-phase2.md](conception-technique-phase2.md).

Hors scope actuel : workflow BL / facture / paiement ORION ; suppression physique archives.

## Fiches papier de référence

[fiches-reference.md](fiches-reference.md)
