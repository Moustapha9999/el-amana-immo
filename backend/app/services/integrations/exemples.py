"""Exemples de code (cURL, Python httpx, TypeScript fetch) pour une opération documentée.

Les exemples n'utilisent que des espaces réservés : l'URL de base et le jeton sont lus dans
des variables d'environnement, les valeurs de paramètres sont fictives. Aucun mécanisme
d'authentification machine-à-machine n'est supposé : seul le jeton de session existant est montré.
"""

from __future__ import annotations

import json
import re

from app.services.integrations.catalogue import (
    AUTH_LOGIN1,
    AUTH_LOGIN2,
    AUTH_SESSION,
    Operation,
)

BASE_URL_PAR_DEFAUT = "https://bea-digital.exemple.invalid"
VAR_BASE_URL = "BEA_BASE_URL"
VAR_JETON = "BEA_ACCESS_TOKEN"

_PLACEHOLDER = re.compile(r"\{([^}/]+)\}")
_AVERTISSEMENT = (
    "Exemple généré par le Studio d'intégration API BEA DIGITAL — valeurs fictives. "
    "À exécuter uniquement avec un compte et des droits autorisés pour cette opération."
)


def _auth_texte(op: Operation) -> str:
    if op.authentification == AUTH_LOGIN1:
        return "Session BEA DIGITAL (Login 1) : jeton obtenu par POST /api/v1/auth/login."
    if op.authentification == AUTH_LOGIN2:
        module = op.module_code or "<module>"
        if module == "demandes":
            return (
                "Session module Demandes (Login 2) : jeton obtenu par POST /api/v1/auth/modules/<module>/login "
                "avec une session Login 1 active."
            )
        return (
            f"Session module « {module} » (Login 2) : jeton obtenu par POST /api/v1/auth/modules/{module}/login "
            "avec une session Login 1 active."
        )
    if op.authentification == AUTH_SESSION:
        return "Session BEA DIGITAL (Login 1) ou session module (Login 2) : jeton de session en cours."
    return ""


def prerequis(op: Operation) -> list[str]:
    items = [_auth_texte(op)]
    if op.permissions:
        items.append("Permission requise (au moins une) : " + ", ".join(op.permissions) + ".")
    items.append(f"Définir {VAR_BASE_URL} (URL de l'environnement visé) et {VAR_JETON} (jeton de session).")
    items.append("Ne jamais écrire un jeton, un mot de passe ou une donnée bancaire réelle dans le code.")
    return items


def _chemin_exemple(op: Operation) -> str:
    return _PLACEHOLDER.sub(lambda m: f"<{m.group(1)}>", op.chemin)


def _valeur_fictive(type_label: str, nom: str) -> object:
    t = type_label.lower()
    if t.startswith("integer"):
        return 1
    if t.startswith("number"):
        return 0
    if t.startswith("boolean"):
        return False
    if t.startswith("liste"):
        return []
    if t.startswith("dictionnaire") or t == "object":
        return {}
    return f"<{nom}>"


def _requete(op: Operation) -> dict[str, object]:
    return {
        p["nom"]: _valeur_fictive(p["type"], p["nom"])
        for p in op.parametres
        if p["emplacement"] == "query" and p["requis"]
    }


def _corps(op: Operation) -> dict[str, object] | None:
    if not op.corps or op.corps.get("type_contenu") != "application/json":
        return None
    return {c["nom"]: _valeur_fictive(c["type"], c["nom"]) for c in op.corps["champs"] if c["requis"]}


def _query_string(params: dict[str, object]) -> str:
    if not params:
        return ""
    parts = []
    for key, value in params.items():
        text = json.dumps(value) if not isinstance(value, str) else value
        parts.append(f"{key}={text}")
    return "?" + "&".join(parts)


def _optionnels(op: Operation) -> list[str]:
    return [p["nom"] for p in op.parametres if p["emplacement"] == "query" and not p["requis"]]


