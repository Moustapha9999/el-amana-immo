from app.models import CategorieImmobilisation


def categorie_audit_snapshot(row: CategorieImmobilisation) -> dict:
    return {
        "code": row.code,
        "famille": row.famille,
        "amortissable": row.amortissable,
        "duree_annees_defaut": row.duree_annees_defaut,
        "compte_immobilisation": row.compte_immobilisation,
        "compte_amortissement": row.compte_amortissement,
        "compte_dotation": row.compte_dotation,
        "mode_amortissement_defaut": row.mode_amortissement_defaut.value
        if hasattr(row.mode_amortissement_defaut, "value")
        else row.mode_amortissement_defaut,
        "periodicite_defaut": row.periodicite_defaut,
    }
