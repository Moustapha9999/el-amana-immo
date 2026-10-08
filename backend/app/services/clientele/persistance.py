"""Enregistrement d'une consolidation ORION : upsert clients (racine) puis comptes (numéro de compte).

Tout ou rien : une anomalie bloquante, une agence inconnue ou un compte déjà rattaché à une
autre racine refuse l'ensemble du lot. Un extrait plus ancien n'écrase jamais un plus récent.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass
from datetime import date

from sqlalchemy import func, literal_column, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Agence, ClienteleClient, ClienteleCompte
from app.services.clientele.consolidation import Consolidation

TAILLE_LOT = 1000


class ConsolidationRefusee(ValueError):
    def __init__(self, motifs: list[str]):
        super().__init__(" ; ".join(motifs[:20]))
        self.motifs = motifs


@dataclass(frozen=True)
class Bilan:
    clients_crees: int
    clients_mis_a_jour: int
    comptes_crees: int
    comptes_mis_a_jour: int


def _lots(lignes: list[dict]) -> list[list[dict]]:
    return [lignes[i:i + TAILLE_LOT] for i in range(0, len(lignes), TAILLE_LOT)]


async def _verifier(session: AsyncSession, consolidation: Consolidation) -> dict[str, uuid.UUID]:
    motifs = [f"ligne {a.numero} : {a.message}" for a in consolidation.anomalies if a.bloquante]
    agences = dict((await session.execute(select(Agence.code, Agence.id))).all())
    inconnues = sorted({c.code_agence for c in consolidation.comptes.values()} - set(agences))
    motifs += [f"agence inconnue : {code}" for code in inconnues]
    numeros = list(consolidation.comptes)
    for i in range(0, len(numeros), TAILLE_LOT):
        existants = await session.execute(
            select(ClienteleCompte.compte, ClienteleCompte.racine_client)
            .where(ClienteleCompte.compte.in_(numeros[i:i + TAILLE_LOT])))
        for numero, racine in existants:
            nouvelle = consolidation.comptes[numero].racine_client
            if racine != nouvelle:
                motifs.append(f"compte {numero} déjà rattaché au client {racine}, pas à {nouvelle}")
    if motifs:
        raise ConsolidationRefusee(motifs)
    return agences


async def enregistrer(session: AsyncSession, consolidation: Consolidation, date_extraction: date) -> Bilan:
    """Écrit la consolidation dans la session courante (le commit reste à l'appelant)."""
    agences = await _verifier(session, consolidation)
    clients = [
        {"id": uuid.uuid4(), **asdict(c), "premiere_extraction": date_extraction, "date_extraction": date_extraction}
        for c in consolidation.clients.values()
    ]
    comptes = []
    for c in consolidation.comptes.values():
        valeurs = asdict(c)
        valeurs["agence_id"] = agences[valeurs.pop("code_agence")]
        comptes.append({"id": uuid.uuid4(), **valeurs,
                        "premiere_extraction": date_extraction, "date_extraction": date_extraction})

    clients_crees, clients_maj = await _upsert(session, ClienteleClient, clients, "racine_client")
    comptes_crees, comptes_maj = await _upsert(session, ClienteleCompte, comptes, "compte")
    return Bilan(clients_crees, clients_maj, comptes_crees, comptes_maj)


_CLIENTS_SQL = """
INSERT INTO clientele_clients (
    id, racine_client, raison_sociale, prenoms, date_naissance, date_naissance_orion,
    nationalite, statut_resident, agent_economique, situation_juridique, categorie_juridique,
    secteur_activite, famille_secteur_activite, type_identifiant, identifiant_orion, nni, nif, rcs,
    premiere_extraction, date_extraction
)
SELECT DISTINCT ON (racine_client)
    gen_random_uuid(), racine_client, raison_sociale, prenoms, date_naissance, date_naissance_orion,
    nationalite, statut_resident, agent_economique, situation_juridique, categorie_juridique,
    secteur_activite, famille_secteur_activite, type_identifiant, identifiant_orion, nni, nif, rcs,
    :d, :d
FROM clientele_import_lignes
WHERE import_id = :iid AND statut_ligne = 'VALIDE' AND racine_client IS NOT NULL
ORDER BY racine_client, numero_ligne
ON CONFLICT (racine_client) DO UPDATE SET
    raison_sociale = EXCLUDED.raison_sociale,
    prenoms = EXCLUDED.prenoms,
    date_naissance = EXCLUDED.date_naissance,
    date_naissance_orion = EXCLUDED.date_naissance_orion,
    nationalite = EXCLUDED.nationalite,
    statut_resident = EXCLUDED.statut_resident,
    agent_economique = EXCLUDED.agent_economique,
    situation_juridique = EXCLUDED.situation_juridique,
    categorie_juridique = EXCLUDED.categorie_juridique,
    secteur_activite = EXCLUDED.secteur_activite,
    famille_secteur_activite = EXCLUDED.famille_secteur_activite,
    type_identifiant = EXCLUDED.type_identifiant,
    identifiant_orion = EXCLUDED.identifiant_orion,
    nni = EXCLUDED.nni,
    nif = EXCLUDED.nif,
    rcs = EXCLUDED.rcs,
    date_extraction = EXCLUDED.date_extraction,
    updated_at = now()
WHERE clientele_clients.date_extraction <= EXCLUDED.date_extraction
RETURNING (xmax = 0) AS cree
"""

_COMPTES_SQL = """
INSERT INTO clientele_comptes (
    id, compte, rib, racine_client, agence_id, ncg, rubrique_comptable, etat_compte,
    date_ouverture, ddc, ddd, devise, conformite_compte, liste_interdiction,
    premiere_extraction, date_extraction
)
SELECT DISTINCT ON (s.compte)
    gen_random_uuid(), s.compte, s.rib, s.racine_client, a.id, s.ncg, s.rubrique_comptable,
    s.etat_compte, s.date_ouverture, s.ddc, s.ddd, s.devise, s.conformite_compte,
    s.liste_interdiction, :d, :d
FROM clientele_import_lignes s
JOIN agences a ON a.code = s.code_agence
WHERE s.import_id = :iid AND s.statut_ligne = 'VALIDE' AND s.compte IS NOT NULL
ORDER BY s.compte, s.numero_ligne
ON CONFLICT (compte) DO UPDATE SET
    rib = EXCLUDED.rib,
    racine_client = EXCLUDED.racine_client,
    agence_id = EXCLUDED.agence_id,
    ncg = EXCLUDED.ncg,
    rubrique_comptable = EXCLUDED.rubrique_comptable,
    etat_compte = EXCLUDED.etat_compte,
    date_ouverture = EXCLUDED.date_ouverture,
    ddc = EXCLUDED.ddc,
    ddd = EXCLUDED.ddd,
    devise = EXCLUDED.devise,
    conformite_compte = EXCLUDED.conformite_compte,
    liste_interdiction = EXCLUDED.liste_interdiction,
    date_extraction = EXCLUDED.date_extraction,
    updated_at = now()
WHERE clientele_comptes.date_extraction <= EXCLUDED.date_extraction
RETURNING (xmax = 0) AS cree
"""


def _bilan_returning(rows) -> tuple[int, int]:
    crees = maj = 0
    for (cree,) in rows:
        if cree:
            crees += 1
        else:
            maj += 1
    return crees, maj


async def enregistrer_depuis_staging(session: AsyncSession, import_id: uuid.UUID,
                                     date_extraction: date) -> Bilan:
    """Upsert SQL depuis le staging (le commit reste à l'appelant). N'efface aucun client."""
    params = {"iid": import_id, "d": date_extraction}
    clients = _bilan_returning((await session.execute(text(_CLIENTS_SQL), params)).all())
    comptes = _bilan_returning((await session.execute(text(_COMPTES_SQL), params)).all())
    return Bilan(clients[0], clients[1], comptes[0], comptes[1])


async def _upsert(session: AsyncSession, modele, lignes: list[dict], cle: str) -> tuple[int, int]:
    crees = maj = 0
    table = modele.__table__
    figees = {"id", cle, "premiere_extraction", "created_at"}
    for lot in _lots(lignes):
        stmt = insert(table).values(lot)
        maj_cols = {k: stmt.excluded[k] for k in lot[0] if k not in figees}
        maj_cols["updated_at"] = func.now()
        stmt = stmt.on_conflict_do_update(
            index_elements=[cle],
            set_=maj_cols,
            where=table.c.date_extraction <= stmt.excluded.date_extraction,
        ).returning(literal_column("(xmax = 0)").label("cree"))
        for (cree,) in await session.execute(stmt):
            if cree:
                crees += 1
            else:
                maj += 1
    return crees, maj
