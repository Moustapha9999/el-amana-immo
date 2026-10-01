"""Visibilité des demandes — le frontend n'est pas un contrôle de sécurité.

Employé : uniquement requester_id = utilisateur courant.
Traitant : uniquement target_espace_code de son périmètre, avec la permission
de traitement correspondante.
Un super-utilisateur n'élargit pas le périmètre employé.
"""

from __future__ import annotations

import uuid

from fastapi import HTTPException, status

from app.services.permission_service import user_has_permission_codes

OWNER_DENIED = "Demande non autorisée"
SCOPE_DENIED = "Demande hors de votre périmètre"
SCOPE_REQUIRED = "Périmètre de demandes obligatoire"

# Département cible → permission de traitement. Pas d'accès aux autres cibles.
PROCESSOR_PERMISSION_BY_TARGET: dict[str, str] = {
    "moyens-generaux": "mg.request.view",
}

_HIDDEN_FROM_OWNER = frozenset({"INTERNAL", "PROCESSOR"})


def require_owner(row, user) -> None:
    if getattr(row, "requester_id", None) != getattr(user, "id", None):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=OWNER_DENIED)


def require_target(row, target_espace: str) -> None:
    if (getattr(row, "target_espace_code", None) or "") != target_espace:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=SCOPE_DENIED)


def can_read_request(
    *,
    requester_id: uuid.UUID,
    user_id: uuid.UUID,
    target_espace: str | None,
    permission_codes: set[str],
) -> bool:
    """Vrai si l'utilisateur est le demandeur, ou traitant du département cible."""
    if requester_id == user_id:
        return True
    needed = PROCESSOR_PERMISSION_BY_TARGET.get(target_espace or "")
    if needed and user_has_permission_codes(permission_codes, needed):
        return True
    return False


def visible_comments(comments, audience: str):
    """Le demandeur ne reçoit pas les notes internes de traitement."""
    if audience == "processor":
        return list(comments)
    return [
        c
        for c in comments
        if str(getattr(c, "visibility", "SHARED") or "SHARED").upper() not in _HIDDEN_FROM_OWNER
    ]
