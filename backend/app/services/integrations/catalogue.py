"""Catalogue des opérations construit à partir des routes FastAPI réellement enregistrées.

Aucune information n'est inventée : l'authentification et les permissions proviennent des
dépendances connues de ``app.api.deps`` ; les paramètres et schémas proviennent du schéma
OpenAPI généré par FastAPI. Ce qui ne peut pas être établi est signalé comme tel.
"""

from __future__ import annotations

import hashlib
import inspect
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, get_args, get_origin

from fastapi import FastAPI
from fastapi.routing import APIRoute
from pydantic import BaseModel

from app.data.plateforme_catalogue import FUNCTIONAL_PERMISSIONS

PERMISSIONS_CONNUES = frozenset(code for code, _label, _module in FUNCTIONAL_PERMISSIONS)

AUTH_LOGIN1 = "login1"
AUTH_LOGIN2 = "login2"
AUTH_SESSION = "login1_ou_login2"
AUTH_INDETERMINEE = "indeterminee"
AUTH_AUCUNE = "aucune_detectee"

PERM_IDENTIFIEE = "identifiee"
PERM_NON_DETERMINEE = "non_determinee"
PERM_NON_VERIFIEE = "non_verifiee"

SCHEMA_EXPLICITE = "explicite"
SCHEMA_GENERIQUE = "generique"
SCHEMA_ABSENT = "absent"

DISPO_DOCUMENTEE = "documentee"
DISPO_RESTREINTE = "restreinte"
DISPO_EXCLUE = "exclue"

EXCLUSION_MASQUEE = "masquee"
EXCLUSION_AUTH = "authentification"
EXCLUSION_INFRA = "infrastructure"
EXCLUSION_ADMIN = "administration"

MOTIFS_EXCLUSION = {
    EXCLUSION_MASQUEE: "Route masquée du schéma OpenAPI (include_in_schema=False) : non exposable.",
    EXCLUSION_AUTH: "Route d'authentification (Login 1 / Login 2, 2FA, mots de passe) : non exposable.",
    EXCLUSION_INFRA: "Route technique (santé, version) hors API métier : non exposable.",
    EXCLUSION_ADMIN: "Route d'administration CORE ADMIN : non exposable à une application cliente.",
}

AVERTISSEMENT = (
    "Ce catalogue décrit les routes réellement enregistrées dans le backend. Il ne constitue pas une "
    "autorisation : une opération documentée n'est pas pour autant ouverte à une application externe. "
    "Une permission « identifiée » est celle exigée par les dépendances FastAPI de la route : elle est "
    "nécessaire, pas forcément suffisante (les services peuvent restreindre par périmètre, propriétaire "
    "ou état métier)."
)

_CONTROLE_CORPS = re.compile(
    r"HTTP_403|status_code\s*=\s*403|\bForbidden\w*|PermissionDenied|\buser_has_permission\w*\(|\bhas_permission\w*\("
    r"|\bpermission_codes\b|\bis_superuser\b|\b_?require_\w+\(|\bscope\b|\bp[eé]rim[eè]tre\b"
)

API_PREFIX = "/api/v1"
_DEPS_MODULE = "app.api.deps"
_NEUTRAL_CALLS = {("app.db.session", "get_db")}
_SENSITIVE_NAME = re.compile(r"pass|secret|token|jeton|key|cle|otp|totp|iban|rib|email|phone|tel", re.I)
_MAX_CHAMPS = 80
_MAX_DESCRIPTION = 1200
_METHODES = ("GET", "POST", "PUT", "PATCH", "DELETE")


@dataclass
class Operation:
    operation_id: str
    nom: str
    methode: str
    chemin: str
    route: APIRoute = field(repr=False)
    module: str
    module_code: str | None
    authentification: str
    permissions: list[str]
    exigences: list[list[str]]
    permission_statut: str
    dependances_non_analysees: list[str]
    schema_reponse_statut: str
    dans_openapi: bool
    categorie_exclusion: str | None
    motifs: list[str]
    disponibilite: str
    resume: str | None
    description: str | None
    parametres: list[dict]
    corps: dict | None
    reponses: list[dict]

    @property
    def exemples_disponibles(self) -> bool:
        return self.disponibilite == DISPO_DOCUMENTEE


@dataclass
class _Analyse:
    login1: bool = False
    session: bool = False
    bearer: bool = False
    module_code: str | None = None
    demandes: bool = False
    permissions: list[str] = field(default_factory=list)
    groupes: list[list[str]] = field(default_factory=list)
    inconnues: list[str] = field(default_factory=list)


