"""Sections annuelles archives (S/T cumulatifs comme tableau banque)."""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from app.services.archive_service import _sections_par_exercice, _totaux


def _ligne(
    *,
    d: date | None,
    designation: str,
    vb: str,
    amt_n1: str = "0",
    dotation: str = "0",
    amt_fin: str | None = None,
    vnc: str | None = None,
    is_report: bool = False,
) -> SimpleNamespace:
    vb_d = Decimal(vb)
    n1 = Decimal(amt_n1)
    dot = Decimal(dotation)
    fin = Decimal(amt_fin) if amt_fin is not None else n1 + dot
    return SimpleNamespace(
        date_acquisition=d,
        designation=designation,
        valeur_brute=vb_d,
        amt_n1=n1,
        dotation=dot,
        amt_fin=fin,
        vnc=Decimal(vnc) if vnc is not None else vb_d - fin,
        is_report=is_report,
    )


def test_sections_par_exercice_cumulatifs_et_total_general():
    """S/T annuels cumulatifs ; total général = somme des lignes (pas somme des S/T)."""
    lignes = [
        _ligne(
            d=date(2004, 1, 1),
            designation="REPORT 2003",
            vb="2749059.30",
            amt_n1="2749059.30",
            amt_fin="2749059.30",
            vnc="0",
            is_report=True,
        ),
        _ligne(
            d=date(2004, 3, 31),
            designation="Armoire",
            vb="21000.00",
            amt_n1="21000.00",
            amt_fin="21000.00",
            vnc="0",
        ),
        _ligne(
            d=date(2005, 1, 3),
            designation="Fauteuil",
            vb="22000.00",
            amt_n1="22000.00",
            amt_fin="22000.00",
            vnc="0",
        ),
        _ligne(
            d=date(2005, 2, 7),
            designation="Armoires",
            vb="44000.00",
            amt_n1="44000.00",
            amt_fin="44000.00",
            vnc="0",
        ),
    ]

    sections = _sections_par_exercice(lignes)
    assert [s["annee"] for s in sections] == [2004, 2005]
    assert sections[0]["label"] == "Exercice 2004"
    assert sections[0]["ouverture"] is None
    assert len(sections[0]["lignes"]) == 2
    assert sections[0]["totaux"]["valeur_brute"] == Decimal("2770059.30")
    assert sections[0]["totaux"]["nb_lignes"] == 2

    # Ouverture année N = S/T cumulatif N-1
    assert sections[1]["ouverture"] is not None
    assert sections[1]["ouverture"]["valeur_brute"] == Decimal("2770059.30")
    assert len(sections[1]["lignes"]) == 2
    assert sections[1]["totaux"]["valeur_brute"] == Decimal("2836059.30")
    assert sections[1]["totaux"]["nb_lignes"] == 4

    grand = _totaux(lignes)
    assert grand["valeur_brute"] == Decimal("2836059.30")
    # Ne pas sommer les S/T annuels (cumulatifs) — ça doublerait
    somme_st = sections[0]["totaux"]["valeur_brute"] + sections[1]["totaux"]["valeur_brute"]
    assert somme_st != grand["valeur_brute"]
    assert sections[-1]["totaux"]["valeur_brute"] == grand["valeur_brute"]


def test_sections_rattache_report_ouverture_a_annee_acquisitions():
    """S/T / REPORT daté N-1 est rattaché au bloc de la première année d'acquisitions."""
    lignes = [
        _ligne(
            d=date(2005, 12, 31),
            designation="REPORT 2005",
            vb="2627450.00",
            amt_n1="2627450.00",
            amt_fin="2627450.00",
            vnc="0",
            is_report=True,
        ),
        _ligne(
            d=date(2006, 1, 23),
            designation="Portable Toshiba",
            vb="73000.00",
            amt_n1="73000.00",
            amt_fin="73000.00",
            vnc="0",
        ),
        _ligne(
            d=date(2006, 2, 7),
            designation="Imprimante HP",
            vb="15000.00",
            amt_n1="15000.00",
            amt_fin="15000.00",
            vnc="0",
        ),
    ]
    sections = _sections_par_exercice(lignes)
    assert [s["annee"] for s in sections] == [2006]
    assert sections[0]["ouverture"] is None
    assert len(sections[0]["lignes"]) == 3
    assert sections[0]["lignes"][0].is_report is True
    assert sections[0]["totaux"]["valeur_brute"] == Decimal("2715450.00")
