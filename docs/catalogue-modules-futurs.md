# Catalogue des futurs modules BEA DIGITAL

Phase C — **Étape 8** : identifier les processus des départements, **avant**
de coder (Étape 9). ORION reste la source de vérité bancaire ; BEA DIGITAL
complète (Excel → contrôles → workflows → GED → reporting).

> Hypothèse de travail pour ateliers métier. À valider avec chaque département
> El Amana — ne pas traiter comme un cahier des charges figé.

## Comment lire une fiche

Pour chaque processus candidat :

| Rubrique | Contenu |
|----------|---------|
| Processus | Nom métier |
| Aujourd’hui | Tâches manuelles / Excel / e-mail |
| ORION | Ce qui reste dans le core banking |
| BEA DIGITAL | Ce que le module apporterait |
| Contrôles / validations | Qui valide, quels seuils |
| Documents | GED / pièces |
| Rapports | Exports, alertes |
| Risques / opportunités | Doublons, délais, erreurs |
| Module proposé | Code catalogue (`plateforme_modules`) |
| Priorité | P1 / P2 / P3 |

## État actuel (déjà dans le seed)

| Espace | Modules seed | Statut |
|--------|--------------|--------|
| `comptabilite` | `immobilisations` | **actif** |
| `comptabilite` | `rapprochements`, `controles`, `cloture`, `reporting-compta` | bientôt |
| `credit` | `credit` | bientôt |
| `rh` | `rh` | bientôt |
| `informatique` | `tickets-si` | bientôt |
| `achats` | `demandes-achat` | bientôt |
| `moyens-generaux` | `stock-fournitures`, `achats-appro`, `notes-frais`, `contrats-echeances`, `archives-mg` | **actif** |

CDC et conception : [moyens-generaux/](moyens-generaux/README.md).

Conventions techniques déjà figées (Phase B) :

- Routes : `/{module}/...` (sauf immo = URLs racine)
- Rôles : `{module}.{profil}` (sauf immo = codes courts legacy)
- Permissions : `{module}.*` + `require_module_access`
- Backup : `make_module_scope` dans `module_backup_scopes.py`
- Notif : `event_type` libre + taxonomie

---

## 1. Comptabilité (espace actif)

Référence livrée : Immobilisations & Amortissements.

### 1.1 Immobilisations & Amortissements — **livré**

| Rubrique | Contenu |
|----------|---------|
| Processus | Parc, dotations, cessions, rebuts, inventaire, écritures |
| ORION | Soldes / comptes ; BEA = travail interne + contrôles |
| Module | `immobilisations` (`legacy-root`) |

### 1.2 Rapprochements Excel / ORION — P1

| Rubrique | Contenu |
|----------|---------|
| Aujourd’hui | Fichiers Excel, copier-coller, contrôles manuels |
| BEA DIGITAL | Import, écarts, workflow de résolution, trace audit |
| Module | `rapprochements` (déjà seed `bientot`) |

### 1.3 Contrôles comptables périodiques — P2

| Rubrique | Contenu |
|----------|---------|
| Aujourd’hui | Check-lists, mails, tableaux ad hoc |
| BEA DIGITAL | Plans de contrôle, anomalies, assignation |
| Module | `controles` |

### 1.4 Clôture comptable — P2

| Rubrique | Contenu |
|----------|---------|
| Aujourd’hui | Suivi Excel de jalons de clôture |
| BEA DIGITAL | Checklist, statut, pièces GED, alertes |
| Module | `cloture` |

### 1.5 Reporting transverse compta — P3

| Rubrique | Contenu |
|----------|---------|
| Aujourd’hui | Exports ponctuels hors immo |
| BEA DIGITAL | Tableaux de bord multi-modules compta |
| Module | `reporting-compta` |

---

## 2. Crédit

### 2.1 Instruction & suivi de dossiers (hors saisie ORION) — P1

| Rubrique | Contenu |
|----------|---------|
| Processus | Constitution dossier, circuit validation interne, checklist |
| Aujourd’hui | Excel, e-mails, dossiers papier / partages fichiers |
| ORION | Décision / encours / échéancier (source de vérité) |
| BEA DIGITAL | Workflow interne, contrôles documentaires, alertes délais |
| Documents | Pièces identité, garanties, avenants → GED |
| Rapports | Dossiers en retard, files par agence / comité |
| Module | `credit` — entrée `/credit`, logout → `/credit` |
| Rôles cibles | `credit.lecteur`, `credit.analyste`, `credit.valideur`, `credit.admin` |

### 2.2 Suivi garanties & covenants — P2

| Rubrique | Contenu |
|----------|---------|
| Aujourd’hui | Tableaux Excel échéances garanties |
| BEA DIGITAL | Alertes échéance, lien dossier, GED |
| Module futur | `garanties` (espace `credit`) — **pas encore seed** |

