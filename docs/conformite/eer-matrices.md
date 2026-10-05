# EER — Matrices métier (étape 2, à valider)

Complète [eer-architecture-metier.md](eer-architecture-metier.md) (points 7 à 10 du livrable).
Repères de source : [CDC §n] cahier des charges général, [FICHES] fiches transcrites
dans la demande Étape 2, [XLS] Excel de suivi, [PROP] proposition, [À CONFIRMER] absent des sources.

Toutes les listes ci-dessous deviennent des lignes de `eer_referentiels` /
`eer_checklist_regles` : modifiables par paramétrage, pas par code.

## 0. Apports des fiches officielles

Analyse des 7 PDF interactifs BEA (04/10/2026). Leurs champs de formulaire portent des noms
génériques (« Champ de texte n », « Case n ») : les libellés et options viennent du texte imprimé.

| Point | Constat [FICHES] | Effet sur le modèle |
|-------|------------------|---------------------|
| Motif de la fiche | « Entrée en relation » **ou** « Mise à jour du dossier client » | `motif_fiche` ; périmètre MAJ [À CONFIRMER] |
| Identifiant | PP, PM publique, Mandataire : « Numéro IDP » ; PM privée, Association : « Numéro IDM » | `numero_idp` / `numero_idm` |
| Situation matrimoniale (PP) | Célibataire, Marié(e), Divorcé(e), Veuf(ve) | référentiel initial |
| Champs libres | type de contrat, origine des fonds, destination des fonds, motif PPE, lien client/mandataire, comptes avec mandat | texte libre (aucune liste inventée) |
| Téléphones | 3 par PP et par mandataire | `telephone_1..3` |
| Contact d’urgence (PP) | Nom, Téléphone, Lien avec le client | rôle `CONTACT_URGENCE` |
| Tranches | PP : 4 tranches PP ; **PM privée, PM publique, Association : tranches PM** ; libellé « tranche du **revenu mensuel estimé** » | colonne Excel « Estimation revenus par mois » = tranche |
| PPE / FATCA | présents : PP, PM privée, Association, Mandataire ; **absents : PM publique** ; FATCA = une question « le client ou le mandataire » | règles §2 |
| Risque | PP, PM, Mandataire : Faible / Moyen / Élevé ; **Association : Élevé imposé** | risque forcé |
| Avis KYC | PP : Moyen/Élevé ; PM privée + publique : toute ouverture ; Association : obligatoire ; FATCA OUI ; mandataire : avis sur sa fiche | §5.2 |
| BE / actionnariat | PM privée **et** PM publique (≥ 10 %) ; Association : non | §2 |
| Dirigeants | PM privée et publique : gérant + co-gérant ; Association : signataire + co-signataire + membres de direction (Nom, Nationalité, Fonction ou Qualité) | rôles |
| RSE | PM privée seulement : Impact RSE Oui/Non + domaines | `eer_parties_morales` |
| Fiche actionnaire | niveaux 1-3 : Nom, Nationalité, % ; niveau 4 : Nom, Nationalité, Lien avec le client | graphe, % nullable |
| Tableau des signataires | cadre banque : Date, Nom, Fonction, Avis, Signature | **visas internes** (`eer_visas`) |
| Spécimen de signature | code agence, IDP / IDM, racine, photo, nom client, **n° de compte, date d’ouverture**, nombre de signataires, type de signature unique / conjointes / séparées, nom et téléphone du signataire | champs compte + rôle `SIGNATAIRE_COMPTE` |
| Référence externe | « Procédure classifications risques clients » | à fournir pour un calcul de risque |

Toujours **absente** des fiches : la liste des **pièces justificatives** à joindre par profil.

## 1. Type client → Profil → Formulaire

### 1.1 Types et profils [FICHES]

