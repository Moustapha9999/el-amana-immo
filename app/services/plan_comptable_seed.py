"""Seed idempotent du plan comptable et types El Amana."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.el_amana_referentiel import (
    LIBELLE_ECRITURE_MODELE,
    PLAN_COMPTABLE_EL_AMANA,
    TYPES_IMMOBILISATION_EL_AMANA,
)
from app.models import CategorieImmobilisation, ComptePlanComptable, ParametrageEcriture


async def seed_plan_comptable_el_amana(session: AsyncSession) -> dict[str, int]:
    """Upsert comptes, types et parametrage ecritures. Retourne des compteurs."""
    stats = {"comptes_created": 0, "comptes_updated": 0, "types_created": 0, "types_updated": 0, "parametrage": 0}

    existing_comptes = {
        c.numero: c
        for c in (await session.execute(select(ComptePlanComptable))).scalars().all()
    }
    for row in PLAN_COMPTABLE_EL_AMANA:
        numero = row["numero"]
        if numero in existing_comptes:
            compte = existing_comptes[numero]
            compte.libelle = row["libelle"]
            compte.type_compte = row["type_compte"]
            stats["comptes_updated"] += 1
        else:
            session.add(
                ComptePlanComptable(
                    numero=numero,
                    libelle=row["libelle"],
                    type_compte=row["type_compte"],
                )
            )
            stats["comptes_created"] += 1

    await session.flush()

    existing_types = {
        t.code: t for t in (await session.execute(select(CategorieImmobilisation))).scalars().all()
    }
    for row in TYPES_IMMOBILISATION_EL_AMANA:
        alt = row.get("comptes_amortissement_alternatifs")
        fields = {
            "famille": row["famille"],
            "type_immobilisation": row["type_immobilisation"],
            "compte_immobilisation": row["compte_immobilisation"],
            "compte_amortissement": row.get("compte_amortissement"),
            "compte_dotation": row.get("compte_dotation"),
            "comptes_amortissement_alternatifs": alt,
            "amortissable": row["amortissable"],
            "duree_annees_defaut": row.get("duree_annees_defaut"),
            "taux_lineaire_defaut": row.get("taux_lineaire_defaut"),
            "mode_amortissement_defaut": row["mode_amortissement_defaut"],
            "periodicite_defaut": row["periodicite_defaut"],
            "prorata_temporis": True,
            "journal_code": "OD",
        }
        code = row["code"]
        if code in existing_types:
            categorie = existing_types[code]
            for key, value in fields.items():
                setattr(categorie, key, value)
            stats["types_updated"] += 1
        else:
            categorie = CategorieImmobilisation(code=code, **fields)
            session.add(categorie)
            existing_types[code] = categorie
            stats["types_created"] += 1

    await session.flush()

    existing_param = {
        p.categorie_id: p for p in (await session.execute(select(ParametrageEcriture))).scalars().all()
    }
    for row in TYPES_IMMOBILISATION_EL_AMANA:
        if not row["amortissable"]:
            continue
        categorie = existing_types[row["code"]]
        debit = row["compte_dotation"]
        credit = row["compte_amortissement"]
        if not debit or not credit:
            continue
        if categorie.id in existing_param:
            param = existing_param[categorie.id]
            param.journal_code = "OD"
            param.compte_debit = debit
            param.compte_credit = credit
            param.libelle_modele = LIBELLE_ECRITURE_MODELE
        else:
            session.add(
                ParametrageEcriture(
                    categorie_id=categorie.id,
                    journal_code="OD",
                    compte_debit=debit,
                    compte_credit=credit,
                    libelle_modele=LIBELLE_ECRITURE_MODELE,
                )
            )
            stats["parametrage"] += 1

    return stats
