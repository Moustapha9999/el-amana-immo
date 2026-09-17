Les fichiers de sauvegarde (dumps PostgreSQL et copies de documents) sont stockés ici.

Ne pas commiter le contenu de ce dossier (dumps hors git).
Ne jamais supprimer un dump tant qu'un dump plus récent n'a pas été restauré avec succès.

Restore non destructif (refuse si `public` a déjà des tables) :
`.\scripts\db-restore.ps1` / `./scripts/db-restore.sh`.
Voir [docs/base-de-donnees-unique.md](../docs/base-de-donnees-unique.md).
