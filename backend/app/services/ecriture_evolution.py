from datetime import date
from decimal import Decimal

from app.data.comptes_evolution_el_amana import COMPTE_REEVALUATION_DEFAUT, compte_reprise_from_dotation
from app.models import Immobilisation
from app.services.ecriture_sortie import enregistrer_ecritures_sortie


def plan_ecritures_reevaluation(immo: Immobilisation, *, delta: Decimal) -> list[tuple[str, str, Decimal, str]]:
    compte_immo = immo.compte_immobilisation or "142000"
    compte_reeval = COMPTE_REEVALUATION_DEFAUT
    montant = abs(delta).quantize(Decimal("0.01"))
    if montant <= 0:
        return []
    if delta > 0:
        return [(compte_immo, compte_reeval, montant, f"Réévaluation à la hausse — {immo.code_inventaire}")]
    return [(compte_reeval, compte_immo, montant, f"Réévaluation à la baisse — {immo.code_inventaire}")]


def plan_ecritures_reprise(immo: Immobilisation, *, montant: Decimal) -> list[tuple[str, str, Decimal, str]]:
    compte_amort = immo.compte_amortissement or "148000"
    compte_reprise = compte_reprise_from_dotation(immo.compte_dotation)
    m = montant.quantize(Decimal("0.01"))
    if m <= 0:
        return []
    return [(compte_reprise, compte_amort, m, f"Reprise sur amortissements — {immo.code_inventaire}")]


async def enregistrer_ecritures_evolution(
    db,
    *,
    immo: Immobilisation,
    date_ecriture: date,
    reference: str,
    lines: list[tuple[str, str, Decimal, str]],
):
    return await enregistrer_ecritures_sortie(
        db,
        immo=immo,
        date_ecriture=date_ecriture,
        reference=reference,
        lines=lines,
    )
