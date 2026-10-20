"""Compatibilité « retour arrière » des migrations Alembic.

Chaque révision postérieure à ``REFERENCE`` déclare au niveau du module :

    retour_arriere = "compatible"    # la version précédente du code fonctionne sur le schéma migré
    retour_arriere = "restauration"  # revenir à la version précédente exige de restaurer la sauvegarde

Usages (depuis ``backend/``, ou dans l'image : ``python scripts/migrations_retour.py``) :

    migrations_retour.py <revision_depuis>   révisions appliquées entre <revision_depuis> et head ;
                                             dernière ligne : RETOUR_ARRIERE=aucune_migration|compatible|restauration
    migrations_retour.py --verifier          échoue si une révision postérieure à REFERENCE ne déclare rien

Une révision antérieure ou égale à ``REFERENCE`` (déjà appliquée sur la base de référence) n'est pas
déclarée : elle compte comme « restauration ».
"""
from __future__ import annotations

import sys
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

REFERENCE = "20261020_clientele_14"
VALEURS = ("compatible", "restauration")


def _scripts() -> ScriptDirectory:
    racine = Path(__file__).resolve().parent.parent
    cfg = Config(str(racine / "alembic.ini"))
    cfg.set_main_option("script_location", str(racine / "alembic"))
    return ScriptDirectory.from_config(cfg)


def _anterieures(sd: ScriptDirectory) -> set[str]:
    return {r.revision for r in sd.iterate_revisions(REFERENCE, "base")}


def _declaration(rev) -> str | None:
    valeur = getattr(rev.module, "retour_arriere", None)
    return valeur if valeur in VALEURS else None


def verifier() -> int:
    sd = _scripts()
    anciennes = _anterieures(sd)
    fautives = [
        r.revision for r in sd.walk_revisions()
        if r.revision not in anciennes and _declaration(r) is None
    ]
    for rev in fautives:
        print(f"ERREUR: {rev} ne déclare pas retour_arriere = \"compatible\" | \"restauration\"")
    return 1 if fautives else 0


def analyser(depuis: str) -> int:
    sd = _scripts()
    anciennes = _anterieures(sd)
    try:
        revisions = list(sd.iterate_revisions("heads", depuis))
    except Exception as exc:  # révision inconnue de cette image, ou hors de la lignée
        print(f"ERREUR: révision {depuis} non analysable ({exc})")
        print("RETOUR_ARRIERE=restauration")
        return 2
    revisions = [r for r in revisions if r.revision != depuis]
    if not revisions:
        print("RETOUR_ARRIERE=aucune_migration")
        return 0
    resultat = "compatible"
    for r in reversed(revisions):
        decl = None if r.revision in anciennes else _declaration(r)
        print(f"  {r.revision} : {decl or 'non déclarée'}")
        if decl != "compatible":
            resultat = "restauration"
    print(f"RETOUR_ARRIERE={resultat}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(64)
    sys.exit(verifier() if sys.argv[1] == "--verifier" else analyser(sys.argv[1]))
