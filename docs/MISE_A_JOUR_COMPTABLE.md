# Mise à jour du PC comptable (code du jour)

Kit à utiliser quand l’instance Docker tourne déjà sur le PC banque et contient des saisies.

## Sur la machine de développement (aujourd’hui)

```powershell
# 1. Construire les images à jour
docker compose --env-file .env.docker build frontend backend
docker compose --env-file .env.docker up -d frontend backend

# 2. Exporter le kit de MISE À JOUR (pas le dump de cette machine)
.\scripts\export-kit-comptable.ps1 -UpdateOnly
```

Résultat : `dist\kit-maj-comptable\` (images + scripts + compose).

Copier ce dossier sur clé USB.

## Sur le PC comptable (demain)

1. Sauvegarder d’abord (optionnel si le script le fait déjà) : dans `C:\immo`  
   `.\scripts\backup-local.ps1`
2. Copier le contenu du kit **par-dessus** `C:\immo` (surtout `images\` et `scripts\`).  
   **Ne pas** supprimer `.env.docker`.
3. Lancer :

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\update-on-comptable.ps1
```

4. Ouvrir http://localhost puis **Ctrl+F5**.

## Ce que fait la mise à jour

| Élément | Effet |
|---------|--------|
| Images backend / frontend | Remplacées (nouvelles fonctionnalités) |
| Migrations Alembic | Appliquées au démarrage du backend |
| Volume Postgres | **Conservé** (opérations du comptable intactes) |
| Dump de la machine dev | **Non utilisé** |

## Interdit

- `docker compose down -v` (efface la base)
- Relancer `install-on-comptable.ps1` sur une base déjà remplie (restaure un dump et peut écraser)

## Contrôles après mise à jour

- Connexion OK
- Paramètres → Nouveau compte : durée / taux optionnels
- Archives → Ouvrir un exercice : zone Soldes Orion
- Soldes 142 : plus de zone de saisie Orion ; totaux cohérents
- Inventaire / amortissements : natures non amortissables (140000, 142000, 145300)
