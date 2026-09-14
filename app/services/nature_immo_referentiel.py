"""Référentiel métier Nature IMMO = Types + Plan comptable (source unique banque)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.data.el_amana_referentiel import (
    COMPTES_NON_AMORTISSABLES_EL_AMANA,
    MESSAGE_NON_AMORTISSABLE_EL_AMANA,
    TYPES_IMMOBILISATION_EL_AMANA,
)

# Réexport pour les services d'amortissement
__all__ = [
    "COMPTES_NON_AMORTISSABLES_EL_AMANA",
    "MESSAGE_NON_AMORTISSABLE_EL_AMANA",
    "bank_taux_for_code",
    "bank_taux_for_duree",
    "is_compte_non_amortissable",
    "is_immobilisation_amortissable",
    "normalize_taux_for_categorie",
    "paired_accounts_for_immo",
    "suggest_paired_accounts",
]

# Taux banque figés (ne pas recalculer via 100/durée pour les natures officielles)
BANK_TAUX_BY_CODE: dict[str, Decimal] = {
    row["code"]: Decimal(row["taux_lineaire_defaut"]).quantize(Decimal("0.0001"))
    for row in TYPES_IMMOBILISATION_EL_AMANA
    if row.get("taux_lineaire_defaut") is not None
}

BANK_TAUX_BY_DUREE: dict[int, Decimal] = {}
for row in TYPES_IMMOBILISATION_EL_AMANA:
    duree = row.get("duree_annees_defaut")
    taux = row.get("taux_lineaire_defaut")
    if duree and taux is not None and duree not in BANK_TAUX_BY_DUREE:
        BANK_TAUX_BY_DUREE[int(duree)] = Decimal(taux).quantize(Decimal("0.0001"))

# Compte immo → (amort, dotation)
PAIRS_BY_COMPTE_IMMO: dict[str, tuple[str, str]] = {
    row["compte_immobilisation"]: (row["compte_amortissement"], row["compte_dotation"])
    for row in TYPES_IMMOBILISATION_EL_AMANA
    if row.get("compte_amortissement") and row.get("compte_dotation")
}

FRAIS_CATEGORY_CODES = frozenset({"TY-147050", "TY-147030"})


def is_compte_non_amortissable(compte: str | None) -> bool:
    """True si le compte immobilisation est non amortissable (Banque El Amana)."""
    if not compte:
        return False
    return compte.strip() in COMPTES_NON_AMORTISSABLES_EL_AMANA


def is_immobilisation_amortissable(
    immo: Any,
    categorie: Any | None = None,
) -> bool:
    """Une immobilisation est amortissable sauf comptes 140000 / 142000 / 145300.

    La détection par compte prime sur le flag catégorie (sécurité métier).
    """
    cat = categorie if categorie is not None else getattr(immo, "categorie", None)
    compte = getattr(immo, "compte_immobilisation", None)
    if not compte and cat is not None:
        compte = getattr(cat, "compte_immobilisation", None)
    if is_compte_non_amortissable(compte):
        return False
    if cat is not None and not bool(getattr(cat, "amortissable", False)):
        return False
    if cat is None:
        return False
    return True


def bank_taux_for_code(categorie_code: str | None) -> Decimal | None:
    if not categorie_code:
        return None
    return BANK_TAUX_BY_CODE.get(categorie_code)


def bank_taux_for_duree(annees: int | None) -> Decimal | None:
    """Taux banque pour une durée connue (ex. 3 → 33.33, pas 33.3333)."""
    if annees is None or annees <= 0:
        return None
    if annees in BANK_TAUX_BY_DUREE:
        return BANK_TAUX_BY_DUREE[annees]
    return (Decimal("100") / Decimal(annees)).quantize(Decimal("0.0001"))


def paired_accounts_for_immo(numero_immo: str) -> tuple[str, str] | None:
    return PAIRS_BY_COMPTE_IMMO.get(numero_immo.strip())


def suggest_paired_accounts(numero_immo: str) -> tuple[str, str]:
    """Comptes 148/681 : d'abord la paire banque officielle, sinon suffixe."""
    official = paired_accounts_for_immo(numero_immo)
    if official:
        return official
    digits = "".join(ch for ch in numero_immo if ch.isdigit())
    if len(digits) < 3:
        raise ValueError("Numéro de compte immobilisation trop court.")
    suffix = digits[-3:]
    return f"148{suffix}", f"681{suffix}"


def normalize_taux_for_categorie(
    categorie_code: str | None,
    taux: Decimal | None,
) -> Decimal | None:
    """Aligne les taux Excel ambigus (33) sur le taux banque de la nature."""
    if taux is None:
        return bank_taux_for_code(categorie_code)
    bank = bank_taux_for_code(categorie_code)
    if bank is None:
        return taux.quantize(Decimal("0.0001"))
    # Excel affiche souvent « 33% » pour les frais 3 ans alors que le calcul est 33,33 %
    if categorie_code in FRAIS_CATEGORY_CODES and taux.quantize(Decimal("0.01")) in (
        Decimal("33.00"),
        Decimal("33"),
    ):
        return bank
    return taux.quantize(Decimal("0.0001"))