def _closure_vars(fn: Any) -> dict[str, Any]:
    code = getattr(fn, "__code__", None)
    cells = getattr(fn, "__closure__", None) or ()
    if code is None:
        return {}
    return {name: cell.cell_contents for name, cell in zip(code.co_freevars, cells)}


def _call_label(call: Any) -> str:
    module = getattr(call, "__module__", "") or ""
    qual = getattr(call, "__qualname__", None) or type(call).__name__
    short = module.rsplit(".", 1)[-1] if module else ""
    return f"{short}.{qual}".replace(".<locals>", "") if short else qual


def _analyse_dependances(dependant: Any, out: _Analyse) -> None:
    for sub in dependant.dependencies:
        call = sub.call
        module = getattr(call, "__module__", "") or ""
        qual = getattr(call, "__qualname__", "") or ""
        if type(call).__name__ == "HTTPBearer":
            out.bearer = True
        elif module == _DEPS_MODULE and qual == "get_platform_user":
            out.login1 = True
        elif module == _DEPS_MODULE and qual == "get_current_user":
            out.session = True
        elif module == _DEPS_MODULE and qual.startswith(("require_platform_permission.", "require_permission.")):
            if qual.startswith("require_platform_permission."):
                out.login1 = True
            codes = list(_closure_vars(call).get("permission_codes", ()))
            out.permissions.extend(codes)
            if codes and sorted(codes) not in out.groupes:
                out.groupes.append(sorted(codes))
        elif module == _DEPS_MODULE and qual.startswith("require_module_access."):
            out.module_code = _closure_vars(call).get("module_code") or out.module_code
        elif module == _DEPS_MODULE and qual.startswith("require_demandes_module."):
            out.demandes = True
        elif (module, qual) in _NEUTRAL_CALLS:
            pass
        elif module.startswith("app."):
            out.inconnues.append(_call_label(call))
        _analyse_dependances(sub, out)


def _controles_corps(endpoint: Any) -> list[str]:
    """Marqueurs de contrôle d'accès dans le corps de l'endpoint (hors signature) ; heuristique prudente."""
    try:
        lignes = inspect.getsource(endpoint).splitlines()
    except (OSError, TypeError):
        return ["source indisponible"]
    debut = next((i + 1 for i, ligne in enumerate(lignes) if re.search(r"\)\s*(->.*)?:\s*$", ligne)), 0)
    corps = "\n".join(lignes[debut:])
    return sorted({m.group(0).rstrip("(") for m in _CONTROLE_CORPS.finditer(corps)})


def exigence_texte(exigences: list[list[str]]) -> str | None:
    """Logique réelle : au moins un code par dépendance, toutes les dépendances requises."""
    if not exigences:
        return None
    parts = [g[0] if len(g) == 1 else "au moins une de (" + ", ".join(g) + ")" for g in exigences]
    return " ET ".join(parts)


def _schema_statut(response_model: Any) -> str:
    if response_model is None:
        return SCHEMA_ABSENT
    return SCHEMA_EXPLICITE if _est_type_precis(response_model) else SCHEMA_GENERIQUE


def _est_type_precis(tp: Any) -> bool:
    if tp in (Any, dict, list, object, None):
        return False
    if isinstance(tp, type) and issubclass(tp, BaseModel):
        return True
    origin = get_origin(tp)
    args = get_args(tp)
    if origin is dict:
        return len(args) == 2 and _est_type_precis(args[1])
    if args:
        return all(_est_type_precis(a) or a is type(None) for a in args)
    return isinstance(tp, type)


def _exclusion(route: APIRoute) -> str | None:
    path = route.path
    if not route.include_in_schema:
        return EXCLUSION_MASQUEE
    if not path.startswith(API_PREFIX + "/"):
        return EXCLUSION_INFRA
    if path.startswith(f"{API_PREFIX}/auth/"):
        return EXCLUSION_AUTH
    if path.startswith(f"{API_PREFIX}/plateforme/admin/") or path == f"{API_PREFIX}/plateforme/admin":
        return EXCLUSION_ADMIN
    return None


def _domaine(route: APIRoute) -> str:
    if route.tags:
        return str(route.tags[0])
    rest = route.path[len(API_PREFIX):] if route.path.startswith(API_PREFIX) else route.path
    segment = rest.strip("/").split("/", 1)[0]
    return segment or "racine"