| Type client (code) | Libellé Excel [XLS] | Profils |
|--------------------|---------------------|---------|
| `PP` | Personne_Physique | Salarié, Retraité, Étudiant, Sans emploi, Professionnel, Entrepreneur, Rentier, Personnel BEA |
| `PM_PRIVEE` | Personne_Morale_Privée | SA, SARL, SUARL, Succursale, Groupement, Établissement, Projet privé, Professions libérales, Institutions financières, SNC, SCS, SP, SAS, SCA |
| `PM_PUBLIQUE` | Personne_Morale_Publique | EPIC, EPA, Collectivité, Administration centrale, Institution nationale, Institution internationale, Institution financière publique, Ambassade, Projet public |
| `ASSOCIATION` | Personne_Morale_Association | Association, ONG, Fondation, Coopérative, Parti politique, Projet |

Sous-profil : niveau prévu, **vide** au départ [À CONFIRMER].

### 1.2 Sections de formulaire par type

Un seul écran « dossier EER » ; les sections s’affichent selon le type (✓ = affichée,
◐ = conditionnelle, — = absente).

| Section [FICHES] | PP | PM privée | PM publique | Association |
|------------------|----|-----------|-------------|-------------|
| Motif (entrée en relation / mise à jour), date, code agence, racine client | ✓ | ✓ | ✓ | ✓ |
| Numéro IDP / IDM | IDP | IDM | IDP | IDM |
| Profil client | ✓ | ✓ | ✓ | ✓ |
| Identité PP (sexe, prénom, prénom du père, nom, naissance, adresse et pays de résidence) | ✓ | — | — | — |
| Pièce d’identité (NNI, carte séjour, carte diplomatique, passeport ; n°, délivrance, expiration), nationalité | ✓ | — | — | — |
| Situation matrimoniale | ✓ | — | — | — |
| Profession, employeur, salaire net, date embauche, type de contrat | ✓ | — | — | — |
| Téléphones (1-3), email | ✓ | email | email | email |
| Contact en cas d’urgence (Nom, Téléphone, Lien) | ✓ | — | — | — |
| Raison sociale / nom de l’entité / de l’association, date de création | — | ✓ | ✓ | ✓ |
| Gérant, co-gérant | — | ✓ | ✓ | — |
| Signataire, co-signataire | — | — | — | ✓ |
| Activités principales, adresse du siège, effectif | — | ✓ | ✓ | ✓ |
| RC chronologique, RC analytique, pays de résidence fiscale | — | ✓ | ✓ | — |
| NIF | — | ✓ | ✓ | ✓ |
| N° d’agrément | — | — | — | ✓ |
| Site web | — | ✓ | ✓ | ✓ |
| Impact RSE + domaines | — | ✓ | — | — |
| Membres de la direction (Nom, Nationalité, Fonction ou Qualité) | — | — | — | ✓ |
| Bénéficiaires effectifs (≥ 10 %) + actionnariat (Nom ou raison sociale, Nationalité, % actions) | — | ✓ | ✓ | — |
| Fiche actionnaire (niveaux 1 à 4, en annexe) | — | ◐ | ◐ | — |
| Mandataires (Nom, Nationalité, Fonction) + fiche Mandataire | ◐ | ◐ | ◐ | ◐ |
| Mouvements mensuels (tranche) | PP | PM | PM | PM |
| Origine / destination des fonds | ✓ | ✓ | ✓ | ✓ |
| Signature client | ✓ | ✓ | ✓ | ✓ |
| *Cadre banque* — PPE (+ motif) | ✓ | ✓ | — | ✓ |
| *Cadre banque* — FATCA (client ou mandataire) | ✓ | ✓ | — | ✓ |
| *Cadre banque* — Segmentation LBC-FT | F/M/E | F/M/E | F/M/E | Élevé imposé |
| *Cadre banque* — Commentaire sur le profil du client | ✓ | ✓ | ✓ | ✓ |
| *Cadre banque* — Tableau des signataires (visas : Date, Nom, Fonction, Avis, Signature) | ✓ | ✓ | ✓ | ✓ |
| Spécimen de signature (compte, date d’ouverture, type de signature, signataires) | ✓ | ✓ | ✓ | ✓ |

### 1.3 Tranches de mouvements mensuels [FICHES][CDC §22]

| Type | Tranches |
|------|----------|
| PP | < 50 000 MRU · 50 000–100 000 · 100 000–200 000 · > 200 000 |
| PM privée | < 100 000 MRU · 100 000–1 000 000 · 1 000 000–5 000 000 · > 5 000 000 |
| PM publique, Association | mêmes tranches que PM privée [FICHES] |

