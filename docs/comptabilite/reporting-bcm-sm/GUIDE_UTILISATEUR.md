# Guide utilisateur — Reporting BCM SM

**SM = Situation Mensuelle.** Dans l’interface métier, on ne parle plus de « campagne ».

## Navigation

- Accueil — pilotage et indicateurs
- Situations mensuelles — liste des SM
- Nouvelle SM — création d’un brouillon
- Imports — BAL DET uniquement (analyse → prévisualisation → confirmation)
- BAL DET — consultation paginée (lecture seule)
- Contrôles — contrôles internes BAL DET
- Paramètres — huit paramètres mensuels (sans reconduction N−1)
- Correspondances — 242 règles en `A_VALIDER` (pas d’activation)
- Archives BAL COND — historique uniquement, hors workflow

## Cycle d’une SM

1. Créer la SM (période / version)
2. Importer et confirmer la BAL DET
3. Consulter / lancer les contrôles internes
4. Saisir et valider les paramètres
5. Mapping et état réglementaire — **bloqués** tant que D01/D02 ne sont pas tranchés

## Décisions bloquantes

| Code | Sujet | Effet UI |
|------|--------|----------|
| D01 | Arbitrage mapping | Pas d’activation des règles ; workflow réglementaire verrouillé |
| D02 | Formalisation ECART | ECART désactivé |

## Vocabulaire

| Ancien | Actuel |
|--------|--------|
| Campagne | SM / Situation Mensuelle |
| Nouvelle campagne | Nouvelle SM |
| Fiche campagne | Fiche SM |
