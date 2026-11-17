# T3.4-C — Terminologie SM, KPI, finalisation UI

Branche : `feat/reporting-bcm-sm-t3` · **Aucun commit / push / déploiement.**

Base : T3.4-B (`T3_4B_REPORT.md`, `T3_4B_AUDIT.md`).

## Terminologie SM

**SM = Situation Mensuelle.** Vocabulaire métier unique dans l’UI.

| Ancien (UI) | Nouveau |
|-------------|---------|
| Campagnes | Situations mensuelles |
| Campagne | SM / Situation Mensuelle |
| Nouvelle campagne | Nouvelle SM |
| Fiche campagne | Fiche SM |
| Campagne sélectionnée | SM sélectionnée |
| Progression campagne | Progression de la SM |
| Supprimer / archiver la campagne | Supprimer / archiver la SM |

### Occurrences techniques conservées (volontairement)

- Routes `/reporting-bcm-sm/campagnes…`
- API `/campaigns`, `campaign_id`, JSON `campaigns_*`
- Tables `rbcm_campaign`, modèles SQLAlchemy, services `campaign_service`
- Permissions `reporting-bcm-sm.*` (codes inchangés)
- Selectors Angular `bea-rbcm-campagne-*`, classes `RbcmCampagne*`

Aucune migration « rename campagne → sm ». Compatibilité API préservée.

## Menu / écrans

- Accueil, Situations mensuelles, Nouvelle SM, Imports, BAL DET, Contrôles, Paramètres, Correspondances, **Archives BAL COND**
- Titres de routes Angular mis à jour
- Guide utilisateur : `GUIDE_UTILISATEUR.md`

## KPI dashboard (définition T3.4-C)

| KPI | Statuts |
|-----|---------|
| SM ouvertes | `BROUILLON`, `IMPORTS`, `RAPPROCHEE`, `PARAMETREE`, `ROUVERTE` |
| SM en cours | `IMPORTS`, `RAPPROCHEE`, `PARAMETREE`, `ROUVERTE` |
| SM en attente | `A_CONTROLER` |
| SM calculées | `CALCULEE` |
| SM approuvées | `APPROUVEE` |
| SM clôturées / archivées | `CLOTUREE` |

**Correction :** `CALCULEE` n’est plus comptée dans « ouvertes ».  
`OPEN_CAMPAIGN_STATUSES` (unicité de période) reste = tout sauf `CLOTUREE`.

Champs API ajoutés (rétrocompatibles) : `campaigns_in_progress`, `campaigns_calculated`, `campaigns_approved`, `campaigns_archived`, `status_groups`.

## D01 / D02

- Endpoints workflow présents.
- UI Fiche SM : actions Soumettre / Contrôle OK / Approuver **visibles mais verrouillées** avec explication D01/D02.
- Mapping reste `A_VALIDER` ; ECART `DESACTIVE`.
- Pas de contournement.

## Debounce

RxJS `debounceTime(300)` + `distinctUntilChanged` :

- Situations mensuelles (déjà)
- Correspondances (déjà)
- Imports (ajouté)
- BAL DET (ajouté)
- Contrôles / anomalies (ajouté)

## Prévisualisation BAL DET

Drawer structuré : fichier (nom, taille, SHA, période, lignes), structure, contrôles d’analyse, échantillon ≤ 50 lignes, anomalies.  
Confirmation désactivée si `ready_to_confirm === false` / raisons bloquantes.

## Pagination Contrôles

`GET /campaigns/{id}/reconcile/issues` : page, page_size, search, severity, code, resolved, sort, total.  
UI : filtres + pager première/préc/suiv/dernière + drawer détail (sans action corrective fictive).

## Playwright

Dossier `e2e/reporting-bcm-sm/` (package local, hors `package.json` Angular).  
Scénarios couvrant Login 1+2, nav SM, terminologie, imports, BAL DET, contrôles, params, mapping, archives, notifications, responsive 5 viewports.

**Exécution DEV (16/11/2026) :** suite instable sur la persistance Login 2 lors des `page.goto` successifs (réaffichage écran `/modules/.../acces`). Dernier run : **2 passed / 12 failed** — échecs concentrés sur la session module, pas sur les assertions métier une fois l’écran chargé.  
**Contrôle manuel navigateur DEV :** Accueil SM OK (menu Situations mensuelles / Nouvelle SM / Archives BAL COND ; KPI SM ouvertes ≠ calculées ; D01/D02 visibles en fiche).  
À stabiliser ensuite via `storageState` Login 2 ou navigation par liens shell (hors scope bloquant T3.4-C).

## Responsive

Contrôle manuel Accueil DEV après rebuild. Suite Playwright responsive prête mais impactée par la même flakiness Login 2.

## Tests backend

```
22 passed, 1 skipped  (test_reporting_bcm_sm.py + test_sm_kpi_open_excludes_calculee)
```

## Décisions métier encore bloquantes

| Décision | Impact |
|----------|--------|
| D01 | Pas d’activation mapping / état réglementaire |
| D02 | ECART inactif |
| Import métier octobre | Non démarré — attendre validation T3.4-C |

## État Git

Branche dirty `feat/reporting-bcm-sm-t3`. Pas de commit. DEV uniquement.