## 2. Type client → Checklist

### 2.1 Socle (toujours généré pour le type)

| Code règle | Libellé | Axe | PP | PM priv. | PM pub. | Asso |
|------------|---------|-----|----|----------|---------|------|
| `FICHE_CLIENT` | Fiche client renseignée et signée | PHYSIQUE | ✓ | ✓ | ✓ | ✓ |
| `PIECE_IDENTITE` | Pièce d’identité du client PP (pour une PM / association : pièces des gérants, signataires [À CONFIRMER]) | PHYSIQUE | ✓ | ◐ | ◐ | ◐ |
| `PIECE_VALIDITE` | Validité de la pièce (expiration) | PHYSIQUE | ✓ | ◐ | ◐ | ◐ |
| `SPECIMEN_SIGNATURE` | Spécimen de signature (compte, type de signature, signataires, photo) | PHYSIQUE | ✓ | ✓ | ✓ | ✓ |
| `VISAS_BANQUE` | Tableau des signataires (visas internes) renseigné | PHYSIQUE | ✓ | ✓ | ✓ | ✓ |
| `JUSTIFICATIF_REQUIS` | Justificatif requis selon profil (liste [À CONFIRMER]) | PHYSIQUE | ✓ | — | — | — |
| `DOCUMENTS_ENTITE` | Documents de l’entité (liste [À CONFIRMER]) | PHYSIQUE | — | ✓ | ✓ | ✓ |
| `INFOS_CLIENT` | Informations client complètes | SYSTEME | ✓ | ✓ | ✓ | ✓ |
| `COHERENCE_IDENTITE` | Cohérence fiche ↔ pièce ↔ système | COHERENCE | ✓ | ✓ | ✓ | ✓ |
| `MOUVEMENTS` | Estimation des mouvements renseignée | SYSTEME | ✓ | ✓ | ✓ | ✓ |
| `ORIGINE_FONDS` / `DESTINATION_FONDS` | Origine / destination des fonds | SYSTEME | ✓ | ✓ | ✓ | ✓ |
| `PPE_STATUT` | Statut PPE renseigné | SYSTEME | ✓ | ✓ | — | ✓ |
| `FATCA_STATUT` | Indice d’américanité renseigné (client ou mandataire) | SYSTEME | ✓ | ✓ | — | ✓ |
| `LBCFT_RISQUE` | Risque LBC-FT évalué et justifié (Association : Élevé imposé) | SYSTEME | ✓ | ✓ | ✓ | ✓ |
| `CONTACT_URGENCE` | Contact en cas d’urgence | PHYSIQUE | ✓ | — | — | — |
| `ACTIONNARIAT` | Structure d’actionnariat complète | PHYSIQUE | — | ✓ | ✓ | — |
| `BE_IDENTIFIES` | BE identifiés (≥ seuil paramétré, 10 %) | PHYSIQUE | — | ✓ | ✓ | — |
| `DIRECTION` | Gérant (PM) / signataire + membres de direction (Association) | PHYSIQUE | — | ✓ | ✓ | ✓ |
| `AVIS_KYC` | Avis du service Conformité KYC | PHYSIQUE | ◐ | ✓ | ✓ | ✓ |

### 2.2 Enrichissements conditionnels

| Condition | Éléments ajoutés |
|-----------|------------------|
| `ppe = OUI` (toute partie) | `PPE_MOTIF` (bloquant), `PPE_CONTROLE_RENFORCE`, `AVIS_KYC` |
| `fatca_indice = OUI` | `FATCA_REVUE_KYC`, `AVIS_KYC` |
| `a_mandataire` (par mandataire) | `MANDATAIRE_FICHE`, `MANDATAIRE_PIECE`, `MANDATAIRE_VALIDITE`, `MANDAT_DOCUMENT`, `MANDATAIRE_PPE`, `MANDATAIRE_FATCA`, `MANDATAIRE_RISQUE`, `MANDATAIRE_AVIS` |
| `risque ∈ {MOYEN, ELEVE}` (PP) | `LBCFT_VALIDATION_PREALABLE`, `AVIS_KYC` |
| `type_client = ASSOCIATION` | risque forcé ELEVE, `AVIS_KYC` |
| `impact_rse = OUI` (PM privée) | `RSE_DOMAINES` (domaines précisés) |
| `type_client ∈ {PM_PRIVEE, PM_PUBLIQUE}` | `AVIS_KYC` |
| organisation détentrice sans détenteurs | `ACTIONNARIAT_NIVEAU_SUIVANT` (pour chaque organisation) |
| par BE (calculé ou déclaré) | `BE_PIECE`, `BE_JUSTIFICATIF_DETENTION` |
| `residence` / `nationalite` | [À CONFIRMER] : aucune règle documentée, pas d’élément ajouté |