def _base_id(methode: str, route: APIRoute) -> str:
    module = (getattr(route.endpoint, "__module__", "") or "").rsplit(".", 1)[-1]
    name = getattr(route.endpoint, "__name__", "") or route.name
    return f"{methode.lower()}.{module}.{name}"


def _description(route: APIRoute) -> str | None:
    text = (route.description or "").strip()
    if not text:
        return None
    return text[:_MAX_DESCRIPTION]


# --- OpenAPI -----------------------------------------------------------------------------


def _ref_name(ref: str) -> str:
    return ref.rsplit("/", 1)[-1]


def _resolve(schema: dict | None, components: dict) -> dict:
    seen = 0
    while isinstance(schema, dict) and "$ref" in schema and seen < 5:
        schema = components.get(_ref_name(schema["$ref"]), {})
        seen += 1
    return schema or {}


def _type_label(schema: dict | None) -> str:
    if not isinstance(schema, dict) or not schema:
        return "non précisé"
    if "$ref" in schema:
        return _ref_name(schema["$ref"])
    for key in ("anyOf", "oneOf"):
        if key in schema:
            parts = [_type_label(s) for s in schema[key]]
            return " | ".join(dict.fromkeys(parts))
    if "allOf" in schema and len(schema["allOf"]) == 1:
        return _type_label(schema["allOf"][0])
    kind = schema.get("type")
    if kind == "array":
        return f"liste de {_type_label(schema.get('items'))}"
    if kind == "object" and "additionalProperties" in schema and isinstance(schema["additionalProperties"], dict):
        return f"dictionnaire de {_type_label(schema['additionalProperties'])}"
    if kind:
        fmt = schema.get("format")
        return f"{kind} ({fmt})" if fmt else str(kind)
    if "enum" in schema:
        return "énumération"
    return "non précisé"


def _schema_nom(schema: dict | None) -> str | None:
    if not isinstance(schema, dict):
        return None
    if "$ref" in schema:
        return _ref_name(schema["$ref"])
    if schema.get("type") == "array" and isinstance(schema.get("items"), dict) and "$ref" in schema["items"]:
        return f"liste de {_ref_name(schema['items']['$ref'])}"
    return None


def _champs(schema: dict | None, components: dict) -> list[dict]:
    target = _resolve(schema, components)
    if target.get("type") == "array":
        target = _resolve(target.get("items"), components)
    props = target.get("properties") or {}
    required = set(target.get("required") or [])
    out = []
    for name, prop in list(props.items())[:_MAX_CHAMPS]:
        desc = prop.get("description") if isinstance(prop, dict) else None
        out.append({"nom": name, "type": _type_label(prop), "requis": name in required, "description": desc})
    return out


def _defaut_sur(name: str, value: Any) -> Any:
    if value is None or isinstance(value, bool | int | float):
        return value
    if isinstance(value, str) and len(value) <= 40 and not _SENSITIVE_NAME.search(name):
        return value
    return None


def _valeurs(schema: dict) -> list[str]:
    enum = schema.get("enum")
    if not enum:
        for key in ("anyOf", "oneOf"):
            for sub in schema.get(key, []) or []:
                if isinstance(sub, dict) and sub.get("enum"):
                    enum = sub["enum"]
                    break
    if not enum:
        return []
    return [str(v) for v in enum[:30]]


def _parametres(op: dict) -> list[dict]:
    out = []
    for param in op.get("parameters") or []:
        schema = param.get("schema") or {}
        name = str(param.get("name"))
        out.append(
            {
                "nom": name,
                "emplacement": str(param.get("in")),
                "requis": bool(param.get("required")),
                "type": _type_label(schema),
                "description": param.get("description") or schema.get("description"),
                "defaut": _defaut_sur(name, schema.get("default")),
                "valeurs": _valeurs(schema),
            }
        )
    return out


def _corps(op: dict, components: dict) -> dict | None:
    body = op.get("requestBody")
    if not isinstance(body, dict):
        return None
    content = body.get("content") or {}
    if not content:
        return None
    type_contenu, media = next(iter(content.items()))
    schema = (media or {}).get("schema")
    return {
        "type_contenu": type_contenu,
        "requis": bool(body.get("required")),
        "schema_nom": _schema_nom(schema),
        "champs": _champs(schema, components),
    }


