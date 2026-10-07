"""Règles métier du circuit Achat → Réception → Facture → Paiement.

Fonctions pures (aucun accès base) : le service les applique à chaque écriture,
quel que soit le client appelant. Le frontend peut recalculer pour l'affichage,
mais seule cette logique fait foi.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status

from app.schemas.nombres import QTY_DEC, format_qty
from app.services.reporting_export import format_montant

ZERO = Decimal("0")
CENT = Decimal("100")
TOLERANCE = Decimal("0.01")


def refus(detail: str, *, code: int = status.HTTP_400_BAD_REQUEST) -> HTTPException:
    return HTTPException(code, detail=detail)


def verrou(detail: str) -> HTTPException:
    return refus(detail, code=status.HTTP_409_CONFLICT)


# --- Calculs ---


def arrondi_montant(v: Any) -> Decimal:
    return Decimal(str(v or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def arrondi_quantite(v: Any) -> Decimal:
    return Decimal(str(v or 0)).quantize(QTY_DEC, rounding=ROUND_HALF_UP)


def qte(v: Any) -> str:
    return format_qty(arrondi_quantite(v))


def prix_net(prix_unitaire: Any, remise_pct: Any = ZERO) -> Decimal:
    """PU après remise, arrondi à 2 décimales (base de facturation d'une ligne BC)."""
    return arrondi_montant(
        arrondi_montant(prix_unitaire) * (Decimal("1") - Decimal(str(remise_pct or 0)) / CENT)
    )


@dataclass(frozen=True)
class MontantsLigne:
    ht: Decimal
    tva: Decimal
    ttc: Decimal


def calculer_ligne(
    quantite: Any, prix_unitaire: Any, remise_pct: Any = ZERO, taux_tva: Any = ZERO
) -> MontantsLigne:
    """HT = qté × PU × (1 − remise) ; TVA = arrondi(HT × taux) ; TTC = HT + TVA."""
    brut = arrondi_quantite(quantite) * arrondi_montant(prix_unitaire)
    ht = arrondi_montant(brut - brut * Decimal(str(remise_pct or 0)) / CENT)
    tva = arrondi_montant(ht * Decimal(str(taux_tva or 0)) / CENT)
    return MontantsLigne(ht=ht, tva=tva, ttc=ht + tva)


def totaliser(lignes: Iterable[MontantsLigne]) -> MontantsLigne:
    ht = tva = ZERO
    for m in lignes:
        ht += m.ht
        tva += m.tva
    return MontantsLigne(ht=ht, tva=tva, ttc=ht + tva)


def cle_designation(v: str | None) -> str:
    return " ".join((v or "").lower().split())


# --- Bon de commande ---

BC_BROUILLON = "BROUILLON"
BC_SOUMIS = "SOUMIS"
BC_VALIDE = "VALIDE"
BC_ENVOYE = "ENVOYE"
BC_PARTIEL = "PARTIEL"
BC_RECU = "RECU"
BC_CLOTURE = "CLOTURE"
BC_REJETE = "REJETEE"
BC_ANNULE = "ANNULEE"

BC_TRANSITIONS: dict[str, tuple[frozenset[str], str]] = {
    "soumettre": (frozenset({BC_BROUILLON}), BC_SOUMIS),
    "retour_brouillon": (frozenset({BC_SOUMIS}), BC_BROUILLON),
    "valider": (frozenset({BC_SOUMIS}), BC_VALIDE),
    "envoyer": (frozenset({BC_VALIDE}), BC_ENVOYE),
    "cloturer": (frozenset({BC_RECU}), BC_CLOTURE),
    "rejeter": (frozenset({BC_SOUMIS}), BC_REJETE),
    "annuler": (frozenset({BC_BROUILLON, BC_SOUMIS, BC_VALIDE, BC_ENVOYE}), BC_ANNULE),
}
# Actions réservées à mg.purchase.approve (les autres : mg.purchase.create).
BC_ACTIONS_APPROBATION = frozenset({"valider", "rejeter", "cloturer"})

BC_STATUTS_RECEPTION = frozenset({BC_VALIDE, BC_ENVOYE, BC_PARTIEL})
BC_STATUTS_FACTURATION = frozenset({BC_VALIDE, BC_ENVOYE, BC_PARTIEL, BC_RECU, BC_CLOTURE})
BC_STATUTS_FIGES = frozenset({BC_CLOTURE, BC_ANNULE, BC_REJETE})

# Hors brouillon : logistique, contacts et modalités de règlement seulement.
# Lignes, fournisseur, date, devise (donc montants) sont figés.
BC_CHAMPS_LOGISTIQUES = frozenset(
    {
        "date_livraison_prevue",
        "agence_livraison_id",
        "adresse_livraison",
        "agence_facturation_id",
        "adresse_facturation",
        "acheteur_nom",
        "acheteur_tel",
        "conditions",
        "incoterm",
        "conditions_paiement",
        "moyen_paiement",
        "ref_paiement",
        "montant_paiement",
        "observation",
    }
)


def champs_bc_modifiables(statut: str) -> frozenset[str] | None:
    """None = tout est modifiable ; ensemble vide = rien."""
    if statut == BC_BROUILLON:
        return None
    if statut in BC_STATUTS_FIGES:
        return frozenset()
    return BC_CHAMPS_LOGISTIQUES


def bc_editable(statut: str) -> bool:
    return statut not in BC_STATUTS_FIGES


def statut_bc_selon_receptions(
    lignes: Sequence[Any], *, envoye: bool
) -> str:
    """Statut BC déduit des quantités reçues (après réception ou annulation)."""
    if lignes and all(
        arrondi_quantite(lg.quantite_recue) >= arrondi_quantite(lg.quantite) for lg in lignes
    ):
        return BC_RECU
    if any(arrondi_quantite(lg.quantite_recue) > 0 for lg in lignes):
        return BC_PARTIEL
    return BC_ENVOYE if envoye else BC_VALIDE


def signature_ligne_bc(row: Any) -> tuple:
    """Empreinte d'une ligne BC pour détecter une modification réelle."""
    return (
        cle_designation(getattr(row, "description", "")),
        arrondi_quantite(getattr(row, "quantite", 0)),
        arrondi_montant(getattr(row, "prix_unitaire", 0)),
        (getattr(row, "uom", None) or "U").strip().upper(),
        arrondi_montant(getattr(row, "remise_pct", 0) or 0),
        arrondi_montant(getattr(row, "taux_tva", 0) or 0),
    )


# --- Facture ---

FAC_BROUILLON = "BROUILLON"
FAC_RECUE = "RECUE"
FAC_ANOMALIE = "ANOMALIE"
FAC_VALIDEE = "VALIDEE"
FAC_A_PAYER = "A_PAYER"
FAC_PARTIELLE = "PARTIELLEMENT_PAYEE"
FAC_PAYEE = "PAYEE"
FAC_ANNULEE = "ANNULEE"

FACTURE_STATUTS_MODIFIABLES = frozenset({FAC_BROUILLON, FAC_RECUE, FAC_ANOMALIE})
FACTURE_STATUTS_VALIDES = frozenset({FAC_VALIDEE, FAC_A_PAYER, FAC_PARTIELLE, FAC_PAYEE})
FACTURE_STATUTS_PAYABLES = frozenset({FAC_VALIDEE, FAC_A_PAYER, FAC_PARTIELLE})

PAY_A_PAYER = "A_PAYER"
PAY_PAYE = "PAYE"
PAY_ANNULE = "ANNULE"


def statut_paiement_facture(ttc: Any, total_paye: Any) -> str:
    ttc = arrondi_montant(ttc)
    paye = arrondi_montant(total_paye)
    if paye <= 0:
        return FAC_A_PAYER
    if paye + TOLERANCE > ttc:
        return FAC_PAYEE
    return FAC_PARTIELLE


def verifier_montant_paiement(montant: Any, ttc: Any, deja_engage: Any) -> None:
    """montant ≤ TTC − paiements déjà engagés (payés ou programmés)."""
    montant = arrondi_montant(montant)
    if montant <= 0:
        raise refus("Le montant du paiement doit être supérieur à 0.")
    reste = max(ZERO, arrondi_montant(ttc) - arrondi_montant(deja_engage))
    if montant > reste + TOLERANCE / 2:
        raise refus(
            f"Le montant du paiement ({montant_lisible(montant)}) dépasse le reste à payer "
            f"({montant_lisible(reste)})."
        )


def montant_lisible(v: Any) -> str:
    """40 000 / 12 500,50 — sans « ,00 » pour les montants entiers."""
    s = format_montant(v)
    return s[:-3] if s.endswith(",00") else s


# --- Rapprochement facture ↔ BC ↔ réceptions ---


@dataclass
class EcartLigne:
    designation: str
    bc_ligne_id: UUID | None
    quantite_commandee: Decimal = ZERO
    quantite_recue: Decimal = ZERO
    quantite_deja_facturee: Decimal = ZERO
    quantite_facturee: Decimal = ZERO
    prix_unitaire_bc: Decimal | None = None
    prix_unitaire_facture: Decimal = ZERO
    taux_tva_bc: Decimal | None = None
    taux_tva_facture: Decimal = ZERO
    ok: bool = True
    motifs: list[str] = field(default_factory=list)


@dataclass
class Rapprochement:
    ecart_quantite: bool
    ecart_montant: bool
    lignes: list[EcartLigne]
    details: list[str]
    attendu_ttc: Decimal
    facture_ttc: Decimal

    @property
    def resultat(self) -> str:
        return "ANOMALIE" if (self.ecart_quantite or self.ecart_montant) else "CONFORME"


def associer_ligne_bc(
    bc_lignes: Sequence[Any], bc_ligne_id: UUID | None, designation: str
) -> Any | None:
    """Lien explicite ligne BC en priorité ; désignation normalisée (unique) en secours."""
    if bc_ligne_id is not None:
        for lg in bc_lignes:
            if lg.id == bc_ligne_id:
                return lg
        raise refus(f"La ligne « {designation} » ne correspond à aucune ligne de ce bon de commande.")
    cle = cle_designation(designation)
    candidats = [lg for lg in bc_lignes if cle_designation(lg.description) == cle]
    return candidats[0] if len(candidats) == 1 else None


def verifier_plafond_commande(
    bc_lignes: Sequence[Any],
    facture_par_ligne: dict[UUID, Decimal],
    deja_facture: dict[UUID, Decimal],
) -> None:
    """Refus dur : on ne facture jamais plus que la quantité commandée."""
    by_id = {lg.id: lg for lg in bc_lignes}
    for lid, qty in facture_par_ligne.items():
        lg = by_id[lid]
        reste = arrondi_quantite(lg.quantite) - arrondi_quantite(deja_facture.get(lid, ZERO))
        if arrondi_quantite(qty) > reste:
            raise refus(
                f"Quantité facturée {qte(qty)} > reste à facturer {qte(max(reste, ZERO))} "
                f"sur la commande pour « {lg.description} »."
            )


def rapprocher_facture(
    bc_lignes: Sequence[Any],
    facture_lignes: Sequence[Any],
    deja_facture: dict[UUID, Decimal],
    facture_ttc: Any,
) -> Rapprochement:
    """Contrôle 3 voies ligne par ligne.

    ``facture_lignes`` : objets avec designation, quantite, prix_unitaire, taux_tva, bc_ligne_id.
    ``deja_facture`` : quantités des AUTRES factures actives, par ligne BC.

    Quantité : facturé ≤ reçu − déjà facturé (facturation partielle conforme).
    Prix / TVA : identiques à la ligne BC. Montant : TTC facture = TTC recalculé.
    """
    by_id = {lg.id: lg for lg in bc_lignes}
    par_ligne: dict[UUID, Decimal] = {}
    for fl in facture_lignes:
        if fl.bc_ligne_id is not None:
            par_ligne[fl.bc_ligne_id] = par_ligne.get(fl.bc_ligne_id, ZERO) + arrondi_quantite(fl.quantite)

    ecart_q = ecart_m = False
    details: list[str] = []
    lignes: list[EcartLigne] = []
    attendu: list[MontantsLigne] = []

    for fl in facture_lignes:
        pu_fac = arrondi_montant(fl.prix_unitaire)
        taux_fac = arrondi_montant(fl.taux_tva or 0)
        e = EcartLigne(
            designation=fl.designation,
            bc_ligne_id=fl.bc_ligne_id,
            quantite_facturee=arrondi_quantite(fl.quantite),
            prix_unitaire_facture=pu_fac,
            taux_tva_facture=taux_fac,
        )
        bc = by_id.get(fl.bc_ligne_id) if fl.bc_ligne_id is not None else None
        if bc is None:
            e.ok = False
            e.motifs.append("Ligne absente du bon de commande")
            ecart_q = True
            details.append(f"« {fl.designation} » : ligne absente du BC")
            attendu.append(calculer_ligne(fl.quantite, pu_fac, ZERO, taux_fac))
        else:
            pu_bc = prix_net(bc.prix_unitaire, getattr(bc, "remise_pct", 0))
            taux_bc = arrondi_montant(getattr(bc, "taux_tva", 0) or 0)
            e.quantite_commandee = arrondi_quantite(bc.quantite)
            e.quantite_recue = arrondi_quantite(bc.quantite_recue)
            e.quantite_deja_facturee = arrondi_quantite(deja_facture.get(bc.id, ZERO))
            e.prix_unitaire_bc = pu_bc
            e.taux_tva_bc = taux_bc
            disponible = e.quantite_recue - e.quantite_deja_facturee
            total_ligne = par_ligne.get(bc.id, ZERO)
            if total_ligne > disponible:
                e.ok = False
                e.motifs.append(
                    f"Facturé {qte(total_ligne)} > reçu non facturé {qte(max(disponible, ZERO))}"
                )
                ecart_q = True
                details.append(
                    f"« {bc.description} » : facturé {qte(total_ligne)} > reçu non facturé "
                    f"{qte(max(disponible, ZERO))}"
                )
            if abs(pu_fac - pu_bc) > TOLERANCE / 2:
                e.ok = False
                e.motifs.append(f"PU {format_montant(pu_fac)} ≠ BC {format_montant(pu_bc)}")
                ecart_m = True
                details.append(
                    f"« {bc.description} » : PU facturé {format_montant(pu_fac)} ≠ BC {format_montant(pu_bc)}"
                )
            if taux_fac != taux_bc:
                e.ok = False
                e.motifs.append(f"TVA {format_montant(taux_fac)} % ≠ BC {format_montant(taux_bc)} %")
                ecart_m = True
                details.append(
                    f"« {bc.description} » : TVA {format_montant(taux_fac)} % ≠ BC {format_montant(taux_bc)} %"
                )
            attendu.append(calculer_ligne(fl.quantite, pu_bc, ZERO, taux_bc))
        lignes.append(e)

    attendu_ttc = totaliser(attendu).ttc
    fac_ttc = arrondi_montant(facture_ttc)
    if abs(fac_ttc - attendu_ttc) > TOLERANCE:
        ecart_m = True
        details.append(
            f"Montant TTC facture {format_montant(fac_ttc)} ≠ attendu {format_montant(attendu_ttc)}"
        )
    # Dédoublonne les messages d'une même ligne BC facturée en plusieurs lignes.
    details = list(dict.fromkeys(details))
    return Rapprochement(
        ecart_quantite=ecart_q,
        ecart_montant=ecart_m,
        lignes=lignes,
        details=details,
        attendu_ttc=attendu_ttc,
        facture_ttc=fac_ttc,
    )
