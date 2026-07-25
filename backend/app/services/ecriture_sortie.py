from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.data.comptes_sortie_el_amana import COMPTE_MOINS_VALUE, COMPTE_PLUS_VALUE, COMPTE_TRESORERIE
from app.models import EcritureComptable, Immobilisation


def plan_ecritures_cession(
    immo: Immobilisation,
    *,
    cumul: Decimal,
    valeur_brute: Decimal,
    vnc: Decimal,
    prix_cession: Decimal,
    plus_value: Decimal,
    moins_value: Decimal,
) -> list[tuple[str, str, Decimal, str]]:
    compte_immo = immo.compte_immobilisation or "142000"
    compte_amort = immo.compte_amortissement or "148000"
    lines: list[tuple[str, str, Decimal, str]] = []

    if cumul > 0:
        lines.append((compte_amort, compte_immo, cumul, "Reprise amortissements — cession"))
    if prix_cession > 0:
        lines.append((COMPTE_TRESORERIE, compte_immo, min(prix_cession, vnc), "Encaissement cession"))
    if plus_value > 0:
        lines.append((COMPTE_TRESORERIE, COMPTE_PLUS_VALUE, plus_value, "Plus-value de cession"))
    if moins_value > 0:
        lines.append((COMPTE_MOINS_VALUE, compte_immo, moins_value, "Moins-value de cession"))

    return lines


def plan_ecritures_rebut(
    immo: Immobilisation,
    *,
    cumul: Decimal,
    vnc: Decimal,
) -> list[tuple[str, str, Decimal, str]]:
    compte_immo = immo.compte_immobilisation or "142000"
    compte_amort = immo.compte_amortissement or "148000"
    lines: list[tuple[str, str, Decimal, str]] = []
    if cumul > 0:
        lines.append((compte_amort, compte_immo, cumul, "Reprise amortissements — rebut"))
    if vnc > 0:
        lines.append((COMPTE_MOINS_VALUE, compte_immo, vnc, "Perte nette — mise au rebut"))
    return lines


async def enregistrer_ecritures_sortie(
    db: AsyncSession,
    *,
    immo: Immobilisation,
    date_ecriture: date,
    reference: str,
    lines: list[tuple[str, str, Decimal, str]],
) -> list[EcritureComptable]:
    journal = immo.categorie.journal_code if immo.categorie else "OD"
    created: list[EcritureComptable] = []
    for idx, (debit, credit, montant, libelle) in enumerate(lines, start=1):
        if montant <= 0:
            continue
        row = EcritureComptable(
            journal_code=journal,
            date_ecriture=date_ecriture,
            libelle=libelle,
            compte_debit=debit,
            compte_credit=credit,
            montant=montant.quantize(Decimal("0.01")),
            reference=f"{reference}-{idx}",
            immobilisation_id=immo.id,
            generee_auto=True,
            validee=True,
        )
        db.add(row)
        created.append(row)
    await db.flush()
    return created