def _curl(op: Operation) -> str:
    chemin = _chemin_exemple(op) + _query_string(_requete(op))
    corps = _corps(op)
    lignes = [
        f"# {_AVERTISSEMENT}",
        f"# {_auth_texte(op)}",
        f'BASE_URL="${{{VAR_BASE_URL}:-{BASE_URL_PAR_DEFAUT}}}"',
        f'curl -sS -X {op.methode} "$BASE_URL{chemin}" \\',
        f'  -H "Authorization: Bearer ${VAR_JETON}" \\',
    ]
    if corps is not None:
        lignes.append('  -H "Content-Type: application/json" \\')
        lignes.append(f"  -d '{json.dumps(corps, ensure_ascii=False)}' \\")
    lignes.append('  -H "Accept: application/json"')
    optionnels = _optionnels(op)
    if optionnels:
        lignes.append(f"# Paramètres optionnels : {', '.join(optionnels)}")
    return "\n".join(lignes)


def _python(op: Operation) -> str:
    params = _requete(op)
    corps = _corps(op)
    lignes = [
        f'"""{_AVERTISSEMENT}',
        "",
        _auth_texte(op),
        '"""',
        "import os",
        "",
        "import httpx",
        "",
        f'BASE_URL = os.environ.get("{VAR_BASE_URL}", "{BASE_URL_PAR_DEFAUT}")',
        f'ACCESS_TOKEN = os.environ["{VAR_JETON}"]',
        "",
        "response = httpx.request(",
        f'    "{op.methode}",',
        f'    f"{{BASE_URL}}{_chemin_exemple(op)}",',
    ]
    if params:
        lignes.append(f"    params={params!r},")
    if corps is not None:
        lignes.append(f"    json={corps!r},")
    lignes += [
        '    headers={"Authorization": f"Bearer {ACCESS_TOKEN}", "Accept": "application/json"},',
        "    timeout=30.0,",
        ")",
        "response.raise_for_status()",
        "print(response.json())",
    ]
    return "\n".join(lignes)


def _typescript(op: Operation) -> str:
    params = _requete(op)
    corps = _corps(op)
    query = ""
    lignes = [
        f"// {_AVERTISSEMENT}",
        f"// {_auth_texte(op)}",
        f"const BASE_URL = process.env.{VAR_BASE_URL} ?? '{BASE_URL_PAR_DEFAUT}';",
        f"const ACCESS_TOKEN = process.env.{VAR_JETON};",
        "if (!ACCESS_TOKEN) throw new Error('" + VAR_JETON + " manquant');",
        "",
    ]
    if params:
        lignes.append(
            "const params = new URLSearchParams("
            + json.dumps({k: str(v) if not isinstance(v, str) else v for k, v in params.items()}, ensure_ascii=False)
            + ");"
        )
        query = "?${params}"
    lignes += [
        f"const response = await fetch(`${{BASE_URL}}{_chemin_exemple(op)}{query}`, {{",
        f"  method: '{op.methode}',",
        "  headers: {",
        "    Authorization: `Bearer ${ACCESS_TOKEN}`,",
        "    Accept: 'application/json',",
    ]
    if corps is not None:
        lignes.append("    'Content-Type': 'application/json',")
    lignes.append("  },")
    if corps is not None:
        lignes.append(f"  body: JSON.stringify({json.dumps(corps, ensure_ascii=False)}),")
    lignes += [
        "});",
        "if (!response.ok) throw new Error(`HTTP ${response.status}`);",
        "console.log(await response.json());",
    ]
    return "\n".join(lignes)


def generer(op: Operation) -> dict:
    base = {"operation_id": op.operation_id, "authentification": op.authentification}
    if not op.exemples_disponibles:
        motif = "; ".join(op.motifs) or "Opération non documentée."
        return {**base, "disponible": False, "motif": motif, "prerequis": [], "exemples": []}
    return {
        **base,
        "disponible": True,
        "motif": None,
        "prerequis": prerequis(op),
        "exemples": [
            {"langage": "curl", "libelle": "cURL", "code": _curl(op)},
            {"langage": "python", "libelle": "Python (httpx)", "code": _python(op)},
            {"langage": "typescript", "libelle": "TypeScript (fetch)", "code": _typescript(op)},
        ],
    }