def _reponses(op: dict, components: dict, *, typed: bool) -> list[dict]:
    out = []
    for code, rep in (op.get("responses") or {}).items():
        content = (rep or {}).get("content") or {}
        media = content.get("application/json") or {}
        schema = media.get("schema")
        documented = bool(schema) and (typed or not str(code).startswith("2"))
        out.append(
            {
                "code": str(code),
                "description": (rep or {}).get("description"),
                "schema_nom": _schema_nom(schema) if documented else None,
                "champs": _champs(schema, components) if documented else [],
            }
        )
    return out


# --- Construction ------------------------------------------------------------------------


def _authentification(a: _Analyse) -> str:
    if a.module_code or a.demandes:
        return AUTH_LOGIN2
    if a.login1:
        return AUTH_LOGIN1
    if a.session:
        return AUTH_SESSION
    if a.bearer or a.inconnues:
        return AUTH_INDETERMINEE
    return AUTH_AUCUNE


def _permission_statut(auth: str, a: _Analyse) -> str:
    if auth in (AUTH_AUCUNE, AUTH_INDETERMINEE):
        return PERM_NON_VERIFIEE
    if a.permissions and not a.inconnues:
        return PERM_IDENTIFIEE
    return PERM_NON_DETERMINEE


def _motifs(op: Operation, doublon: bool) -> list[str]:
    motifs: list[str] = []
    absentes = [code for code in op.permissions if code not in PERMISSIONS_CONNUES]
    if absentes:
        motifs.append("Permission(s) exigée(s) par le code mais absente(s) du référentiel : " + ", ".join(absentes) + ".")
    if op.schema_reponse_statut == SCHEMA_ABSENT:
        motifs.append("Aucun schéma de réponse déclaré (pas de response_model) : réponse non documentée.")
    elif op.schema_reponse_statut == SCHEMA_GENERIQUE:
        motifs.append("Schéma de réponse générique (dict / Any) : structure de la réponse non documentée.")
    if op.authentification == AUTH_AUCUNE:
        motifs.append("Aucune dépendance d'authentification détectée : accès non vérifié.")
    elif op.authentification == AUTH_INDETERMINEE:
        motifs.append("Authentification réalisée par une dépendance ou un traitement non analysé : non déterminée.")
    if op.permission_statut == PERM_NON_DETERMINEE:
        corps = [d for d in op.dependances_non_analysees if d.startswith("corps de l'endpoint")]
        deps = [d for d in op.dependances_non_analysees if d not in corps]
        if deps:
            motifs.append("Permission non déterminée : contrôle par dépendance propre au module (" + ", ".join(deps) + ").")
        if corps:
            motifs.append(
                "Permission non déterminée : contrôle d'accès supplémentaire dans le traitement ("
                + ", ".join(d.split(" : ", 1)[1] for d in corps)
                + ")."
            )
        if not op.dependances_non_analysees:
            motifs.append("Aucune permission déclarée dans les dépendances : permission non déterminée.")
    if op.corps and op.corps.get("type_contenu") != "application/json":
        motifs.append("Corps de requête non JSON (ex. envoi de fichier) : exemple de code non généré.")
    if not op.dans_openapi:
        motifs.append("Opération absente du schéma OpenAPI généré.")
    if doublon:
        motifs.append("Plusieurs routes partagent cette méthode et ce chemin : seule la première est atteignable.")
    return motifs