### 2.3 Exemples attendus

| Cas | Checklist |
|-----|-----------|
| PP Salarié, PPE NON, FATCA NON, pas de mandataire, risque FAIBLE | socle PP (sans `AVIS_KYC`) |
| idem + PPE OUI | socle + `PPE_MOTIF`, `PPE_CONTROLE_RENFORCE`, `AVIS_KYC` |
| idem + 1 mandataire | socle + 8 éléments mandataire |
| PM privée SARL, A → 60 % → B → 70 % → X | socle PM + actionnariat 2 niveaux + X BE (42 %) + `BE_PIECE`(X) + `AVIS_KYC` |

## 3. Type client → Documents

Seuls les documents **cités** dans les sources sont listés ; le reste est à fournir.

| Document (type GED) | PP | PM priv. | PM pub. | Asso | Source |
|---------------------|----|----------|---------|------|--------|
| Fiche client (PP / PM privée / PM publique / associations), signée | ✓ | ✓ | ✓ | ✓ | [FICHES] |
| Pièce d’identité | client | gérant(s) [À CONFIRMER] | gérant(s) [À CONFIRMER] | signataire(s) [À CONFIRMER] | [CDC §12] |
| Spécimen de signature (+ photo) | ✓ | ✓ | ✓ | ✓ | [FICHES] |
| Justificatif requis | ✓ | — | — | — | [CDC §13] — nature par profil [À CONFIRMER] |
| Mandat / procuration + fiche mandataire | ◐ | ◐ | ◐ | ◐ | [CDC §34][FICHES] |
| Documents société | — | ✓ | — | — | [CDC §34] — liste [À CONFIRMER] |
| Actes de l’entité publique | — | — | ✓ | — | [À CONFIRMER] |
| Documents association (agrément…) | — | — | — | ✓ | n° agrément [FICHES], pièces [À CONFIRMER] |
| Fiche actionnaire personne morale (niveaux 1-4) | — | ◐ | ◐ | — | [FICHES] — si plusieurs actionnaires / niveaux |
| Justificatifs BE | — | ✓ | ✓ | — | [CDC §21] — nature [À CONFIRMER] |
| Justificatif origine des fonds | ◐ | ◐ | ◐ | ◐ | [CDC §23] — quand exigé [À CONFIRMER] |
| Avis conformité | ◐ | ✓ | ✓ | ✓ | [CDC §34] |
| Autres documents | ◐ | ◐ | ◐ | ◐ | [CDC §34] |

## 4. Type client → Contrôles

