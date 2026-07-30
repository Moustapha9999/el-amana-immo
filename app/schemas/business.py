"""Backward-compatible exports."""

from app.schemas.common import MessageResponse, PaginatedResponse
from app.schemas.immobilisation import ImmobilisationCreate, ImmobilisationRead, ImmobilisationUpdate
from app.schemas.organisation import AgenceCreate, AgenceRead

__all__ = [
    "AgenceCreate",
    "AgenceRead",
    "ImmobilisationCreate",
    "ImmobilisationRead",
    "ImmobilisationUpdate",
    "MessageResponse",
    "PaginatedResponse",
]
