# T3.5-3 T0 — Audit du canevas officiel et plan d’intégration

Branche : `feat/reporting-bcm-sm-t3` · HEAD Git inchangé `091b57c`  
**Audit et conception uniquement. Aucun code métier modifié. Aucun commit / push / rebuild / déploiement.**  
T3.5-4, T3.5-5, T3.5-6 **non commencés**. Mapping 242 `A_VALIDER` et ECART **non activés**.  
`engine/runner.py` **non modifié**. SM `11/2026` et `01/2026` **non touchées**. Migrations `rbcm_01`–`rbcm_04` **préservées**.

Références : `T3_5_WORKFLOW_CONCEPTION.md`, `T3_5_1_REPORT.md`, `T3_5_2_REPORT.md`, `T3_5_2_REVIEW_COMPLEMENTAIRE.md`.

La préparation WORK **n’est jamais** une approbation réglementaire.

---

## 1. Inventaire du canevas officiel

Fichier examiné (présent à la racine du dépôt, **pas** la maquette) :

| Propriété | Valeur mesurée |
|-----------|----------------|
| Chemin | `BEA-SM-10-2026.xlsx` |
| Taille | 78 202 octets |
| SHA-256 | `54e3b687434f4901889c1164b8d6d7fbc3bd225a117b1b36016c84e8fc852658` |
| openpyxl | 3.1.5 (déjà dans `backend/requirements.txt`) |
| Feuilles | **8**, toutes visibles |
| Formules | **663** |
| Noms définis | **7** (`fond_*`) |

`Copie de Maquette SM-RC-MF.xlsx` n’a **pas** servi de structure. Elle reste une aide au mapping de comptes.

**Constats structurels majeurs :**

1. Le fichier n’est **pas** un modèle vide. C’est une **SM octobre 2026 déjà remplie** (date `2026-10-31`, banque `BEA`, montants en dur).
2. Les totaux sont surtout des formules `SUM` / `+cellules`.
3. Neuf formules d’ETAT A **incrustent des constantes d’octobre** (dont `2873218`, proche de l’ECART historique). Ce ne sont pas des règles réutilisables.
4. L’export actuel (`excel_export.py`) crée un classeur technique **sans** ces huit feuilles officielles. Il n’est pas le livrable.

Noms définis (zones « fond » du classeur, lus dans le fichier) :

| Nom | Portée |
|-----|--------|
| `fond_situation_mensuelle` | ETAT A colonnes C–G, lignes de détail |
| `fond_concours_economie` | ETAT B C–H |
| `fond_emploi_ressource` | ETAT C C–E |
| `fond_fond_propre_net` | CALCUL FPN `C19`, `C21` |
| `fond_liquidite_1` | RATIO DE LIQUIDITE `D23`, `D12` |
| `fond_fp_ai` | RATIO FP ET AI `C9` |
| `fond1_couverture_risque` | RATIO COUVERTURE `E7:E17`, `E20:E25` |

---

## 2. Cartographie des huit feuilles

| # | Nom exact | Dimensions utilisées | Fusions | Lignes non vides | Formules | Rôle |
|---|-----------|----------------------|---------|------------------|----------|------|
| 1 | `informations à fournir` | A1:F20 | 0 | 19 | 1 | Annexes FPN |
| 2 | `ETAT A` | A1:K181 | 8 | 167 | 306 | Situation mensuelle — **157 codes BCM** 101–520 |
| 3 | `ETAT B` | A1:U101 | 16 | 54 | 136 | Concours à l’économie — **48 codes** 101–216 |
| 4 | `ETAT C` | A1:P53 | 0 | 49 | 92 | Emplois / ressources / engagements par maturité — **40 codes** |
| 5 | `CALCUL FPN` | A1:I49 | 0 | 39 | 30 | Fonds propres nets |
| 6 | `RATIO COUVERTURE DE RISQUE` | A1:K600 (30 lignes réellement remplies) | 0 | 30 | 57 | Pondérations + ratio |
| 7 | `RATIO DE LIQUIDITE` | A1:AB50 | 0 | 44 | 31 | Actifs liquides / exigibilités |
| 8 | `RATIO FP ET AI` | A1:I18 | 0 | 16 | 10 | Fonds propres / immobilisations |

En-tête commun mesuré (toutes les feuilles) :

| Cellule | Contenu octobre |
|---------|-----------------|
| A1 | Banque Centrale de Mauritanie Direction de Contrôle des Banques |
| A2 | Intitulé d’état + « arrêté le: » |
| B2 | `2026-10-31` |
| A3 | Banque déclarante : |
| B3 | `BEA` |
| D1 / E1 | Codes de mise en page `L` + nombre de lignes ; `C` + nombre de colonnes |

### ETAT A — axes (lignes 5–7, fusions D5:E5, F5:G5, B5:B6, C5:C6)

| Colonne | En-tête officiel | Sens |
|---------|------------------|------|
| A | Libellé | Rubrique |
| B | CODE BCM | 101–520 |
| C | PROVISIONS ET AMORTISSEMENTS | Axe 1 |
| D | OUGUIYAS / RESIDENTS | Axe 2 |
| E | OUGUIYAS / NON RESIDENTS | Axe 3 |
| F | DEVISES / RESIDENTS | Axe 4 |
| G | DEVISES / NON RESIDENTS | Axe 5 |
| H | Total | `SUM(D:G)` sur les lignes de détail |
| I147 | Contrôle | `=+H147-H81` (passif − actif), cache octobre = 0 |

Blocs : Actif (l.7–81, codes 101–240) · Passif (l.83–147, codes 301–427) · Hors-bilan (l.150–171, codes 501–520).  
Lignes « …… » (112, 116, 120, 124, 208, 222, 307, 311, 315, 333, 334, 405) : **séparateurs sans montant**.

### ETAT B — axes (fusions C5:G5, etc.)

| Colonne | En-tête |
|---------|---------|
| A | Libellé |
| B / J | CODE BCM (doublé) |
| C–G | RESIDENTS : EPA, EPC, privé, particuliers, divers |
| H | NON RESIDENTS |
| I | TOTAL `SUM(C:H)` |
| L | POUR CONTRÔLE (`IF` vs totaux ETAT A) |

### ETAT C — axes

