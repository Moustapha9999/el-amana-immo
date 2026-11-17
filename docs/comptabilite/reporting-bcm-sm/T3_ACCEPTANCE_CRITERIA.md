# T3 — Critères d’acceptation

Module `reporting-bcm-sm` — socle uniquement.

## 1. Critères vérifiables

| # | Critère | Preuve |
|---|---------|--------|
| C1 | Module présent au catalogue, `espace_code=comptabilite`, `entry_path` renseigné | API `/plateforme/modules/reporting-bcm-sm` ou admin catalogue |
| C2 | Carte visible sur hub `/comptabilite` pour utilisateur habilité | UI |
| C3 | Login 2 module obligatoire avant écrans métier | Redirection `/modules/reporting-bcm-sm/acces` |
| C4 | Routes `/reporting-bcm-sm/accueil`, `/campagnes`, création, détail | Navigation |
| C5 | Déconnexion module → `/comptabilite` (jamais Login 1) | Contrat routes |
| C6 | `GET /api/v1/reporting-bcm-sm/campaigns` liste | HTTP 200 + corps |
| C7 | `POST .../campaigns` crée `BROUILLON` | HTTP 201 + audit |
| C8 | Doublon période ouverte refusé | Erreur métier structurée |
| C9 | Sans permission `.view` / `.prepare` → refus | 403 |
| C10 | Sans session module → refus | 401/403 |
| C11 | Aucun import DET/COND / mapping / moteur / Excel dans le lot | Revue PR |
| C12 | Aucune touche BCM Clientèle / amortissement_engine / MFA | Diff |
| C13 | Migration uniquement sous `backend/alembic/versions/` | Diff |
| C14 | Feedback UI via FeedbackService (pas `alert`) | Revue front |
| C15 | Working tree / CI verte sur tests ajoutés | CI / pytest |

## 2. Tests fonctionnels

- Créer campagne octobre 2026 → visible en liste  
- Ouvrir détail → statut `BROUILLON`, période correcte  
- Tentative 2ᵉ campagne même période/version ouverte → échec  
- Utilisateur Lecteur : voit liste, ne crée pas  

## 3. Tests de sécurité / permissions

- Token plateforme seul (Login 1) sans Login 2 module → pas d’accès API métier  
- Permission `view` sans `prepare` → GET OK, POST KO  
- Pas d’endpoint T3 qui bypasse `require_permission`  

## 4. Tests de concurrence

- Deux POST simultanés même période : au plus une campagne créée (contrainte UNIQUE + gestion erreur)  
- Pas de corruption de ligne (pas de partial update hors transaction)  

## 5. Tests d’audit

- Création campagne → entrée `audit_logs` (action, entity, user, request_id)  
- Pas de secret / contenu fichier dans l’audit  

## 6. Validation finale T3

T3 accepté si **C1–C15** OK et aucun critère hors périmètre livré par erreur.

**Ensuite seulement :** ouverture T4 (imports) sur validation produit séparée.
