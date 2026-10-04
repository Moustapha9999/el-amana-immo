"""Chargement initial EER : référentiels, paramètres, règles de checklist.

Inséré seulement si absent, jamais réécrit : une fois en base, le paramétrage appartient
au métier (écran règles, phase C). Une règle modifiée = nouvelle version, jamais un UPDATE.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.eer_referentiel import PARAMETRES_INITIAUX, REGLES_CHECKLIST_INITIALES, referentiels_initiaux
from app.models import EerChecklistRegle, EerParametre, EerReferentiel
from app.services.eer.checklist_engine import Regle


async def initialiser_referentiel(db: AsyncSession, *, date_effet: date | None = None) -> dict[str, int]:
    date_effet = date_effet or date.today()
    ajouts = {"referentiels": 0, "parametres": 0, "regles": 0}

    existants = {(r.domaine, r.code): r for r in (await db.execute(select(EerReferentiel))).scalars()}
    for ligne in referentiels_initiaux():
        cle = (ligne["domaine"], str(ligne["code"]))
        if cle in existants:
            continue
        parent = existants.get((ligne["parent"][0], str(ligne["parent"][1]))) if ligne["parent"] else None
        ref = EerReferentiel(domaine=cle[0], code=cle[1], libelle=ligne["libelle"], ordre=ligne["ordre"],
                             parent_id=parent.id if parent else None, actif=True, meta=_json(ligne["meta"]))
        db.add(ref)
        await db.flush()
        existants[cle] = ref
        ajouts["referentiels"] += 1

    codes_parametres = set((await db.execute(select(EerParametre.code))).scalars())
    for code, valeur in PARAMETRES_INITIAUX.items():
        if code not in codes_parametres:
            db.add(EerParametre(code=code, valeur=valeur, date_effet=date_effet,
                                description="Valeur initiale documentée (fiches officielles / décisions)"))
            ajouts["parametres"] += 1

    codes_regles = set((await db.execute(select(EerChecklistRegle.code))).scalars())
    for data in REGLES_CHECKLIST_INITIALES:
        if data["code"] in codes_regles:
            continue
        regle = Regle.depuis_dict(data)  # valide la condition avant insertion
        db.add(EerChecklistRegle(
            code=regle.code, version=1, libelle=regle.libelle, categorie=regle.categorie, axe=regle.axe,
            nature=regle.nature, portee=regle.portee, role_cible=regle.role_cible, obligatoire=regle.obligatoire,
            condition=_json(regle.condition), ordre=regle.ordre, type_controle=regle.type_controle,
            document_type_code=regle.document_type, date_effet=date_effet, actif=True))
        ajouts["regles"] += 1
    await db.flush()
    return ajouts


def _json(valeur):
    """Les StrEnum deviennent des chaînes simples dans le JSONB."""
    if isinstance(valeur, dict):
        return {str(k): _json(v) for k, v in valeur.items()}
    if isinstance(valeur, (list, tuple)):
        return [_json(v) for v in valeur]
    if isinstance(valeur, str):
        return str(valeur)
    return valeur
