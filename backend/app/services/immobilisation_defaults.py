from uuid import UUID

from app.core.exceptions import NotFoundError, ValidationError
from app.models import CategorieImmobilisation, Immobilisation
from app.schemas.immobilisation import ImmobilisationCreate, ImmobilisationUpdate
from app.services.amortissement_rate import taux_lineaire_from_duree_annees as _taux_from_duree_annees


def _sync_duree_mois_from_annees(annees: int | None) -> int:
    if annees is None or annees <= 0:
        return 0
    return annees * 12


async def load_categorie(db, categorie_id: UUID | None) -> CategorieImmobilisation | None:
    if categorie_id is None:
        return None
    row = await db.get(CategorieImmobilisation, categorie_id)
    if row is None or row.deleted_at is not None:
        raise NotFoundError("Type d'immobilisation", str(categorie_id))
    return row


def _resolve_taux_defaut(categorie: CategorieImmobilisation, duree_annees: int | None):
    """Taux annuel issu de la catégorie (ou dérivé de la durée)."""
    if categorie.taux_lineaire_defaut is not None:
        return categorie.taux_lineaire_defaut
    return _taux_from_duree_annees(duree_annees)


def apply_categorie_defaults(
    immo: Immobilisation,
    categorie: CategorieImmobilisation,
    *,
    override_comptes: bool = True,
    preserve_taux: bool = False,
) -> None:
    if override_comptes or not immo.compte_immobilisation:
        immo.compte_immobilisation = categorie.compte_immobilisation
    if categorie.amortissable:
        if override_comptes or not immo.compte_amortissement:
            immo.compte_amortissement = categorie.compte_amortissement
        if override_comptes or not immo.compte_dotation:
            immo.compte_dotation = categorie.compte_dotation
        if immo.duree_annees is None and categorie.duree_annees_defaut is not None:
            immo.duree_annees = categorie.duree_annees_defaut
        if immo.duree_mois in (0, 60) and immo.duree_annees is not None:
            immo.duree_mois = _sync_duree_mois_from_annees(immo.duree_annees)
        # Taux catégorie par défaut — conserve une surcharge utilisateur si demandée
        if not preserve_taux or immo.taux is None:
            immo.taux = _resolve_taux_defaut(categorie, immo.duree_annees)
        immo.mode_amortissement = categorie.mode_amortissement_defaut
        # Banque El Amana : dates d'arrêt trimestrielles
        immo.periodicite = "trimestriel"
        immo.prorata_temporis = True
    else:
        immo.compte_amortissement = None
        immo.compte_dotation = None
        immo.duree_annees = None
        immo.duree_mois = 0
        immo.taux = None


def validate_immobilisation(immo: Immobilisation, categorie: CategorieImmobilisation | None) -> None:
    if categorie is None:
        raise ValidationError("Le type d'immobilisation (catégorie El Amana) est obligatoire.")
    if not immo.designation or not str(immo.designation).strip():
        raise ValidationError("La désignation est obligatoire.")
    # Legacy : backfill date comptabilisation = date acquisition si absente
    if immo.date_comptabilisation is None:
        immo.date_comptabilisation = immo.date_acquisition
    if immo.date_comptabilisation < immo.date_acquisition:
        raise ValidationError(
            "La date de comptabilisation ne peut pas être antérieure à la date d'acquisition."
        )
    if immo.quantite < 1:
        raise ValidationError("La quantité doit être au moins 1.")
    if immo.date_mise_en_service and immo.date_mise_en_service < immo.date_acquisition:
        raise ValidationError("La date de mise en service ne peut pas être antérieure à la date d'acquisition.")
    if not immo.compte_immobilisation:
        raise ValidationError("Le compte comptable de l'immobilisation est obligatoire.")
    if categorie.amortissable and (immo.duree_annees is None or immo.duree_annees <= 0):
        raise ValidationError("Durée d'utilisation (années) requise pour une immobilisation amortissable.")
    if categorie.amortissable and (immo.taux is None or immo.taux < 0):
        raise ValidationError("Le taux annuel d'amortissement (%) est obligatoire pour une immobilisation amortissable.")
    if categorie.amortissable:
        # Comptes issus du Type (liés au plan comptable) — obligatoires pour la logique banque
        if not immo.compte_amortissement:
            immo.compte_amortissement = categorie.compte_amortissement
        if not immo.compte_dotation:
            immo.compte_dotation = categorie.compte_dotation
        if not immo.compte_amortissement or not immo.compte_dotation:
            raise ValidationError(
                "Le Type doit avoir un compte d'amortissement et de dotation (Plan comptable)."
            )
        immo.periodicite = "trimestriel"


def prepare_create(payload: ImmobilisationCreate, categorie: CategorieImmobilisation) -> dict:
    """Prépare le payload create — taux catégorie par défaut, surcharge utilisateur autorisée."""
    data = payload.model_dump()
    user_taux = data.get("taux")
    duree_annees = data.get("duree_annees")
    if duree_annees is not None:
        data["duree_mois"] = _sync_duree_mois_from_annees(duree_annees)
    elif categorie.duree_annees_defaut is not None:
        data["duree_annees"] = categorie.duree_annees_defaut
        data["duree_mois"] = _sync_duree_mois_from_annees(categorie.duree_annees_defaut)
    annees = data.get("duree_annees")
    if not data.get("compte_immobilisation"):
        data["compte_immobilisation"] = categorie.compte_immobilisation
    if categorie.amortissable:
        data["periodicite"] = "trimestriel"
        # Note banque : taux issu de la catégorie, modifiable par utilisateur autorisé
        if user_taux is not None:
            data["taux"] = user_taux
        else:
            data["taux"] = _resolve_taux_defaut(categorie, annees)
    else:
        data["taux"] = None
    return data


def apply_update_fields(immo: Immobilisation, payload: ImmobilisationUpdate) -> bool:
    """Applique les champs update. Retourne True si le taux a été fourni explicitement."""
    data = payload.model_dump(exclude_unset=True)
    taux_override = "taux" in data
    duree_annees = data.pop("duree_annees", None)
    if duree_annees is not None:
        immo.duree_annees = duree_annees
        immo.duree_mois = _sync_duree_mois_from_annees(duree_annees)
    for key, value in data.items():
        setattr(immo, key, value)
    if immo.duree_annees and immo.duree_annees > 0 and immo.taux is None:
        immo.taux = _taux_from_duree_annees(immo.duree_annees)
    immo.periodicite = "trimestriel"
    return taux_override
