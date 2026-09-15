# Kit USB unique — PC comptable

## Sur cette machine (développement)

```powershell
.\scripts\export-kit-comptable.ps1
```

Résultat : `dist\kit-comptable\` (images backend+frontend, scripts, `.cmd`, dump local s’il existe).

## Sur le PC comptable

### Emplacement

Copier **tout** le dossier USB vers :

```text
C:\immo
```

### Déjà installé (saisies à conserver)

1. Copier le contenu du kit **par-dessus** `C:\immo` (surtout `images\`, `scripts\`, `*.cmd`).
2. **Ne pas** supprimer `.env.docker`.
3. Double-cliquer **`MettreAJour.cmd`**.
4. Ouvrir http://localhost puis Ctrl+F5.

### Première installation

1. Docker Desktop installé et Running.
2. Dossier collé dans `C:\immo`.
3. Double-cliquer **`Installer.cmd`**.

## Lanceurs (double-clic à la racine de `C:\immo`)

| Fichier | Action |
|---------|--------|
| `Demarrer.cmd` | Démarre la plateforme |
| `Arreter.cmd` | Arrête les conteneurs (données conservées) |
| `Sauvegarder.cmd` | Dump PostgreSQL + documents → `backups\` |
| `Verifier.cmd` | Santé conteneurs + comptages + `/health` |
| `MettreAJour.cmd` | Nouveau logiciel **sans** perdre les saisies |
| `Installer.cmd` | Première installation seulement |

## Règles données

- `MettreAJour.cmd` : backup automatique puis nouvelles images ; volume Postgres **intact**.
- `Installer.cmd` : restaure un dump **uniquement** si la base est vide.
- **Interdit** : `docker compose down -v`.

## Si vous avez un backup du PC comptable

Placez le fichier `.dump` dans `C:\immo\backups\` **avant** une install sur base vide, ou conservez-le après `Sauvegarder.cmd` pour migration serveur.
