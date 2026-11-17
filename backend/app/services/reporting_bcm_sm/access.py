"""Droits de contribution SM — Login 2, pas le responsable.

Les habilitations sont attribuées dans CORE ADMIN. ``view`` reste lecture seule.
L’approbation finale (SoD) n’est pas un droit de préparation.
"""

from __future__ import annotations

from app.services.permission_service import user_has_permission_codes
from app.services.reporting_bcm_sm.constants import (
    PERM_CONTROL,
    PERM_CORRECT,
    PERM_IMPORT,
    PERM_PARAMS,
    PERM_PREPARE,
)

# Contribution à la préparation (saisie C, confirmation de proposition).
SAISIR_PARAM_PERMS = (PERM_PARAMS, PERM_PREPARE, PERM_CONTROL, PERM_CORRECT)
# Lancer / relancer les contrôles métier.
CONTROL_RUN_PERMS = (PERM_PREPARE, PERM_CONTROL, PERM_IMPORT)
# Importer / confirmer la BAL DET.
IMPORT_PERMS = (PERM_IMPORT, PERM_PREPARE, PERM_CONTROL)


def can_saisir_parametre(have: set[str]) -> bool:
    return user_has_permission_codes(have, *SAISIR_PARAM_PERMS)


def can_lancer_controles(have: set[str]) -> bool:
    return user_has_permission_codes(have, *CONTROL_RUN_PERMS)


def can_importer(have: set[str]) -> bool:
    return user_has_permission_codes(have, *IMPORT_PERMS)
