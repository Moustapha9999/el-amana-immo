"""Catalogue des erreurs transversales BEA DIGITAL (titre, message, statut, journalisation).

Source unique des messages par défaut utilisés par ``app/core/api_errors.py``.
Les codes métier propres à un module (``TRANSITION_INVALIDE``, ``STOCK_INSUFFISANT``…)
restent levés avec leur message par ``AppError(message, code=...)`` ; seul le titre
est déduit ici de leur statut HTTP. Miroir front : ``core/feedback/api-error.ts``.
Documentation : ``docs/catalogue-erreurs.md``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

DEBUG, INFO, WARNING, ERROR = logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR


@dataclass(frozen=True)
class ErrorSpec:
    code: str
    status: int
    title: str
    message: str
    log_level: int = WARNING
    retryable: bool = False


_SPECS: tuple[ErrorSpec, ...] = (
    # --- Requête / validation ------------------------------------------------
    ErrorSpec("BAD_REQUEST", 400, "Requête invalide",
              "Certaines informations sont incorrectes. Vérifiez les champs indiqués, puis réessayez."),
    ErrorSpec("BUSINESS_RULE_ERROR", 400, "Opération impossible", "L’opération n’a pas pu être effectuée."),
    ErrorSpec("INVALID_VALUE", 400, "Valeur non autorisée",
              "Une valeur saisie n’est pas autorisée. Vérifiez les champs à liste de choix."),
    ErrorSpec("VALIDATION_ERROR", 422, "Champs à corriger",
              "Certaines informations ne respectent pas le format attendu. Vérifiez les champs indiqués."),
    ErrorSpec("PAYLOAD_TOO_LARGE", 413, "Fichier trop volumineux",
              "Le fichier ou la requête est trop volumineux. Choisissez un fichier plus petit."),
    ErrorSpec("URI_TOO_LONG", 414, "Recherche trop longue",
              "La recherche ou le filtre est trop long. Réduisez les critères, puis réessayez."),
    ErrorSpec("UNSUPPORTED_MEDIA_TYPE", 415, "Format non pris en charge", "Ce format de fichier n’est pas pris en charge."),
    ErrorSpec("NOT_ACCEPTABLE", 406, "Format indisponible", "Ce format de réponse n’est pas disponible pour cette ressource."),
    ErrorSpec("RANGE_NOT_SATISFIABLE", 416, "Téléchargement impossible",
              "La partie demandée du fichier n’est pas disponible. Relancez le téléchargement."),
    ErrorSpec("HEADERS_TOO_LARGE", 431, "Requête refusée",
              "La requête n’a pas pu être traitée. Reconnectez-vous ; si le problème persiste, contactez le support."),
    # --- Authentification ----------------------------------------------------
    ErrorSpec("AUTH_REQUIRED", 401, "Session expirée", "Votre session a expiré. Reconnectez-vous pour continuer.", INFO),
    ErrorSpec("UNAUTHENTICATED", 401, "Session expirée", "Votre session a expiré. Reconnectez-vous pour continuer.", INFO),
    ErrorSpec("TOKEN_INVALID", 401, "Session expirée", "Votre session a expiré. Reconnectez-vous pour continuer.", INFO),
    ErrorSpec("PLATFORM_SESSION_EXPIRED", 401, "Session expirée",
              "Votre session a expiré. Reconnectez-vous pour continuer.", INFO),
    ErrorSpec("MODULE_SESSION_EXPIRED", 401, "Session du module expirée",
              "Votre session sur ce module a expiré. Reconnectez-vous au module pour continuer.", INFO),
    ErrorSpec("MODULE_AUTH_REQUIRED", 401, "Connexion au module requise",
              "Connectez-vous au module pour continuer.", INFO),
    ErrorSpec("SESSION_REVOKED", 401, "Session révoquée",
              "Votre session a été fermée (déconnexion ou révocation). Reconnectez-vous pour continuer."),
    ErrorSpec("USER_NOT_FOUND", 401, "Session expirée", "Votre session a expiré. Reconnectez-vous pour continuer."),
    ErrorSpec("AUTH_INVALID_CREDENTIALS", 401, "Connexion refusée", "Identifiant ou mot de passe incorrect."),
    ErrorSpec("TOTP_REQUIRED", 401, "Code de vérification requis",
              "Saisissez le code à 6 chiffres de votre application d’authentification.", INFO),
    ErrorSpec("TOTP_INVALID", 401, "Code de vérification incorrect",
              "Le code de vérification est incorrect ou expiré. Saisissez le code affiché actuellement."),
    ErrorSpec("LOGIN_LOCKED", 429, "Connexion temporairement bloquée",
              "Trop de tentatives de connexion. Patientez quelques minutes avant de réessayer.", WARNING, True),
    ErrorSpec("PASSWORD_CHANGE_REQUIRED", 403, "Mot de passe à renouveler",
              "Vous devez définir un nouveau mot de passe avant de continuer.", INFO),
    ErrorSpec("MFA_REQUIRED", 403, "Double authentification requise",
              "Activez la double authentification sur votre compte pour accéder à cette fonctionnalité.", INFO),
    # --- Autorisations -------------------------------------------------------
    ErrorSpec("FORBIDDEN", 403, "Accès refusé",
              "Vous ne disposez pas des autorisations nécessaires pour accéder à cette page ou effectuer cette opération."),
    ErrorSpec("PERMISSION_DENIED", 403, "Accès refusé",
              "Vous ne disposez pas des autorisations nécessaires pour effectuer cette opération."),
    ErrorSpec("MODULE_FORBIDDEN", 403, "Module non autorisé", "Vous n’avez pas accès à ce module."),
    ErrorSpec("MODULE_UNAVAILABLE", 403, "Module indisponible",
              "Ce module est momentanément indisponible. Réessayez plus tard.", INFO),
    # --- Ressources / concurrence -------------------------------------------
    ErrorSpec("NOT_FOUND", 404, "Élément introuvable",
              "Cette page ou cette ressource est introuvable ou n’est plus disponible.", INFO),
    ErrorSpec("GONE", 410, "Élément retiré", "Cette ressource a été définitivement retirée.", INFO),
    ErrorSpec("METHOD_NOT_ALLOWED", 405, "Action indisponible", "Cette action n’est pas disponible de cette manière."),
    ErrorSpec("CONFLICT", 409, "Conflit de données",
              "Cette information a été modifiée par un autre utilisateur. Actualisez les données avant de réessayer."),
    ErrorSpec("DUPLICATE", 409, "Doublon", "Cette donnée existe déjà."),
    ErrorSpec("DUPLICATE_REQUEST", 409, "Opération déjà en cours",
              "Cette opération est déjà en cours de traitement. Patientez quelques instants.", INFO, True),
    ErrorSpec("CONCURRENT_UPDATE", 409, "Modification simultanée",
              "Une autre opération modifiait les mêmes données au même moment. Actualisez puis réessayez.",
              WARNING, True),
    ErrorSpec("RESOURCE_LOCKED", 409, "Élément en cours de modification",
              "Cet élément est en cours de modification par une autre opération. Réessayez dans quelques instants.",
              WARNING, True),
    ErrorSpec("PRECONDITION_FAILED", 412, "Données obsolètes",
              "Les données affichées ne sont plus à jour. Actualisez la page avant de réessayer."),
    ErrorSpec("REQUEST_TIMEOUT", 408, "Délai dépassé",
              "La demande a pris trop de temps. Vérifiez votre connexion, puis réessayez si nécessaire.", INFO, True),
    ErrorSpec("RATE_LIMITED", 429, "Trop de requêtes",
              "Trop de tentatives ont été effectuées. Patientez quelques instants avant de réessayer.", WARNING, True),
    # --- Serveur / dépendances ----------------------------------------------
    ErrorSpec("INTERNAL_ERROR", 500, "Erreur inattendue",
              "Une erreur inattendue est survenue. Votre demande n’a pas pu être traitée normalement. "
              "Si le problème persiste, contactez le support avec la référence indiquée.", ERROR),
    ErrorSpec("NOT_IMPLEMENTED", 501, "Fonctionnalité indisponible",
              "Cette fonctionnalité n’est pas encore disponible.", WARNING),
    ErrorSpec("BAD_GATEWAY", 502, "Service indisponible",
              "Le service est temporairement indisponible. Réessayez dans quelques instants.", ERROR, True),
    ErrorSpec("SERVICE_UNAVAILABLE", 503, "Service indisponible",
              "Le service est temporairement indisponible. Réessayez dans quelques instants.", ERROR, True),
    ErrorSpec("DATABASE_ERROR", 503, "Service indisponible",
              "La base de données est momentanément indisponible. Réessayez dans quelques instants.", ERROR, True),
    ErrorSpec("DATABASE_BUSY", 503, "Service très sollicité",
              "Le service est très sollicité. Réessayez dans quelques instants.", ERROR, True),
    ErrorSpec("DATABASE_TIMEOUT", 503, "Traitement trop long",
              "Le traitement a pris trop de temps et a été interrompu. Affinez votre recherche ou réessayez plus tard.",
              ERROR, True),
    ErrorSpec("DEPENDENCY_UNAVAILABLE", 503, "Service indisponible",
              "Un service nécessaire à cette opération est momentanément indisponible. Réessayez dans quelques instants.",
              ERROR, True),
    ErrorSpec("GATEWAY_TIMEOUT", 504, "Délai de réponse dépassé",
              "Le service met trop de temps à répondre. Vérifiez le statut de votre opération avant de la relancer.",
              ERROR),
)

CATALOG: dict[str, ErrorSpec] = {s.code: s for s in _SPECS}

# Code transversal par défaut pour un statut HTTP sans code explicite.
STATUS_CODES: dict[int, str] = {
    400: "BUSINESS_RULE_ERROR",
    401: "AUTH_REQUIRED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    406: "NOT_ACCEPTABLE",
    408: "REQUEST_TIMEOUT",
    409: "CONFLICT",
    410: "GONE",
    412: "PRECONDITION_FAILED",
    413: "PAYLOAD_TOO_LARGE",
    414: "URI_TOO_LONG",
    415: "UNSUPPORTED_MEDIA_TYPE",
    416: "RANGE_NOT_SATISFIABLE",
    422: "VALIDATION_ERROR",
    429: "RATE_LIMITED",
    431: "HEADERS_TOO_LARGE",
    500: "INTERNAL_ERROR",
    501: "NOT_IMPLEMENTED",
    502: "BAD_GATEWAY",
    503: "SERVICE_UNAVAILABLE",
    504: "GATEWAY_TIMEOUT",
}

# Titre d'un code métier non catalogué, déduit de son statut.
_TITLE_BY_STATUS: dict[int, str] = {
    400: "Opération impossible",
    401: "Authentification requise",
    403: "Accès refusé",
    404: "Élément introuvable",
    409: "Conflit de données",
    413: "Fichier trop volumineux",
    415: "Format non pris en charge",
    422: "Champs à corriger",
    423: "Élément verrouillé",
    429: "Trop de requêtes",
}


def default_code(status_code: int) -> str:
    if status_code in STATUS_CODES:
        return STATUS_CODES[status_code]
    return "INTERNAL_ERROR" if status_code >= 500 else "BUSINESS_RULE_ERROR"


def spec_for(code: str | None, status_code: int) -> ErrorSpec:
    """Spécification du code (catalogue), sinon celle du code transversal du statut."""
    if code and code in CATALOG:
        return CATALOG[code]
    return CATALOG[default_code(status_code)]


def title_for(code: str | None, status_code: int) -> str:
    if code and code in CATALOG:
        return CATALOG[code].title
    if status_code in _TITLE_BY_STATUS:
        return _TITLE_BY_STATUS[status_code]
    return spec_for(None, status_code).title