| Contrôle | Type | Résultats | PP | PM priv. | PM pub. | Asso |
|----------|------|-----------|----|----------|---------|------|
| Présence de chaque document obligatoire | AUTO_PRESENCE | PRESENT / ABSENT | ✓ | ✓ | ✓ | ✓ |
| Expiration pièce (date contrôle) | AUTO_EXPIRATION | VALIDE / EXPIREE / EXPIRATION_PROCHE (délai paramétré [À CONFIRMER]) / A_VERIFIER | ✓ | ✓ | ✓ | ✓ |
| Cohérence fiche ↔ pièce ↔ système (nom, prénom, n°, naissance, nationalité) | AUTO_COHERENCE + confirmation analyste | COHERENT / ANOMALIE | ✓ | ✓ | ✓ | ✓ |
| OCR (assistance seulement, jamais validation) [CDC §12] | AUTO (GED OCR) | proposition | ✓ | ✓ | ✓ | ✓ |
| Champs obligatoires du formulaire | AUTO | OK / MANQUANT | ✓ | ✓ | ✓ | ✓ |
| Motif PPE présent si PPE | AUTO | OK / KO | ✓ | ✓ | ◐ | ✓ |
| Actionnariat : 0 < % ≤ 100, somme ≤ 100 %, cycles | AUTO_CALCUL | OK / A_VERIFIER / KO | — | ✓ | ◐ | — |
| Calcul BE vs seuil | AUTO_CALCUL | liste BE proposés | — | ✓ | ◐ | ◐ |
| Revue documentaire analyste | MANUEL | CONFORME / NON_CONFORME + motif | ✓ | ✓ | ✓ | ✓ |
| Vérification données système (ORION) | MANUEL (V1, pas d’intégration ORION) | CONFORME / NON_CONFORME | ✓ | ✓ | ✓ | ✓ |

## 5. Type client → Workflow

### 5.1 États et transitions

> Mis à jour le 04/10/2026 : le **chargé clientèle** crée et soumet le dossier ; état
> `ABANDONNE` ajouté ; `EN_CONTROLE` suit des étapes internes (CHECKLIST → CHECKLIST_VALIDEE →
> FICHES → CONTROLES) pour la reprise au point d’arrêt. Les paragraphes « Saisie V1 » ci-dessous
> sont remplacés par [eer-architecture-metier.md §0 bis](eer-architecture-metier.md).

```text
A_COMPLETER → (relance, reste A_COMPLETER) | ABANDONNE (motif obligatoire)
BROUILLON → ABANDONNE (brouillon créé à tort, motif obligatoire)
BROUILLON → SOUMIS → A_AFFECTER → AFFECTE → EN_CONTROLE
EN_CONTROLE → CONFORME | NON_CONFORME
NON_CONFORME → A_COMPLETER → RESOUMIS → EN_CONTROLE
CONFORME → AVIS_CONFORMITE (si requis) → VALIDE
AVIS_CONFORMITE → A_COMPLETER (avis défavorable, motif obligatoire)
CONFORME → VALIDE (si avis non requis)
VALIDE → CLOTURE → ARCHIVE
```

**Pas d’état REJETÉ** (décision du 04/10/2026) : un dossier non conforme ou un avis
défavorable repart toujours en complément sur le même dossier.

Saisie V1 (décision du 04/10/2026) : l’**agent conformité** crée le dossier à réception
du dossier papier, le soumet, puis le contrôle. La séparation des rôles porte donc sur
**contrôleur ≠ auteur de l’avis / de la validation**, pas sur créateur ≠ contrôleur.

**Accès au module = tous les droits EER** (décision du 04/10/2026, Administrateur Système) :
tout agent ayant accès au département et au module EER (CORE ADMIN) reçoit `eer.admin`
(toutes les permissions, toutes agences) ; l’Administrateur Système (superuser) aussi.
Sans accès au module, aucun droit EER, même avec un rôle `eer.*`. Le paramètre daté
`workflow.separation_roles` vaut **false** : une même personne peut créer, contrôler,
émettre l’avis et valider. Réactivable par une nouvelle valeur datée `true` (la règle
s’applique alors si le paramètre en vigueur **et** l’instantané du dossier l’activent).