Emplois l.5–25 (codes 101–120) puis Ressources l.27–50 (codes 201–220).  
Colonnes C/D/E = maturités `< 3 mois` / `3 mois–2 ans` / `> 2 ans` ; F = TOTAL ; I = POUR CONTRÔLE vs ETAT A.

---

## 3. Cartographie des cellules et rubriques (ETAT A)

Nature lue dans le fichier officiel (openpyxl, formules non évaluées par Python) :

| Nature | Signification |
|--------|----------------|
| `FORMULE` | Agrégat structurel (`SUM`, `+C9+C10`, …) — à **conserver** |
| `FORMULE_CONSTANTE` | Formule contenant un montant d’octobre — **ne pas réutiliser** |
| `VALEUR` | Nombre d’octobre (feuille saisie) |
| `ZERO` | Nombre `0` écrit dans le fichier d’octobre (zéro réel **ou** case remplie à 0 — indiscernable) |
| `VIDE` | Aucune valeur dans la cellule |

Comptage ETAT A, colonnes C–H, 157 codes : FORMULE 296 · ZERO 409 · VIDE 185 · VALEUR 43 · FORMULE_CONSTANTE 9.

| Ligne | Code | Libellé | C | D | E | F | G | H |
|------:|-----:|---------|---|---|---|---|---|---|
| 8 | 101 | Caisse | FORMULE | FORMULE | FORMULE | FORMULE | FORMULE | FORMULE |
| 9 | 102 | Billets et monnaies | ZERO | FORMULE_CONSTANTE | ZERO | VALEUR | ZERO | FORMULE |
| 10 | 103 | Autres avoirs | ZERO | ZERO | ZERO | ZERO | ZERO | FORMULE |
| 11 | 104 | Institut d'émission, Trésor Public, CCP | FORMULE | FORMULE | FORMULE | FORMULE | FORMULE | FORMULE |
| 12 | 105 | Institut d'émission | ZERO | VALEUR | VIDE | VIDE | ZERO | FORMULE |
| 13 | 106 | Trésor Public, comptes courants postaux | ZERO | VIDE | ZERO | ZERO | ZERO | FORMULE |
| 14 | 107 | Etablissements de crédit et Intermédiaires Financiers | FORMULE | FORMULE | FORMULE | FORMULE | FORMULE | FORMULE |
| 15 | 108 | Comptes Ordinaires | FORMULE | FORMULE | FORMULE | FORMULE | FORMULE | FORMULE |
| 16 | 109 | Banques et correspondants étrangers | ZERO | ZERO | ZERO | ZERO | VALEUR | FORMULE |
| 17 | 110 | Etablissements financiers | ZERO | VIDE | ZERO | ZERO | VALEUR | FORMULE |
| 18 | 111 | Dispositions - Cession | ZERO | ZERO | ZERO | ZERO | ZERO | FORMULE |
| 19 | 112 | (séparateur) | VIDE | VIDE | VIDE | VIDE | VIDE | VIDE |
| 20 | 113 | Prêts au jour le jour | FORMULE | FORMULE | FORMULE | FORMULE | FORMULE | FORMULE |
| 21 | 114 | Banques et correspondants étrangers | ZERO | FORMULE_CONSTANTE | ZERO | ZERO | ZERO | FORMULE |
| 22 | 115 | Etablissements financiers | ZERO | ZERO | ZERO | ZERO | ZERO | FORMULE |
| 23 | 116 | (séparateur) | VIDE | VIDE | VIDE | VIDE | VIDE | VIDE |
| 24 | 117 | Comptes Prêts à terme | FORMULE | FORMULE | FORMULE | FORMULE | FORMULE | FORMULE |
| 25 | 118 | Banques et correspondants étrangers | ZERO | VIDE | ZERO | VIDE | VIDE | FORMULE |
| 26 | 119 | Etablissements financiers | ZERO | VIDE | ZERO | ZERO | ZERO | FORMULE |
| 27 | 120 | (séparateur) | VIDE | VIDE | VIDE | VIDE | VIDE | VIDE |
| 28 | 121 | Créances immobilisées, douteuses, intransférables | ZERO | ZERO | ZERO | ZERO | ZERO | FORMULE |
| 29 | 122 | Valeurs reçues en pension au jour le jour | ZERO | ZERO | ZERO | ZERO | ZERO | FORMULE |
| 30 | 123 | Valeurs reçues en pension à terme ou achetées ferme | ZERO | ZERO | ZERO | ZERO | ZERO | FORMULE |
| 31 | 124 | (séparateur) | VIDE | VIDE | VIDE | VIDE | VIDE | VIDE |
| 32 | 125 | Crédits à la clientèle | FORMULE | FORMULE | FORMULE | FORMULE | FORMULE | FORMULE |
| 33 | 126 | Créances commerciales | VIDE | VALEUR | ZERO | ZERO | ZERO | FORMULE |
| 34 | 127 | Autres crédits à court terme | VIDE | VALEUR | ZERO | ZERO | ZERO | FORMULE |
| 35 | 128 | Crédits à moyen terme | VIDE | VALEUR | ZERO | ZERO | ZERO | FORMULE |
| 36 | 129 | Crédits à long terme | VIDE | VALEUR | ZERO | ZERO | ZERO | FORMULE |
| 37 | 130 | Valeurs non imputées | VIDE | ZERO | ZERO | ZERO | ZERO | FORMULE |
| 38 | 131 | Comptes ordinaires débiteurs | VALEUR | FORMULE_CONSTANTE | ZERO | ZERO | ZERO | FORMULE |
| 39 | 132 | Créances restructurées | VIDE | VALEUR | ZERO | ZERO | ZERO | FORMULE |
| 40 | 133 | Créances immobilisées | VIDE | VALEUR | ZERO | ZERO | ZERO | FORMULE |
| 41 | 134 | Créances douteuses ou litigieuses | VIDE | VALEUR | ZERO | ZERO | ZERO | FORMULE |
| 42 | 201 | Chèques à recouvrer | VIDE | VALEUR | ZERO | ZERO | ZERO | FORMULE |
| 43 | 202 | Effets en recouvrements reçus des correspondants | ZERO | ZERO | ZERO | ZERO | ZERO | FORMULE |
| 44 | 203 | Effets à l'encaisse, reçus de la clientèle | FORMULE | FORMULE | FORMULE | FORMULE | FORMULE | FORMULE |
| 45 | 204 | Effets à crédit immédiat | ZERO | ZERO | ZERO | ZERO | ZERO | FORMULE |
| 46 | 205 | Effets à l'encaissement non disponibles | ZERO | ZERO | ZERO | ZERO | ZERO | FORMULE |
| 47 | 206 | Débiteurs divers | VIDE | VALEUR | ZERO | ZERO | ZERO | FORMULE |
| 48 | 207 | Succursales et agences locales | ZERO | ZERO | ZERO | ZERO | ZERO | FORMULE |
| 49 | 208 | (séparateur) | VIDE | VIDE | VIDE | VIDE | VIDE | VIDE |
| 50 | 209 | Comptes de régularisation | FORMULE | FORMULE | FORMULE | FORMULE | FORMULE | FORMULE |
| 51 | 210 | Charges payées ou comptabilisées d'avance | ZERO | ZERO | ZERO | ZERO | ZERO | FORMULE |
| 52 | 211 | Produits à recouvrir | ZERO | VALEUR | ZERO | ZERO | ZERO | FORMULE |
| 53 | 212 | Ecart de conversion de devises | ZERO | ZERO | ZERO | ZERO | ZERO | FORMULE |
| 54 | 213 | Divers | ZERO | ZERO | ZERO | ZERO | ZERO | FORMULE |
| 55 | 214 | Opérations sur titres | ZERO | ZERO | ZERO | ZERO | ZERO | FORMULE |
| 56 | 215 | Titres de placement | FORMULE | FORMULE | FORMULE | FORMULE | FORMULE | FORMULE |
| 57 | 216 | Bons du Trésor et assimilés | ZERO | VALEUR | ZERO | ZERO | ZERO | FORMULE |
| 58 | 217 | Autres titres | ZERO | VALEUR | ZERO | ZERO | ZERO | FORMULE |
| 59 | 218 | Titres de participation et de filiales | FORMULE | FORMULE | FORMULE | FORMULE | FORMULE | FORMULE |
| 60 | 219 | Titres de participation | ZERO | VALEUR | ZERO | ZERO | ZERO | FORMULE |
| 61 | 220 | Titres de filiales | ZERO | ZERO | ZERO | ZERO | ZERO | FORMULE |
| 62 | 221 | Créances et autres emplois immobilisés | ZERO | ZERO | ZERO | ZERO | ZERO | FORMULE |
| 63 | 222 | (séparateur) | VIDE | VIDE | VIDE | VIDE | VIDE | VIDE |
| 64 | 223 | Prêts participatifs | ZERO | ZERO | ZERO | ZERO | ZERO | FORMULE |
| 65 | 224 | Immobilisations corporelles | FORMULE | FORMULE | FORMULE | FORMULE | FORMULE | FORMULE |
| 66 | 225 | Immobilisations d'exploitation | VALEUR | VALEUR | ZERO | ZERO | ZERO | FORMULE |
| 67 | 226 | Immobilisations hors exploitation | ZERO | ZERO | ZERO | ZERO | ZERO | FORMULE |
| 68 | 227 | Immobilisations en cours | ZERO | VIDE | ZERO | ZERO | ZERO | FORMULE |
| 69 | 228 | Opérations de crédit bail | FORMULE | FORMULE | FORMULE | FORMULE | FORMULE | FORMULE |
| 70 | 229 | Immobilisations en location | ZERO | ZERO | ZERO | ZERO | ZERO | FORMULE |
| 71 | 230 | Immobilisations en cours | ZERO | ZERO | ZERO | ZERO | ZERO | FORMULE |
| 72 | 231 | Immobilisations non louées après résiliation | ZERO | ZERO | ZERO | ZERO | ZERO | FORMULE |
| 73 | 232 | Opérations de location simple | ZERO | ZERO | ZERO | ZERO | ZERO | FORMULE |
| 74 | 233 | Frais et valeurs incorporelles immobilisés | FORMULE | FORMULE | FORMULE | FORMULE | FORMULE | FORMULE |
| 75 | 234 | Frais immobilisés | VALEUR | FORMULE_CONSTANTE | ZERO | ZERO | ZERO | FORMULE |
| 76 | 235 | Immobilisations incorporelles | VALEUR | FORMULE_CONSTANTE | ZERO | ZERO | ZERO | FORMULE |
| 77 | 236 | Actionnaires ou associés | ZERO | VALEUR | ZERO | ZERO | ZERO | FORMULE |
| 78 | 237 | Résultat en attente d'affectation | ZERO | ZERO | ZERO | ZERO | ZERO | FORMULE |
| 79 | 238 | Report à nouveau | ZERO | ZERO | ZERO | ZERO | ZERO | FORMULE |
| 80 | 239 | Excédent des charges sur les produits | ZERO | VIDE | ZERO | ZERO | ZERO | FORMULE |
| 81 | 240 | Total de l'actif | FORMULE | FORMULE | FORMULE | FORMULE | FORMULE | FORMULE |
| 85 | 301 | Institut d'émission, Trésor Public, CCP | VIDE | VIDE | ZERO | ZERO | ZERO | FORMULE |
| 86 | 302 | Etablissements de crédit et intermédiaires financiers | VIDE | FORMULE | FORMULE | FORMULE | FORMULE | FORMULE |
| 87 | 303 | Comptes ordinaires | VIDE | FORMULE | FORMULE | FORMULE | FORMULE | FORMULE |
| 88 | 304 | Banques et correspondants étrangers | VIDE | VIDE | ZERO | ZERO | VALEUR | FORMULE |
| 89 | 305 | Etablissements financiers | VIDE | ZERO | ZERO | ZERO | ZERO | FORMULE |
| 90 | 306 | Disposition- Prélèvement | VIDE | VALEUR | ZERO | ZERO | ZERO | FORMULE |
| 91 | 307 | (séparateur) | VIDE | VIDE | VIDE | VIDE | VIDE | VIDE |
| 92 | 308 | Emprunts au jour le jour | VIDE | FORMULE | FORMULE | FORMULE | FORMULE | FORMULE |
| 93 | 309 | Banques et correspondants étrangers | VIDE | VIDE | ZERO | ZERO | ZERO | FORMULE |
| 94 | 310 | Etablissements financiers | VIDE | VALEUR | ZERO | ZERO | ZERO | FORMULE |
| 95 | 311 | (séparateur) | VIDE | VIDE | VIDE | VIDE | VIDE | VIDE |
| 96 | 312 | Comptes et emprunts à terme | VIDE | FORMULE | FORMULE | FORMULE | FORMULE | FORMULE |
| 97 | 313 | Banques et correspondants étrangers | VIDE | ZERO | ZERO | ZERO | VALEUR | FORMULE |
| 98 | 314 | Etablissements financiers | VIDE | VIDE | ZERO | ZERO | ZERO | FORMULE |
| 99 | 315 | (séparateur) | VIDE | VIDE | VIDE | VIDE | VIDE | VIDE |
| 100 | 316 | Valeur données en pension au jour le jour | VIDE | VIDE | ZERO | ZERO | ZERO | FORMULE |
| 101 | 317 | Valeur données en pension a terme ou vendues ferme | VIDE | FORMULE | FORMULE | FORMULE | FORMULE | FORMULE |
| 102 | 318 | Refinancement BCM | VIDE | ZERO | ZERO | ZERO | ZERO | FORMULE |
| 103 | 319 | Refinancement autres intermédiaires financiers | VIDE | ZERO | ZERO | ZERO | ZERO | FORMULE |
| 104 | 320 | Comptes créditeurs de clientèle | VIDE | FORMULE | FORMULE | FORMULE | FORMULE | FORMULE |
| 105 | 321 | Comptes ordinaires créditeurs | VIDE | FORMULE | FORMULE | FORMULE | FORMULE | FORMULE |
| 106 | 322 | Etablissements publics et semi-publics | VIDE | FORMULE_CONSTANTE | VIDE | VALEUR | ZERO | FORMULE |
| 107 | 323 | Entreprises du secteur privé | VIDE | VALEUR | VIDE | VALEUR | ZERO | FORMULE |
| 108 | 324 | Particuliers | VIDE | VIDE | VIDE | VIDE | ZERO | FORMULE |
| 109 | 325 | Divers | VIDE | VALEUR | VIDE | VIDE | ZERO | FORMULE |
| 110 | 326 | Comptes créditeurs à terme | VIDE | FORMULE | FORMULE | FORMULE | FORMULE | FORMULE |
| 111 | 327 | Etablissements publics et semi-publics | VIDE | VALEUR | ZERO | ZERO | ZERO | FORMULE |
| 112 | 328 | Entreprises du secteur privé | VIDE | FORMULE_CONSTANTE | ZERO | ZERO | ZERO | FORMULE |
| 113 | 329 | Particuliers | VIDE | ZERO | ZERO | ZERO | ZERO | FORMULE |
| 114 | 330 | Divers | VIDE | ZERO | ZERO | ZERO | ZERO | FORMULE |
| 115 | 331 | Compte d'épargne à régime spécial | VIDE | FORMULE | FORMULE | FORMULE | FORMULE | FORMULE |
| 116 | 332 | Comptes sur livrets | VIDE | VALEUR | ZERO | ZERO | ZERO | FORMULE |
| 117 | 333 | (séparateur) | VIDE | VIDE | VIDE | VIDE | VIDE | VIDE |
| 118 | 334 | (séparateur) | VIDE | VIDE | VIDE | VIDE | VIDE | VIDE |
| 119 | 335 | Autres sommes dues à la clientèle | VIDE | VALEUR | ZERO | ZERO | ZERO | FORMULE |
| 120 | 336 | Bons de caisse | VIDE | ZERO | ZERO | ZERO | ZERO | FORMULE |
| 121 | 401 | Comptes de correspondants exigibles après encaissement | VIDE | ZERO | ZERO | ZERO | ZERO | FORMULE |
| 122 | 402 | Comptes de clientèle exigibles après encaissement | VIDE | VALEUR | VIDE | ZERO | ZERO | FORMULE |
| 123 | 403 | Créditeurs divers | VIDE | FORMULE_CONSTANTE | ZERO | ZERO | ZERO | FORMULE |
| 124 | 404 | Succursales et agences locales | VIDE | VIDE | ZERO | ZERO | ZERO | FORMULE |
| 125 | 405 | (séparateur) | VIDE | VIDE | VIDE | VIDE | VIDE | VIDE |
| 126 | 406 | Comptes de régularisation | VIDE | FORMULE | FORMULE | FORMULE | FORMULE | FORMULE |
| 127 | 407 | Charges à payer | VIDE | ZERO | ZERO | ZERO | ZERO | FORMULE |
| 128 | 408 | Produis perçus d'avance | VIDE | VALEUR | ZERO | ZERO | ZERO | FORMULE |
| 129 | 409 | Ecart de conversion devises | VIDE | ZERO | ZERO | ZERO | ZERO | FORMULE |
| 130 | 410 | Divers | VIDE | ZERO | ZERO | ZERO | ZERO | FORMULE |
| 131 | 411 | Opérations sur titres | VIDE | ZERO | ZERO | ZERO | ZERO | FORMULE |
| 132 | 412 | Versements à effectuer sur titres non libérés | VIDE | ZERO | ZERO | ZERO | ZERO | FORMULE |
| 133 | 413 | Emprunts obligatoires | VIDE | ZERO | ZERO | ZERO | ZERO | FORMULE |
| 134 | 414 | Autres ressources permanentes | VIDE | FORMULE | FORMULE | FORMULE | FORMULE | FORMULE |
| 135 | 415 | Subventions et fonds affectés | VIDE | ZERO | ZERO | ZERO | ZERO | FORMULE |
| 136 | 416 | Emprunts participatifs | VIDE | ZERO | ZERO | ZERO | ZERO | FORMULE |
| 137 | 417 | Autres ressources | VIDE | ZERO | ZERO | ZERO | ZERO | FORMULE |
| 138 | 418 | Provisions pour risques et charges | VIDE | VALEUR | ZERO | ZERO | ZERO | FORMULE |
| 139 | 419 | Plus-values et provisions réglementées | VIDE | ZERO | ZERO | ZERO | ZERO | FORMULE |
| 140 | 420 | Réserves | VIDE | FORMULE | FORMULE | FORMULE | FORMULE | FORMULE |
| 141 | 421 | Primes | VIDE | ZERO | ZERO | ZERO | ZERO | FORMULE |
| 142 | 422 | Autres réserves | VIDE | VALEUR | ZERO | ZERO | ZERO | FORMULE |
| 143 | 423 | Capital | VIDE | VALEUR | ZERO | ZERO | ZERO | FORMULE |
| 144 | 424 | Résultat en attente d'affectation | VIDE | VIDE | ZERO | ZERO | ZERO | FORMULE |
| 145 | 425 | Report à nouveau | VIDE | VALEUR | ZERO | ZERO | ZERO | FORMULE |
| 146 | 426 | Excédent des produits sur les charges | VIDE | VALEUR | VIDE | ZERO | ZERO | FORMULE |
| 147 | 427 | Total du passif | VIDE | FORMULE | FORMULE | FORMULE | FORMULE | FORMULE |
| 152 | 501 | Engagements donnés — intermédiaires financiers | VIDE | FORMULE | FORMULE | FORMULE | FORMULE | FORMULE |
| 153 | 502 | Accords de refinancement | VIDE | ZERO | ZERO | ZERO | ZERO | FORMULE |
| 154 | 503 | Cautions, avals, endos… | VIDE | ZERO | ZERO | ZERO | ZERO | FORMULE |
| 155 | 504 | Confirmations d'ouvertures de crédits documentaires | VIDE | ZERO | ZERO | ZERO | ZERO | FORMULE |
| 156 | 505 | Autres engagements de garantie | VIDE | ZERO | ZERO | ZERO | ZERO | FORMULE |
| 157 | 506 | Engagements reçus d'intermédiaires financiers | VIDE | FORMULE | FORMULE | FORMULE | FORMULE | FORMULE |
| 158 | 507 | Accords de refinancement | VIDE | ZERO | ZERO | ZERO | ZERO | FORMULE |
| 159 | 508 | Cautions, avals… | VIDE | ZERO | ZERO | ZERO | ZERO | FORMULE |
| 160 | 509 | Engagements donnés — clientèle | VIDE | FORMULE | FORMULE | FORMULE | FORMULE | FORMULE |
| 161 | 510 | Acceptation à payer | VIDE | ZERO | ZERO | ZERO | ZERO | FORMULE |
| 162 | 511 | Ouvertures de crédits confirmés | VIDE | FORMULE | FORMULE | FORMULE | FORMULE | FORMULE |
| 163 | 512 | Ouvertures de crédits documentaires | VIDE | ZERO | ZERO | ZERO | VALEUR | FORMULE |
| 164 | 513 | Autres ouvertures de crédits confirmés | VIDE | ZERO | ZERO | ZERO | ZERO | FORMULE |
| 165 | 514 | Caution avals et autres garanties | VIDE | FORMULE | FORMULE | FORMULE | FORMULE | FORMULE |
| 166 | 515 | Garanties de remboursement de crédits | VIDE | ZERO | ZERO | ZERO | ZERO | FORMULE |
| 167 | 516 | Autres cautions, avals et garanties | VIDE | FORMULE_CONSTANTE | ZERO | ZERO | VALEUR | FORMULE |
| 168 | 517 | Obligations cautionnées | VIDE | ZERO | ZERO | ZERO | ZERO | FORMULE |
| 169 | 518 | Divers | VIDE | ZERO | ZERO | ZERO | ZERO | FORMULE |
| 170 | 519 | Engagements reçus de l'Etat | VIDE | ZERO | ZERO | ZERO | ZERO | FORMULE |
| 171 | 520 | Total du hors-bilan | VIDE | FORMULE | FORMULE | FORMULE | FORMULE | FORMULE |

