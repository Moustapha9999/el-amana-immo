"""Photographie d'un import confirmé : l'extraction, pas le stock vivant.

Les lignes de staging valides sont ensuite purgées. Le rapprochement A vs B lit
uniquement ces snapshots — l'absence d'une racine dans B n'efface jamais le client.
"""

from __future__ import annotations

import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_CLIENTS = """
INSERT INTO clientele_import_clients (
    id, import_id, racine_client, raison_sociale, prenoms, nationalite, statut_resident,
    agent_economique, situation_juridique, categorie_juridique, secteur_activite,
    famille_secteur_activite, type_identifiant, nni, nif, rcs
)
SELECT DISTINCT ON (racine_client)
    gen_random_uuid(), :iid, racine_client, raison_sociale, prenoms, nationalite, statut_resident,
    agent_economique, situation_juridique, categorie_juridique, secteur_activite,
    famille_secteur_activite, type_identifiant, nni, nif, rcs
FROM clientele_import_lignes
WHERE import_id = :iid AND statut_ligne = 'VALIDE' AND racine_client IS NOT NULL
ORDER BY racine_client, numero_ligne
"""

_COMPTES = """
INSERT INTO clientele_import_comptes (
    id, import_id, rib, compte, racine_client, code_agence, etat_compte, devise, ncg,
    conformite_compte, liste_interdiction, date_ouverture
)
SELECT DISTINCT ON (rib)
    gen_random_uuid(), :iid, rib, compte, racine_client, code_agence, etat_compte, devise, ncg,
    conformite_compte, liste_interdiction, date_ouverture
FROM clientele_import_lignes
WHERE import_id = :iid AND statut_ligne = 'VALIDE' AND rib IS NOT NULL
ORDER BY rib, numero_ligne
"""


async def photographier_import(session: AsyncSession, import_id: uuid.UUID) -> None:
    await session.execute(text(_CLIENTS), {"iid": import_id})
    await session.execute(text(_COMPTES), {"iid": import_id})
