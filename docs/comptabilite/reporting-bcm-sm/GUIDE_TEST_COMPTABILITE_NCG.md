# Guide de test Comptabilité — Structure NCG & orientations SM

Document destiné à la **Comptabilité** pour valider le parcours de détection et d’orientation des NCG vers les cellules de la Situation Mensuelle (SM).

**Environnement :** DEV Docker local (`http://localhost`).  
**Principe :** aucune orientation n’est active tant qu’elle n’a pas été **confirmée** par un utilisateur habilité distinct du proposant.  
**Cas réel octobre :** le NCG **847000** (Moins-values cession) est détecté comme *nouveau* ; **aucune cellule ne lui est attribuée** tant que la Comptabilité n’a pas décidé.

---

## 1. Accès

1. Se connecter à BEA DIGITAL (Login 1 plateforme, puis module Reporting BCM SM).
2. Sélectionner la SM concernée (ex. **10/2026**) via le sélecteur de période.
3. Deux écrans complémentaires :
   - **Imports BAL DET** → `/reporting-bcm-sm/imports`  
     Panneau **Structure NCG de la BAL DET** (détection).
   - **Revue NCG** → `/reporting-bcm-sm/ncg-revue`  
     Décisions métier (proposer / confirmer / rejeter / différer).

Navigation croisée : bouton **Revue Comptabilité** depuis Structure, bouton **Structure NCG** depuis Revue.

---

## 2. Examiner la Structure NCG

1. Sur **Imports**, s’assurer qu’une BAL DET est **confirmée** (VALIDATED).
2. Ouvrir le panneau Structure : compteurs *Nouveaux*, *Non orientés*, *Mappés*, *Réapparus*, *Soldes nuls*, *Absents mappés*.
3. Filtrer (ex. « Nouveaux ») et rechercher un NCG (ex. `847000`).
4. Cliquer une ligne pour ouvrir la fiche : soldes par période, mapping catalogue, orientations existantes.

---

## 3. Examiner un NCG dans la Revue

1. Aller dans **Revue NCG** (même SM sélectionnée).
2. Les KPI sont cliquables (Nouveaux, Non orientés, Différés, En attente, Actives, Rejetées, Désactivées).
3. Ouvrir un NCG : présence BAL DET, devises/comptes, mapping, proposition éventuelle, notes et historique.

---

## 4. Proposer une orientation

Permission requise : `reporting-bcm-sm.mapping.propose` (ou admin module).

1. Choisir **État** (ETAT A / ETAT B), **Cellule SM**, **Devise**, **Catégorie** (résidents / non-résidents), **Opération** :
   - Ajouter DEB / Ajouter CRE / Soustraire DEB / Soustraire CRE.
2. Renseigner une note métier si utile.
3. **Proposer (À orienter)** → statut `À orienter` (**pas d’activation**).
4. **Soumettre** → `En attente de validation` (toujours non active).

Pour corriger cellule ou opération avant confirmation : **Corriger** (l’historique ancien → nouveau est conservé ; une proposition en attente repasse en « À orienter »).

---

## 5. Valider, rejeter ou différer

| Action | Qui | Effet |
|--------|-----|--------|
| **Confirmer** | `mapping.validate` (≠ proposant) | `Validé et actif` → fusionné au catalogue central pour les **prochains** calculs uniquement |
| **Rejeter** | `mapping.validate` | Motif **obligatoire** ; historique conservé ; jamais appliqué au calcul |
| **Laisser sans orientation** | `mapping.propose` | Différé : sans cellule ni opération ; reste visible ; **jamais** actif automatiquement |
| **Désactiver** | `mapping.validate` | Retire du catalogue actif sans effacer l’historique |

---

## 6. Consulter l’historique

Sur la fiche NCG / orientation :

- Statut courant et badges.
- Notes (corrections horodatées ancienne → nouvelle cellule/opération).
- Motif de rejet / désactivation.
- Auteurs et dates (préparation, soumission, validation, rejet, désactivation) via audit plateforme.

Les orientations **actives**, **rejetées** et **désactivées** sont consultables via les onglets / KPI de la Revue.

---

## 7. Points à vérifier avant de confirmer une orientation

- [ ] Le NCG et son libellé correspondent bien à la BAL DET.
- [ ] Les soldes DEB / CRE et les devises sont ceux attendus.
- [ ] La **cellule SM** (ex. `A:402:D`) et l’**état** (A ou B) sont les bons.
- [ ] La **catégorie** (résidents / non-résidents) et la **devise** (MRU-MRO / devises / toutes) sont correctes.
- [ ] L’**opération** (ADD/SUB DEB/CRE) produit le sens comptable voulu.
- [ ] Aucun mapping catalogue conflictuel n’existe déjà pour le même NCG / cellule / opération.
- [ ] Le validateur n’est **pas** le même utilisateur que le proposant.
- [ ] On ne confirme **pas** pour « équilibrer » un écart de bilan : pas d’injection d’écart global dans une cellule.
- [ ] Pour **847000** : ne confirmer une cellule **que** après décision métier explicite de la Comptabilité.

---

## 8. Ce que ce test ne doit pas faire

- Ne pas modifier les **89** règles du catalogue central sans décision validée.
- Ne pas recalculer les campagnes SM déjà calculées uniquement pour tester une orientation.
- Ne pas attribuer arbitrairement une cellule au NCG 847000.
- Ne pas déployer ni pousser en production depuis ce guide.

---

## Références

- Synthèse technique : [NCG_STRUCTURE_ET_ORIENTATIONS.md](NCG_STRUCTURE_ET_ORIENTATIONS.md)
- Guide utilisateur : [GUIDE_UTILISATEUR.md](GUIDE_UTILISATEUR.md)
- Catalogue central : `backend/app/services/reporting_bcm_sm/engine/rules_catalog.py` (`ALL_RULES`, 89 règles).
- Fusion orientations actives : `merge_active_orientations` (uniquement `VALIDE_ACTIF`).
- API revue : `GET /api/v1/reporting-bcm-sm/campaigns/{id}/ncg-review`.