def construire_operations(app: FastAPI) -> list[Operation]:
    spec = app.openapi()
    paths = spec.get("paths") or {}
    components = (spec.get("components") or {}).get("schemas") or {}

    brut: list[tuple[str, APIRoute]] = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        for methode in sorted(m for m in route.methods or () if m in _METHODES):
            brut.append((methode, route))

    ids = Counter(_base_id(m, r) for m, r in brut)
    chemins = Counter((m, r.path) for m, r in brut)
    operations: list[Operation] = []
    for methode, route in brut:
        base = _base_id(methode, route)
        operation_id = base
        if ids[base] > 1:
            operation_id = f"{base}.{hashlib.sha1(route.path.encode()).hexdigest()[:8]}"

        analyse = _Analyse()
        _analyse_dependances(route.dependant, analyse)
        analyse.inconnues.extend(f"corps de l'endpoint : {m}" for m in _controles_corps(route.endpoint))
        auth = _authentification(analyse)
        module_code = analyse.module_code or ("demandes" if analyse.demandes else None)
        schema_statut = _schema_statut(route.response_model)
        openapi_op = (paths.get(route.path) or {}).get(methode.lower())
        exclusion = _exclusion(route)
        detail = openapi_op or {}

        op = Operation(
            operation_id=operation_id,
            nom=route.name,
            methode=methode,
            chemin=route.path,
            route=route,
            module=module_code or _domaine(route),
            module_code=module_code,
            authentification=auth,
            permissions=sorted(dict.fromkeys(analyse.permissions)),
            exigences=analyse.groupes,
            permission_statut=_permission_statut(auth, analyse),
            dependances_non_analysees=sorted(dict.fromkeys(analyse.inconnues)),
            schema_reponse_statut=schema_statut,
            dans_openapi=openapi_op is not None,
            categorie_exclusion=exclusion,
            motifs=[],
            disponibilite=DISPO_EXCLUE,
            resume=route.summary,
            description=_description(route),
            parametres=_parametres(detail),
            corps=_corps(detail, components),
            reponses=_reponses(detail, components, typed=schema_statut == SCHEMA_EXPLICITE),
        )
        if exclusion is not None:
            op.motifs = [MOTIFS_EXCLUSION[exclusion]]
            op.disponibilite = DISPO_EXCLUE
        else:
            op.motifs = _motifs(op, doublon=chemins[(methode, route.path)] > 1)
            op.disponibilite = DISPO_RESTREINTE if op.motifs else DISPO_DOCUMENTEE
        operations.append(op)
    return operations


def detail_expose(op: Operation) -> dict:
    """Détail montré dans la fiche : rien au-delà de l'identité et du motif pour une route exclue."""
    if op.disponibilite == DISPO_EXCLUE:
        return {"resume": None, "description": None, "parametres": [], "corps": None, "reponses": []}
    return {
        "resume": op.resume,
        "description": op.description,
        "parametres": op.parametres,
        "corps": op.corps,
        "reponses": op.reponses,
    }


_CACHE: dict[int, tuple[list[Operation], dict[str, Operation]]] = {}


def operations_de(app: FastAPI) -> tuple[list[Operation], dict[str, Operation]]:
    """Catalogue mis en cache par application : les routes ne changent pas après le démarrage."""
    key = id(app)
    cached = _CACHE.get(key)
    if cached is None:
        ops = construire_operations(app)
        cached = (ops, {op.operation_id: op for op in ops})
        _CACHE[key] = cached
    return cached


def vider_cache() -> None:
    _CACHE.clear()


def kpis(operations: list[Operation], console_ids: set[str]) -> dict:
    par = defaultdict(Counter)
    for op in operations:
        par["methode"][op.methode] += 1
        par["auth"][op.authentification] += 1
        par["perm"][op.permission_statut] += 1
        par["schema"][op.schema_reponse_statut] += 1
        par["dispo"][op.disponibilite] += 1
    return {
        "total": len(operations),
        "documentees": par["dispo"][DISPO_DOCUMENTEE],
        "restreintes": par["dispo"][DISPO_RESTREINTE],
        "exclues": par["dispo"][DISPO_EXCLUE],
        "console": sum(1 for op in operations if op.operation_id in console_ids),
        "par_methode": dict(par["methode"]),
        "par_authentification": dict(par["auth"]),
        "par_permission_statut": dict(par["perm"]),
        "par_schema_reponse": dict(par["schema"]),
    }


def filtrer(
    operations: list[Operation],
    *,
    module: str | None = None,
    methode: str | None = None,
    authentification: str | None = None,
    permission_statut: str | None = None,
    schema_reponse: str | None = None,
    permission: str | None = None,
    disponibilite: str | None = None,
    console_ids: set[str] | None = None,
    console: bool | None = None,
    recherche: str | None = None,
) -> list[Operation]:
    terme = (recherche or "").strip().lower()
    perm = (permission or "").strip().lower()
    out = []
    for op in operations:
        if module and op.module != module:
            continue
        if methode and op.methode != methode.upper():
            continue
        if authentification and op.authentification != authentification:
            continue
        if permission_statut and op.permission_statut != permission_statut:
            continue
        if schema_reponse and op.schema_reponse_statut != schema_reponse:
            continue
        if perm and not any(perm in code.lower() for code in op.permissions):
            continue
        if disponibilite and op.disponibilite != disponibilite:
            continue
        if console is not None and (op.operation_id in (console_ids or set())) != console:
            continue
        if terme:
            resume = detail_expose(op)["resume"] or ""
            haystack = " ".join([op.operation_id, op.nom, op.chemin, op.module, *(op.permissions), resume]).lower()
            if terme not in haystack:
                continue
        out.append(op)
    return out