Clé logique proposée (sans inventer d’adresse) : `A:{code}:{axe}` avec axe ∈ `C,D,E,F,G,H` — exemple vérifié `A:102:F` = `ETAT A!F9`.

**Les codes BCM d’ETAT B et ETAT C réutilisent 101, 102, …** Ce n’est pas le même espace que l’ETAT A. Le mapping actuel `BCM:102` désigne l’ETAT A. Toute clé document devra porter la feuille (`A:` / `B:` / `C:`).

---

## 4. Inventaire des formules

663 formules, 48 motifs. Répartition :

| Feuille | Formules |
|---------|----------|
| ETAT A | 306 |
| ETAT B | 136 |
| ETAT C | 92 |
| RATIO COUVERTURE DE RISQUE | 57 |
| RATIO DE LIQUIDITE | 31 |
| CALCUL FPN | 30 |
| RATIO FP ET AI | 10 |
| informations à fournir | 1 (`='ETAT A'!D146`) |

### 4.1 Motifs structurels (à conserver)

- `=SUM(plage)` — totaux horizontaux et quelques verticaux (209, FPN, ratios).
- `=+C9+C10` (et variantes) — totaux de rubrique.
- `='ETAT A'!H32` — concordance inter-feuilles (B, C, FPN, ratios).
- `=IF('ETAT A'!H33+'ETAT A'!C33=I11,TRUE,FALSE)` — contrôles mécanographiques ETAT B/C.
- `=D7-E7`, `=G7*F7`, `=H27/H26` — arithmétique des ratios.
- `=IF(C33<C35,C35-C33,0)` — plafonds FPN.

