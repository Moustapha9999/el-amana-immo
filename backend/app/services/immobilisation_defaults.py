from uuid import UUID
from app.core.exceptions import NotFoundError, ValidationError
from app.models import CategorieImmobilisation, Immobilisation
from app.schemas.immobilisation import ImmobilisationCreate, ImmobilisationUpdate


def _sync_duree_mois_from_annees(annees: int | None) -> int:
    if annees is None or annees <= 0:
        return 0
    return annees * 12


from app.services.amortissement_rate import taux_lineaire_from_duree_annees as _taux_from_duree_annees


async def load_categorie(db, categorie_id: UUID | None) -> CategorieImmobilisation | None:
    if categorie_id is None:
        return None
    row = await db.get(CategorieImmobilisation, categorie_id)
    if row is None or row.deleted_at is not None:
        raise NotFoundError("Type d'immobilisation", str(categorie_id))
    return row


def apply_categorie_defaults(
    immo: Immobilisation,
    categorie: CategorieImmobilisation,
    *,
    override_comptes: bool = True,
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
        # Taux métier El Amana (prioritaire) — sinon dérivé de la durée
        if categorie.taux_lineaire_defaut is not None:
            immo.taux = categorie.taux_lineaire_defaut
        else:
            immo.taux = _taux_from_duree_annees(immo.duree_annees)
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
    if immo.quantite < 1:
        raise ValidationError("La quantité doit être au moins 1.")
    if immo.date_mise_en_service and immo.date_mise_en_service < immo.date_acquisition:
        raise ValidationError("La date de mise en service ne peut pas être antérieure à la date d'acquisition.")
    if categorie.amortissable and (immo.duree_annees is None or immo.duree_annees <= 0):
        raise ValidationError("Durée d'utilisation (années) requise pour une immobilisation amortissable.")
    # Forcer la périodicité trimestrielle (dates d'arrêt banque)
    if categorie.amortissable:
        immo.periodicite = "trimestriel"


def prepare_create(payload: ImmobilisationCreate, categorie: CategorieImmobilisation) -> dict:
    data = payload.model_dump()
    data.pop("taux", None)
    duree_annees = data.get("duree_annees")
    if duree_annees is not None:
        data["duree_mois"] = _sync_duree_mois_from_annees(duree_annees)
    elif categorie.duree_annees_defaut is not None:
        data["duree_annees"] = categorie.duree_annees_defaut
        data["duree_mois"] = _sync_duree_mois_from_annees(categorie.duree_annees_defaut)
    annees = data.get("duree_annees")
    if categorie.amortissable:
        data["periodicite"] = "trimestriel"
        if categorie.taux_lineaire_defaut is not None:
            data["taux"] = categorie.taux_lineaire_defaut
        elif annees:
            data["taux"] = _taux_from_duree_annees(annees)
    return data


def apply_update_fields(immo: Immobilisation, payload: ImmobilisationUpdate) -> None:
    data = payload.model_dump(exclude_unset=True)
    data.pop("taux", None)
    duree_annees = data.pop("duree_annees", None)
    if duree_annees is not None:
        immo.duree_annees = duree_annees
        immo.duree_mois = _sync_duree_mois_from_annees(duree_annees)
    for key, value in data.items():
        setattr(immo, key, value)
    if immo.duree_annees and immo.duree_annees > 0 and immo.taux is None:
        immo.taux = _taux_from_duree_annees(immo.duree_annees)
    immo.periodicite = "trimestriel"
