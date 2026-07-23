"""Comptes 28xxx (réévaluation) et 781xxx (reprises) — plan El Amana."""

COMPTE_REEVALUATION_DEFAUT = "282160"


def compte_reprise_from_dotation(compte_dotation: str | None) -> str:
    """681240 → 781240 (reprise symétrique de la dotation)."""
    if compte_dotation and compte_dotation.startswith("681") and len(compte_dotation) >= 4:
        return "781" + compte_dotation[3:]
    return "781000"