Openpyxl **n’évalue pas** ces formules. Les caches octobre sont présents dans le fichier source ; un classeur régénéré aura des caches vides ou périmés jusqu’à ouverture Excel.

### 4.2 Formules à constantes d’octobre (à ne jamais recopier comme règle)

Vérifiées dans ETAT A :

| Cellule | Code | Formule lue |
|---------|------|-------------|
| D9 | 102 | `=588160767-F9` |
| D21 | 114 | `=150000000-150000000` |
| D38 | 131 | `=3972024483-C38-2873218-5` |
| D75 | 234 | `=53348003-C75` |
| D76 | 235 | `=77770480-C76` |
| D106 | 322 | `=331024347.65-F106` |
| D112 | 328 | `=737956675-D111` |
| D123 | 403 | `=463722024+296461984-21` |
| D167 | 516 | `=5874268360-G167` |

`2873218` dans D38 est une **constante d’octobre**, pas une activation D02. Le moteur Python ne doit pas l’injecter.

### 4.3 Formules 30 % dans ETAT B (fichier officiel)

Présentes dans le canevas d’octobre, pas inventées :

- `E46` = `('ETAT A'!C38+'ETAT A'!D38)*30%` (COD 207)
- `E48` = `'ETAT A'!D40*30%` (créances immobilisées)
- `E49` = `'ETAT A'!D41*30%` (douteuses)