| Transition | Permission | Garde backend |
|------------|------------|---------------|
| BROUILLON → SOUMIS | `eer.submit` | champs obligatoires du socle présents |
| SOUMIS → A_AFFECTER | système | automatique |
| A_AFFECTER → AFFECTE | `eer.assign` (ou auto-affectation par l’agent créateur) | analyste habilité |
| AFFECTE → EN_CONTROLE | `eer.control` | analyste affecté |
| EN_CONTROLE → CONFORME / NON_CONFORME | `eer.control` | décision calculée (pas INCOMPLET) |
| NON_CONFORME → A_COMPLETER | `eer.complement.request` | ≥ 1 élément ciblé |
| A_COMPLETER → RESOUMIS | `eer.complement.receive` | éléments ciblés fournis |
| CONFORME → AVIS_CONFORMITE | `eer.control` | avis requis (5.2) |
| AVIS_CONFORMITE → VALIDE | `eer.avis` | avis favorable ; ≠ contrôleur si séparation active |
| AVIS_CONFORMITE → A_COMPLETER | `eer.avis` | avis défavorable, motif + éléments ciblés |
| CONFORME → VALIDE | `eer.validate` | avis non requis ; ≠ contrôleur si séparation active |
| VALIDE → CLOTURE | `eer.validate` | — |
| CLOTURE → ARCHIVE | `eer.archive` | — |
| BROUILLON → ABANDONNE | `eer.update` | motif obligatoire (décision du 04/10/2026 : aucun dossier n’est supprimé, le brouillon reste tracé) |
| A_COMPLETER → ABANDONNE | `eer.validate` | motif obligatoire |
| (tout statut) → supprimé | `eer.admin` | motif obligatoire ; **suppression logique** (décision du 04/10/2026) : `deleted_at` / `deleted_by_id` / `motif_suppression`, dossier retiré des listes, du tableau de bord et de l’API (404) ; versions, historique (`SUPPRESSION`), décisions et visas conservés ; audit CORE `eer.dossier.delete` |

La permission existante `eer.reject` n’est pas utilisée par ce workflow (proposition :
la retirer des rôles lors de la migration sécurité, ou la réserver à l’avis défavorable).

### 5.1 bis Ouverture avant / après contrôle (décision du 04/10/2026)

Les deux cas existent. Un compte peut être ouvert dans ORION alors qu’un élément manque
ou pose problème (ex. NIF absent ou erroné) : le dossier reste alors **non conforme /
à compléter** pendant que le compte est actif.

- `eer_dossiers.moment_controle` : `PREALABLE` (avant ouverture) ou `A_POSTERIORI`.
- `racine_client` et `etat_compte` facultatifs en `PREALABLE`, renseignés dès l’ouverture.
- **Ouverture sous réserve** : `etat_compte` renseigné alors que la décision n’est pas
  CONFORME → les anomalies ouvertes portent une `echeance_regularisation` ; alertes à
  l’échéance ; le reporting distingue « compte ouvert + dossier non conforme » (comme
  l’Excel : conformité NON + état Actif).
- Les cas d’avis **préalable** documentés (5.2) restent bloquants côté workflow ; leur
  application avant l’ouverture ORION est une règle de procédure hors système
  (BEA DIGITAL n’ouvre pas les comptes).

### 5.2 Avis Conformité KYC obligatoire

| Type / condition | Avis requis | Source |
|------------------|-------------|--------|
| PP risque FAIBLE, sans PPE ni FATCA | Non | — |
| PP risque MOYEN ou ELEVE | Oui (validation préalable) | [FICHES][CDC §17] |
| Toute PM privée | Oui | [FICHES] |
| PM publique | Oui (« Toute ouverture de compte d’une Personne Morale est soumise à l’accord du Service Conformité KYC ») | [FICHES] |
| Association / ONG / Fondation / Coopérative / Parti politique / Projet | Oui (risque élevé automatique) | [FICHES] |
| PPE = OUI (toute partie) | Oui | [CDC §15] |
| FATCA indice = OUI | Oui | [CDC §16] |
| Mandataire | Avis sur la fiche mandataire | [FICHES] |

## 6. Mapping Excel Feuil1 → modèle EER

