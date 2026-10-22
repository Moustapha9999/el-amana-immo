"""Cloisonnement des notifications par espace de destination.

Une notification appartient à un seul espace :
- ``module`` : l'espace d'un module (``module_code``) de son département (``espace_code``) ;
- ``core_admin`` : l'espace CORE ADMIN (supervision, restauration, statut des modules) ;
- ``plateforme`` : l'accueil BEA DIGITAL (Login 1), hors module.

Une diffusion vers plusieurs espaces crée une ligne par espace (lecture propre à chacun) et
n'est acceptée que si la route figure dans ``ROUTES_AUTORISEES``.
"""

from __future__ import annotations

PORTEE_MODULE = "module"
PORTEE_CORE_ADMIN = "core_admin"
PORTEE_PLATEFORME = "plateforme"
PORTEES = frozenset({PORTEE_MODULE, PORTEE_CORE_ADMIN, PORTEE_PLATEFORME})

# Code module historique ou GED rattaché sans ambiguïté à un module du catalogue.
MODULE_ALIASES: dict[str, tuple[str, ...]] = {
    "immobilisations": ("immos",),
}

# (module source, module destinataire) : diffusion inter-modules explicitement autorisée.
# Vide par défaut : toute diffusion hors du module d'origine est refusée.
ROUTES_AUTORISEES: frozenset[tuple[str, str]] = frozenset()


def codes_module(module_code: str) -> tuple[str, ...]:
    code = (module_code or "").strip().lower()
    return (code, *MODULE_ALIASES.get(code, ()))


def portee_par_defaut(module_code: str | None) -> str:
    code = (module_code or "").strip().lower()
    if not code:
        return PORTEE_PLATEFORME
    return PORTEE_CORE_ADMIN if code == "core" else PORTEE_MODULE


def route_autorisee(source_module: str, destination_module: str) -> bool:
    if source_module == destination_module:
        return True
    return (source_module, destination_module) in ROUTES_AUTORISEES