D09 reste ouverte : T3.5-3 peut **conserver la formule du canevas** dans le fichier généré, mais BEA DIGITAL ne doit pas la présenter comme vérité métier validée. L’UI marque ces cellules « provisoire / D09 ».

---

## 5. Correspondance données ↔ sources

| Concept | Stockage BEA DIGITAL | Affichage SM | Interdit |
|---------|----------------------|--------------|----------|
| Zéro réel observé | Decimal `0` + statut `ZERO_CONFIRME` / `AUTOMATIQUE` | 0,00 | — |
| Zéro décidé | `0` + `ZERO_MANUEL` + motif | 0,00 + badge | — |
| Inconnu / manquant | `NULL` + `NON_RENSEIGNE` | À compléter | Écrire 0 |
| Non mappé | `NULL` + `NON_MAPPEE` | Sans correspondance | Zéro auto |
| En attente D01 | `NULL` + `EN_ATTENTE_DECISION` | Correspondance à valider | Lifecycle `ACTIVE` |
| Bloqué D16/D17/D09 | `NULL` + `EN_ATTENTE_DECISION` | Décision métier | Ventilation fictive |

### A — BAL DET (calculable en principe)

Soldes NCG, DEB/CRE, devise. Permet des **totaux** et une **coupe MRU / devises**.  
Ne permet **pas** résidents / non-résidents (colonnes D vs E, F vs G).  
`caisse_devises` : paramètre déjà classé A (T3.5-2) ; candidat de remplissage `ETAT A!F9` **sous réserve D04** — non affirmé par le seul canevas.