### 2.3 Comité / décisions internes — P3

| Rubrique | Contenu |
|----------|---------|
| Aujourd’hui | PV Word / mail |
| BEA DIGITAL | Ordre du jour, décisions, pièces, audit |
| Module futur | `comite-credit` — **pas encore seed** |

---

## 3. RH

### 3.1 Demandes RH & absences (processus internes) — P1

| Rubrique | Contenu |
|----------|---------|
| Processus | Congés, absences, demandes administratives |
| Aujourd’hui | Excel / papier / mails managers |
| ORION | Paie / core RH banque si existant — BEA ne remplace pas |
| BEA DIGITAL | Formulaires, validations N+1, historique, notifications |
| Module | `rh` — entrée `/rh` |
| Rôles cibles | `rh.lecteur`, `rh.gestionnaire`, `rh.admin` |

### 3.2 Onboarding / offboarding docs — P2

| Rubrique | Contenu |
|----------|---------|
| Aujourd’hui | Check-lists dispersées |
| BEA DIGITAL | Parcours + GED + tickets SI liés |
| Module futur | `rh-parcours` — **pas encore seed** |

---

## 4. Informatique (DSI)

### 4.1 Tickets & demandes internes — P1

| Rubrique | Contenu |
|----------|---------|
| Processus | Incidents, demandes d’accès, changements |
| Aujourd’hui | Mails, chat, Excel |
| BEA DIGITAL | File tickets, SLA, catégories, lien utilisateur / module |
| Module | `tickets-si` — entrée `/tickets-si`, espace `/informatique` |
| Rôles cibles | `tickets-si.lecteur`, `tickets-si.agent`, `tickets-si.admin` |

### 4.2 Inventaire postes / licences (hors immo) — P3

| Rubrique | Contenu |
|----------|---------|
| Attention | ≠ inventaire immobilisations |
| Module futur | `parc-si` — **pas encore seed** |

---

## 5. Achats

### 5.1 Demandes d’achat & validations — P1

| Rubrique | Contenu |
|----------|---------|
| Processus | DA → validation → bon de commande interne |
| Aujourd’hui | Excel, mails, signatures papier |
| ORION / compta | Engagements / factures selon périmètre banque |
| BEA DIGITAL | Workflow, seuils, pièces, lien centres de coût (org) |
| Module | `demandes-achat` — entrée `/demandes-achat`, espace `/achats` |
| Rôles cibles | `demandes-achat.demandeur`, `demandes-achat.valideur`, `demandes-achat.admin` |

### 5.2 Suivi fournisseurs (métier achats) — P2

| Rubrique | Contenu |
|----------|---------|
| Attention | Table org `fournisseurs` déjà partagée (immo) — ne pas dupliquer sans besoin |
| Module futur | extension ou `suivi-fournisseurs` — **atelier requis** |

---

## 6. Autres départements

### 6.1 Moyens Généraux — seedé (5 modules actifs)

Voir [moyens-generaux/cdc-fonctionnel-v1.md](moyens-generaux/cdc-fonctionnel-v1.md).

| Module | Statut |
|--------|--------|
| `stock-fournitures`, `achats-appro`, `notes-frais`, `contrats-echeances`, `archives-mg` | actif |

### 6.2 Candidats non seedés

Compliance / LBC, Audit interne, Marketing, Agence / réseau, Juridique, Risques.
Créer l’espace CORE ADMIN **seulement** après atelier.

---

## Ordre de construction recommandé (Étape 9+)

```text
1. Stock & Fournitures (MG) — Phase 1
2. Atelier Crédit (P1) → CDC → /credit/...
3. Achats MG / Notes de frais / Contrats
4. Tickets SI ou Demandes d’achat
5. RH demandes
```

Pour **chaque** nouveau module (checklist technique) :

1. Entrée `PLATEFORME_MODULES` + permissions `{module}.*`
2. Rôles `{module}.{profil}` (jamais `administrateur` nu)
3. Contrat routes `module-routing.contract.ts` + shell Angular préfixé
4. `require_module_access("{code}")` + `require_permission`
5. `make_module_scope` + `ESPACE_MODULES`
6. Taxonomie notif / `event_type`
7. Tests isolation (modèle `test_module_isolation.py`)
8. Docs + seed CORE ADMIN

## Hors périmètre de cette étape

- Développement métier (Étape 9)
- Serveur / backup / formation banque (Phase D)
- Remplacement d’ORION

Voir aussi : [core-bea-digital.md](core-bea-digital.md), [frontend-plateforme.md](frontend-plateforme.md),
[socle-bea-digital.md](socle-bea-digital.md), `AGENTS.md`.