| Colonne Excel [XLS] | Champ EER | Remarque |
|---------------------|-----------|----------|
| AGENCE | `eer_dossiers.agence_id` → `agences.libelle` | libellés identiques à la base |
| RACINE CLIENT | `racine_client` | ORION ; nullable avant ouverture |
| NOM CLIENT | partie client (nom / raison sociale) | |
| PROFIL | `type_client_code` | valeurs Personne_Physique… |
| SOUS PROFIL | `profil_code` | Salarié, SARL… (notre « profil ») |
| DATE EER | `date_eer` | |
| RISQUE CLIENT LBC FT | `risque_lbcft` | dernier niveau validé |
| PPE | `ppe_dossier` | [À CONFIRMER] client seul ou toute partie |
| FATCA | `fatca_dossier` | idem |
| Résidence | partie client `residence` | [À CONFIRMER] résident/non-résident ou pays |
| Estimation revenus par mois | `tranche_mouvement_code` | confirmé : fiches « tranche du revenu mensuel estimé » |
| Conformité physique du dossier | `conformite_physique` | axe PHYSIQUE |
| Conformité des données systèmes | `conformite_systeme` | axe SYSTEME |
| Etat du compte | `etat_compte` | Actif / Inactif / Bloqué / Fermé ; saisie manuelle V1 (ORION) |
| Analyste en charge | `analyste_id` | |
| Observations éléments non conformes | généré depuis anomalies ouvertes + observation | « description — observation », séparées par « ; » |
| Conforme (S) | `code_conforme` (dérivé) | 1 ssi physique = système = `CONFORME` |
| Non conforme (T) | `code_non_conforme` (dérivé) | 1 ssi physique ou système = `NON_CONFORME` |

Feuil2 → routes `GET /eer/kpis/agencies` (15 agences listées ; la base en compte 17 : AMANTY et
ZOUERATE en plus, affichées à 0 si vides), `/kpis/profiles` (4 types), `/kpis/account-statuses`
(4 états). Règles détaillées : [eer-architecture-metier.md §11 bis et §21](eer-architecture-metier.md).

## 7. Questions ouvertes

Tranchées le 04/10/2026 :

- Moment du contrôle : **les deux** (préalable ou a posteriori, ouverture sous réserve possible) → §5.1 bis.
- Saisie V1 : **agent conformité**, à réception du dossier papier.
- État REJETÉ : **non**.
- Sous-domaines Conformité : **créés** en « bientôt » dans CORE ADMIN (LBC-FT, FATCA,
  Gestion des dossiers clients, Demandes de prêt, Déclarations BCM, Correspondants
  bancaires, Vérification des procurations). « Dossiers ouverture compte » = module EER [CDC §9].

Résolues par les fiches officielles (04/10/2026) : libellés et listes (champs libres,
situation matrimoniale, formes de mandat), tranches PM publique / association, PPE-FATCA
absents en PM publique, BE en PM publique (oui) et en association (non), colonne
« Estimation revenus par mois » = tranche.

Bloquantes pour les migrations :

1. **Pièces justificatives** par profil (justificatif PP selon profil, documents société,
   actes de l’entité publique, documents association, justificatifs BE) : absentes des fiches
   comme du cahier des charges. Sans cette liste, la checklist documentaire ne contient que
   les fiches, la pièce d’identité et le spécimen.
2. **Périmètre « Mise à jour du dossier client »** : les fiches servent aussi aux mises à jour.
   Le module EER les traite-t-il dès la V1, ou seulement les entrées en relation ?
3. Dossier jamais régularisé (client qui ne revient pas) : reste `A_COMPLETER` avec
   relances, ou clôture possible en « non conforme » ?

Non bloquantes (paramètres, valeurs vides en attendant) :

4. **Tableau des signataires** : quelles fonctions signent, dans quel ordre, et quelles
   valeurs d’avis (favorable / défavorable / réserve) ?
5. Pièce d’identité exigée pour les gérants (PM) et signataires (association) ?
6. Colonnes Excel PPE, FATCA, Résidence : client seul ou mandataires inclus ; résident ou pays.
7. Statut PPE / FATCA d’une PM publique : vraiment non applicable, ou à porter par ses mandataires ?
8. « Procédure classifications risques clients » (citée par les fiches) si calcul automatique souhaité.
9. Délai « expiration proche » (jours).
10. Gravités d’anomalie et libellés.
11. ~~Séparation contrôleur ≠ auteur de l’avis / validation~~ : désactivée (décision du 04/10/2026).
12. ~~Règle d’accès inter-agences~~ : tout agent du module voit toutes les agences (décision du 04/10/2026).
13. Délai de régularisation par défaut d’une ouverture sous réserve (ex. NIF manquant).
14. Fichier `TABLEAU DE SUIVI EER 2026 v2.xlsx` (feuille FLUX) à récupérer au bureau.