Le moteur actuel (`runner.py`) écrit **une** valeur par `cell_ref` `BCM:nnn`. L’ETAT A officiel exige **jusqu’à cinq axes + provisions**. T3.5-3 ne doit pas coller ce scalaire dans toutes les colonnes.

### B — Sources externes (D09)

ETAT B (EPA/EPC/privé/particuliers) et ETAT C (maturités) : hors DET.  
Octobre : beaucoup de feuilles B/C sont des **renvois à ETAT A** + un partage 30 %. Sans fichier crédits/dépôts, B et C restent provisoires.

### C — Paramètres et annexes

Huit paramètres SM (append-only T3.5-2).  
Feuille `informations à fournir` : 14 lignes de montant ; une seule formule (`C9` ← `ETAT A!D146`, code A424 ext). Les autres `C6:C20` sont des **0 numériques d’octobre**, pas des formules. Pour un nouveau mois : `NON_RENSEIGNE` jusqu’à saisie, jamais recopier ces 0.

### D — Décisions métier

Mapping 242 `A_VALIDER` → 43 `cell_ref` vs 157 codes ETAT A. La majorité des lignes sont totaux, séparateurs ou non mappées (D01/D06).  
D16/D17 : colonnes 2–5. D22 : multi-cellules. D02 : ne pas reprendre `2873218`.

---

## 6. Informations non disponibles pour un WORK fidèle

| Information | Raison | Comportement T3.5-3 |
|-------------|--------|---------------------|
| Ventilation résidence | Absente de la DET (D16/D17) | Cellules D/E/F/G en `EN_ATTENTE_DECISION` sauf preuve contraire |
| Ventilation EPA/EPC/privé/particuliers | D09 | ETAT B feuilles : provisoire |
| Maturités | D09 | ETAT C feuilles : provisoire |
| 114 codes ETAT A sans règle mapping | 43 refs mapping vs 157 codes | `NON_MAPPEE` / total formule |
| Règles `ACTIVE` | 0 en DEV, D01 | Interdit d’activer ; WORK sans `AUTOMATIQUE` officiel |
| ECART | D02 | Ne pas écrire la constante 2 873 218 |
| Justificatif GED binaire | Upload métier non branché | `justificatif_ref` texte + `document_id` nullable |
| Recalcul Excel serveur | openpyxl ; pas de moteur DSI | Totaux **Python** à l’écran ; Excel client pour les formules du fichier |

---

## 7. Décisions métier bloquantes (inchangées)

| ID | Effet sur le canevas WORK |
|----|---------------------------|
| **D01** | Pas d’`ACTIVE`. Feuilles mapping = proposition expert, pas valeur officielle |
| **D02** | `is_active_in_run=False`. Interdit d’écrire ECART dans une cellule |
| **D04/D05** | Paramètres C ; caisse A encore provisoire |
| **D06** | Rubrique sans règle → jamais 0 auto |
| **D09** | ETAT B/C non « réels ». Formules 30 % du fichier = héritage octobre, badge provisoire |
| **D15** | Bases D/C/SD non figées |
| **D16/D17** | Colonnes résidence vides |
| **D22** | Conflits multi-cellules : deux propositions, une décision |

Tant que ces portes sont ouvertes : **aucun** livrable `VALIDATED`. Un `WORK` annoté « non validé » est le seul livrable autorisé.

---

## 8. Architecture technique recommandée

Principe : **le canevas officiel est un template de structure**. Le moteur Decimal reste la vérité des montants métier. Excel n’est pas un second moteur.

```
BEA-SM-10-2026.xlsx (fichier source, SHA figé, jamais muté)
        │  lecture unique → cartographie structurelle
        ▼
 rbcm_template + rbcm_template_cell
        │
BAL DET / paramètres / contrôles T3.5-2 / (mapping lecture seule)
        │
        ▼
 fill WORK  (nouveau service, PAS runner.py)
        │  copie du template → blanc des VALEUR/ZERO/FORMULE_CONSTANTE
        │  conserve FORMULE structurelles
        │  écrit les feuilles autorisées (rare en T3.5-3)
        │  overlay RbcmCellDecision courantes
        ▼
 RbcmDeliverable status=WORK + SHA + watermark
        │
        ▼
 UI document (8 feuilles)  ←  totaux recalculés en Python (SUM / + seulement)
 Excel téléchargé          ←  formules natives ; caches non garantis
```

### 8.1 Lecture du canevas

- Copier `BEA-SM-10-2026.xlsx` vers un emplacement template DEV (ex. `backend/app/data/reporting_bcm_sm/templates/`) **sans modifier l’original**.
- Enregistrer SHA-256 `54e3b687…`.
- `campaign.template_version_id` existe déjà (nullable) : le brancher.

