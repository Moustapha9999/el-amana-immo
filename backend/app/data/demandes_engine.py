"""Moteur central de demandes — constantes partagées (pas un second système).

Les tables physiques restent `mg_employee_requests` / `mg_request_categories`
(déjà en production). Le routage se fait par espace plateforme
(`source_espace_code` → `target_espace_code`), pas par un référentiel parallèle.
"""

from __future__ import annotations

# Espace plateforme → module Demandes (code unique : plateforme_modules.code).
DEMANDES_MODULES: dict[str, str] = {
    "comptabilite": "demandes-comptabilite",
    "credit": "demandes-credit",
    "rh": "demandes-rh",
    "informatique": "demandes-informatique",
    "moyens-generaux": "demandes-mg",
}

DEMANDES_MODULE_CODES: frozenset[str] = frozenset(DEMANDES_MODULES.values())

# Modules qui voient l’inbox (demandes dont target_espace = leur espace).
PROCESSOR_MODULE_CODES: frozenset[str] = frozenset({"demandes-mg"})

ESPACE_BY_DEMANDES_MODULE: dict[str, str] = {v: k for k, v in DEMANDES_MODULES.items()}

ESPACE_LABELS: dict[str, str] = {
    "comptabilite": "Comptabilité",
    "credit": "Crédit",
    "rh": "RH",
    "informatique": "Informatique",
    "moyens-generaux": "Moyens Généraux",
}

# Types MG proposés à tous les départements demandeurs.
DEFAULT_SOURCE_ESPACES: list[str] = ["*"]

PROCESSOR_ROLES: dict[str, frozenset[str]] = {
    "moyens-generaux": frozenset(
        {
            "demandes-mg.lecteur",
            "demandes-mg.gestionnaire",
            "demandes-mg.valideur",
            "demandes-mg.admin",
        }
    ),
}

RETIRED_ESPACE_CODES: frozenset[str] = frozenset({"employe"})
RETIRED_MODULE_CODES: frozenset[str] = frozenset({"demandes-employes"})


def is_demandes_module(code: str | None) -> bool:
    return (code or "").strip().lower() in DEMANDES_MODULE_CODES


def is_processor_module(code: str | None) -> bool:
    return (code or "").strip().lower() in PROCESSOR_MODULE_CODES


def espace_for_module(module_code: str | None) -> str | None:
    return ESPACE_BY_DEMANDES_MODULE.get((module_code or "").strip().lower())
