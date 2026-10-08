"""Pont EER ↔ référentiel clientèle (racine ORION 6 chiffres).

Pas de FK : un dossier EER peut précéder l'apparition du client dans ORION.
``eer_parties`` n'est pas fusionné avec ``clientele_clients``.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import AppError
from app.models import ClienteleClient, ClienteleCompte, ClienteleSituation

RACINE_RE = re.compile(r"^[0-9]{6}$")


def normaliser_racine(valeur: str | None, *, obligatoire: bool = False) -> str | None:
    s = (valeur or "").strip()
    if not s:
        if obligatoire:
            raise AppError("Racine client obligatoire", 422, code="RACINE_INVALIDE")
        return None
    if not RACINE_RE.fullmatch(s):
        raise AppError(
            "Racine client invalide (6 chiffres ORION, ex. 000001). Ne pas concaténer un compte.",
            422, code="RACINE_INVALIDE")
    return s


def _vide(valeur: Any) -> bool:
    return valeur is None or (isinstance(valeur, str) and not valeur.strip())


def compte_principal(comptes: list[ClienteleCompte]) -> ClienteleCompte | None:
    if not comptes:
        return None
    ouverts = [c for c in comptes if c.etat_compte == "OUVERT"]
    pool = ouverts or list(comptes)
    return min(pool, key=lambda c: (c.date_ouverture or date.max, c.compte or ""))


def propositions(client: ClienteleClient, *, type_client: str) -> tuple[list[tuple[str, Any]], list[str]]:
    """Chemins fiche EER ← champs ORION. N'invente pas Actif/Inactif."""
    reserves: list[str] = []
    pp = type_client == "PP"
    props: list[tuple[str, Any]] = [
        ("dossier.racine_client", client.racine_client),
        ("client.racine_client", client.racine_client),
        ("client.nom", client.raison_sociale),
        ("client.nationalite", client.nationalite),
    ]
    if pp:
        if client.prenoms:
            props.append(("client.pp.prenom", client.prenoms))
        if client.date_naissance:
            props.append(("client.pp.date_naissance", client.date_naissance.isoformat()))
        if client.type_identifiant == "NNI" and client.nni:
            props.append(("client.piece.type", "NNI"))
            props.append(("client.piece.numero", client.nni))
    else:
        if client.nif:
            props.append(("client.pm.nif", client.nif))
    compte = compte_principal(list(client.comptes))
    if compte:
        props.append(("dossier.numero_compte", compte.compte))
        if compte.date_ouverture:
            props.append(("dossier.date_ouverture_compte", compte.date_ouverture.isoformat()))
        if compte.etat_compte == "FERME":
            props.append(("dossier.etat_compte", "FERME"))
        elif compte.etat_compte == "OUVERT":
            reserves.append(
                "ORION porte OUVERT/FERME des comptes, pas Actif/Inactif EER : "
                "le compte ouvert n'est pas mappé vers Actif.")
    return [(c, v) for c, v in props if not _vide(v)], reserves


async def table_clientele(db: AsyncSession) -> bool:
    return bool(await db.scalar(text("SELECT to_regclass('public.clientele_clients')")))


async def charger_client(db: AsyncSession, racine: str) -> ClienteleClient | None:
    if not await table_clientele(db):
        return None
    return await db.scalar(
        select(ClienteleClient)
        .where(ClienteleClient.racine_client == racine)
        .options(selectinload(ClienteleClient.comptes)))


async def apercu(db: AsyncSession, racine: str) -> dict[str, Any]:
    racine = normaliser_racine(racine, obligatoire=True)  # type: ignore[assignment]
    client = await charger_client(db, racine)
    if client is None:
        return {
            "present": False,
            "racine_client": racine,
            "message": "Absent du référentiel ORION. Un dossier EER peut précéder l'apparition du client.",
        }
    sit = await db.get(ClienteleSituation, racine)
    compte = compte_principal(list(client.comptes))
    type_hint = "PP" if (sit and sit.profil_derive == "PP") else (
        "PM_PRIVEE" if sit and sit.profil_derive == "PM" else "PP")
    props, reserves = propositions(client, type_client="PP" if type_hint == "PP" else "PM_PRIVEE")
    return {
        "present": True,
        "racine_client": racine,
        "nom": client.raison_sociale,
        "prenoms": client.prenoms,
        "nationalite": client.nationalite,
        "date_naissance": client.date_naissance.isoformat() if client.date_naissance else None,
        "profil_derive": sit.profil_derive if sit else None,
        "type_identifiant": client.type_identifiant,
        "nni": client.nni,
        "nif": client.nif,
        "nb_comptes": len(client.comptes),
        "comptes": [
            {"compte": c.compte, "rib": c.rib, "etat_compte": c.etat_compte,
             "date_ouverture": c.date_ouverture.isoformat() if c.date_ouverture else None}
            for c in sorted(client.comptes, key=lambda x: x.compte)
        ],
        "compte_retenu": (
            {"compte": compte.compte, "etat_compte": compte.etat_compte,
             "date_ouverture": compte.date_ouverture.isoformat() if compte.date_ouverture else None}
            if compte else None),
        "propositions": [{"chemin": c, "valeur": v, "source": "ORION"} for c, v in props],
        "reserves": reserves,
    }