### 8.2 Cartographie structurelle

Table dédiée, **séparée** des 242 règles compte. Une ligne = une cellule vérifiée : feuille, adresse Excel, code BCM, axe, nature (`LEAF` / `TOTAL` / `HEADER` / `SEPARATOR` / `CONTROL` / `OCTOBER_CONSTANT_FORMULA`), texte de formule, `writable`.

Interdit : inventer une adresse absente du fichier.

### 8.3 Remplissage

- Feuilles `LEAF` / `ZERO` / `VALEUR` / `FORMULE_CONSTANTE` : vider (None), ne pas recopier octobre.
- Feuilles `FORMULE` structurelles : **laisser la formule Excel**.
- En-têtes B2/B3 : période et banque de la SM.
- Watermark (ligne ou en-tête) : « Version de travail — non validée ».
- Ne pas appeler `runner.py` en mode ACTIVE. Ne pas activer `A_VALIDER`.

Écart volontaire avec T3.5 conception §10.1 (« WORK = A_VALIDER comme propositions ») : **trop risqué** tant que le scalaire `BCM:nnn` ne sait pas viser un axe Excel. T3.5-3 affiche les propositions mapping **en accès expert** seulement. Le document principal reste vide / en attente, plus des totaux formule.

### 8.4 Recalcul

| Couche | Stratégie |
|--------|-----------|
| UI BEA DIGITAL | Réévaluer uniquement `SUM` et sommes `+` du graphe structurel (Decimal). Pas d’`IF` métier Excel, pas de `*30%` comme vérité |
| Fichier téléchargé | Formules Excel conservées. Caches openpyxl **non** utilisés comme affichage interne |
| Interdit T3.5-3 | LibreOffice, Excel COM, nouveau moteur de formules |

Risque : l’utilisateur ouvre le xlsx et voit des totaux Excel différents des totaux UI si une feuille LEAF a été corrigée sans régénération. Mitigation : toute correction → **nouvelle version WORK**.

### 8.5 PDF

Toujours hors périmètre (`excel_export.pdf_status`).

---

## 9. Modèle de versionnement et de traçabilité

Réutiliser, ne pas dupliquer :

| Besoin | Existant |
|--------|----------|
| Run de calcul | `RbcmCalculationRun` + fingerprints (dont `fingerprint_template`) |
| Valeur moteur | `RbcmCellResult` (`calculated_value` / `retained_value` / `value_status`) UNIQUE(run, cell_ref) |
| Correction | `RbcmCellDecision` append-only, `supersedes_decision_id`, `calculated_value` figé, `decided_value`, `reason`, `created_by_id`, `created_at`, `document_id` |
| Fichier | `RbcmDeliverable` (kind EXCEL, sha256, stored_path) |
| Audit | `record_audit` + `RbcmValidationEvent` |

Étendre sans casser :

- `RbcmDeliverable.status` : aujourd’hui défaut `GENERATED`. Introduire `WORK` / `SUPERSEDED` (et `VALIDATED` plus tard, T3.5-5). Une régénération SUPERSEDE l’ancien WORK, fichier conservé.
- Clé cellule document : `A:102:D` (feuille + code + axe), distincte de `BCM:102` mapping.
- Décision courante = dernière ligne sans enfant `supersedes_decision_id`. **Pas** d’UPDATE de fond.
- Motif obligatoire pour toute correction. Référence justificative : même contrat que les paramètres (`justificatif_ref` ; GED plus tard).

Une modification après génération ⇒ nouveau `RbcmDeliverable` WORK, jamais écrasement du binaire ni du `calculated_value` d’origine.

---

## 10. Impacts backend

### Réutiliser

- Campagnes / versions P2, responsable T3.5-1, contrôles T3.5-2, paramètres append-only, `PERM_*` Login 2 (matrice revue T3.5-2).
- `RbcmCellResult` / `RbcmCellDecision` / `RbcmDeliverable`.
- `ged_documents` en lecture CORE ; pas d’upload métier dans ce lot.
- `upload_root() / reporting-bcm-sm / {campaign_id} / exports`.

### Adapter (après validation T0, pas maintenant)

- Remplacer le corps de `excel_export.generate_excel` : charger le template officiel au lieu d’un `Workbook()` vide. Feuilles actuelles « Controles / Alertes » **ne sont pas** le canevas BCM.
- Nouveau `template_service` (lecture SHA, cartographie) + `work_fill_service` (copie + blanc + écriture limitée).
- Endpoints document : `GET` cellules par feuille (`view`) ; `POST` décision (`correct` ∪ `prepare` ∪ `control`, aligné T3.5-2) ; `POST` générer WORK (`prepare` ∪ `control` ∪ `import`) ; téléchargement (`export`).
- **Pas** d’endpoint d’approbation réglementaire.
- Ne pas modifier `engine/runner.py`.

### Permissions (rappel T3.5-2)

| Action T3.5-3 | Permission |
|---------------|------------|
| Voir le document | `view` |
| Préparer / régénérer WORK | `prepare` ∪ `control` ∪ `import` |
| Corriger une cellule autorisée | `parameters.write` ∪ `prepare` ∪ `control` ∪ `correct` |
| Télécharger WORK | `export` |
| Approuver | **absent de ce lot** |

`view` seul : lecture. Actions interdites refusées backend.

---

## 11. Impacts frontend

Fiche SM déjà en 7 étapes. T3.5-2 s’arrête à l’étape 4. T3.5-3 ouvre **5 et 6** sans l’étape 7 de validation.

| Étape | T3.5-3 |
|-------|--------|
| 5 Préparation | Bouton « Préparer la SM (version de travail) » si DET + contrôles existent. Pas de bouton Valider |
| 6 Vérification | Navigateur **8 onglets = 8 noms de feuilles officiels**. Tableau code / libellé / axes / statut. Couleurs : formule, à compléter, bloqué, corrigé. Édition seulement si `writable` et permission. Enregistrer → nouvelle version WORK. Télécharger |
| Accès expert | Mapping, SHA, traces, formules brutes — drawer existant, pas l’écran principal |
| Export actuel | Libellé « Export technique » à distinguer du canevas WORK |

Pas de Material / Tailwind / police ajoutés (`plateforme/` inchangé ; module rbcm conserve le chrome bea-mg).  
Montants : pipe `montant`. Confirmations : `UiDialogService` / `FeedbackService`.  
`unsavedChangesGuard` sur l’édition cellule.

---

## 12. Migrations éventuellement nécessaires

Additives uniquement, **après** `rbcm_04`. Aucune destruction. Pas d’Alembic sur les tables 01–04.

| Objet | Motif |
|-------|--------|
| `rbcm_template` | id, filename, sha256, stored_path, label, is_current, created_at |
| `rbcm_template_cell` | template_id, sheet_name, excel_address, bcm_code, axis, nature, formula, writable UNIQUE(template, sheet, address) |
| Check `rbcm_deliverable.status` | Ajouter `WORK`, `SUPERSEDED` (et réserver `VALIDATED` sans l’utiliser) |
| Option | `justificatif_ref` sur `rbcm_cell_decision` (symétrie paramètres) |

`campaign.template_version_id` : déjà en `rbcm_01`, pas de colonne nouvelle si on pose la FK vers `rbcm_template`.

Pas de table parallèle d’anomalies. Pas de 2ᵉ moteur.

---

## 13. Tests d’acceptation (à écrire à l’implémentation)

Jeux : banque jetable, **jamais** SM BEA 11/2026 / 01/2026.

1. SHA du template lu = `54e3b687…` ; fichier source non muté.
2. WORK a les **8 noms de feuilles** officiels (pas « Informations/FPN/Ratios » de l’export technique).
3. B2 = date d’arrêté de la SM cible ; B3 = banque de la campagne.
4. Aucune constante d’octobre (`588160767`, `2873218`, `5874268360`, …) dans les cellules LEAF du WORK.
5. Formules `SUM` / `+C9+C10` encore présentes après génération.
6. Cellule `NON_RENSEIGNE` affichée « À compléter », jamais `0,00`.
7. `0,00` n’apparaît que si statut zéro réel / zéro décidé.
8. `view` : GET document OK ; POST décision / générer WORK → 403.
9. Contrôleur (perms T3.5-2) peut préparer et corriger.
10. Correction : motif obligatoire ; `calculated_value` conservé ; `supersedes_decision_id` chaîné.
11. Seconde génération : ancien livrable `SUPERSEDED`, SHA distinct, fichier toujours téléchargeable.
12. 0 règle `ACTIVE` après génération ; 242 `A_VALIDER` inchangé.
13. `engine/runner.py` hash / contenu inchangé.
14. ETAT B cellules `*30%` : badge provisoire D09, pas « automatique ».
15. I147 (contrôle actif/passif) reste une formule, non écrasée par Python.
16. Téléchargement WORK sans statut APPROUVEE.
17. Aucun bouton / endpoint d’approbation ajouté.
18. Concurrence : deux préparations WORK — append livrables, pas d’écrasement binaire.

---

## 14. Risques et limites

| Risque | Gravité | Mitigation |
|--------|---------|------------|
| Prendre le xlsx d’octobre pour un modèle vide | Élevé | Blanc obligatoire des LEAF ; tests d’absence de constantes |
| openpyxl caches ≠ UI | Élevé | UI = Python ; fichier = formules ; watermark |
| Coller `BCM:102` dans D–G | Élevé | Clé `A:102:D` ; pas de fill mapping en T3.5-3 |
| Recopier les 0 d’octobre (FPN, hors-bilan) | Élevé | `NULL` + `NON_RENSEIGNE` |
| Faire passer WORK pour officiel | Élevé | Watermark ; pas de `VALIDATED` ; pas d’étape 7 |
| 30 % ETAT B pris pour D09 clos | Moyen | Badge provisoire |
| `cell_ref` String(32) trop court pour `RATIO COUVERTURE DE RISQUE!H28` | Moyen | Clé logique courte `A:102:D` + adresse Excel dans `template_cell` |
| GED non branchée | Faible | Référence texte |
| Export technique encore cliquable | Faible | Libellé distinct |

Limite assumée : T3.5-3 produit un **brouillon structurel annoté**, pas une SM BCM complète.

---

## 15. Plan d’implémentation (sous-lots, après validation de ce T0)

Ne pas démarrer tant que ce rapport n’est pas validé. Découpage interne à T3.5-3 (l’ancien T3.5-4 « écran document » de la conception T3.5 est **absorbé ici**, conformément à l’objectif utilisateur). T3.5-4 externe (réimport, raffinements) reste fermé.

| Sous-lot | Contenu | Hors |
|----------|---------|------|
| **T3.5-3-A** | Copie template + SHA + tables `rbcm_template` / `_cell` + seed de la cartographie **vérifiée** | Fill, UI |
| **T3.5-3-B** | `work_fill_service` : copie, blanc, en-têtes, formules conservées, livrable WORK + watermark | Mapping ACTIVE, runner |
| **T3.5-3-C** | API GET document par feuille + POST générer + download ; permissions T3.5-2 | Approve |
| **T3.5-3-D** | UI 8 onglets dans la fiche (étapes 5–6), statuts, pas de jargon SHA | Validation étape 7 |
| **T3.5-3-E** | POST `RbcmCellDecision` + régénération WORK + historique visible | GED binaire, T3.5-4 |

Ordre : A → B → C → D → E.  
Critère de fin T3.5-3 : un utilisateur habilité prépare, parcourt les huit feuilles, voit les manques, corrige une feuille autorisée avec motif, télécharge un xlsx WORK watermarké, sans qu’aucune règle `A_VALIDER` ne passe `ACTIVE` et sans toucher aux SM 11/2026 et 01/2026.

---

## Décisions à trancher avant implémentation

1. Confirmer le **rejet** du mode « remplir WORK avec les 242 `A_VALIDER` comme si c’était officiel » (recommandation de ce T0 : oui, on rejette).
2. FPN / `informations à fournir` : saisie dans le document (E) ou file C T3.5-2 d’abord ?
3. Les formules 30 % d’ETAT B restent-elles dans le xlsx généré (recommandé : oui, badge D09) ?
4. Emplacement définitif du binaire template (dépôt `backend/app/data/...` vs volume uploads).

---

## État Git / données

- HEAD `091b57c`, branche dirty inchangée par ce T0.
- **Pas de commit, pas de code métier.**
- Canevas officiel lu, non modifié.
- Production v1.0.0 hors périmètre.

**Attendre la validation explicite de ce T0 avant tout code T3.5-3.**
