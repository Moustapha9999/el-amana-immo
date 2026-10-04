"""Conditions déclaratives des règles EER (JSON), évaluées sans exécuter de code.

Forme :
    {"fact": "type_client", "op": "in", "value": ["PM_PRIVEE", "PM_PUBLIQUE"]}
    {"all": [...]}, {"any": [...]}, {"not": {...}}
Une condition absente (None) est toujours vraie. Un fait inconnu rend la feuille fausse
(sauf ``exists`` qui teste justement sa présence).
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import Any

OPERATEURS = frozenset({"eq", "ne", "in", "not_in", "gt", "gte", "lt", "lte", "exists"})
COMBINATEURS = frozenset({"all", "any", "not"})
PROFONDEUR_MAX = 8

_ABSENT = object()


class ConditionInvalide(ValueError):
    """Structure de condition refusée (saisie paramétrage)."""


def valider(condition: Any, *, _profondeur: int = 0) -> None:
    if condition is None:
        return
    if _profondeur > PROFONDEUR_MAX:
        raise ConditionInvalide("Condition trop imbriquée")
    if not isinstance(condition, Mapping):
        raise ConditionInvalide("Une condition doit être un objet")
    cles = set(condition)
    combinateurs = cles & COMBINATEURS
    if combinateurs:
        if len(cles) != 1:
            raise ConditionInvalide("Un combinateur doit être seul dans son objet")
        cle = next(iter(combinateurs))
        valeur = condition[cle]
        if cle == "not":
            valider(valeur, _profondeur=_profondeur + 1)
            return
        if not isinstance(valeur, list) or not valeur:
            raise ConditionInvalide(f"« {cle} » attend une liste non vide")
        for sous in valeur:
            valider(sous, _profondeur=_profondeur + 1)
        return
    if "fact" not in condition or "op" not in condition:
        raise ConditionInvalide("Feuille attendue : fact + op (+ value)")
    if cles - {"fact", "op", "value"}:
        raise ConditionInvalide(f"Clés inconnues : {sorted(cles - {'fact', 'op', 'value'})}")
    if not isinstance(condition["fact"], str) or not condition["fact"]:
        raise ConditionInvalide("« fact » doit être un nom de fait")
    op = condition["op"]
    if op not in OPERATEURS:
        raise ConditionInvalide(f"Opérateur inconnu : {op}")
    if op != "exists" and "value" not in condition:
        raise ConditionInvalide(f"« {op} » attend une valeur")
    if op in {"in", "not_in"} and not isinstance(condition.get("value"), list):
        raise ConditionInvalide(f"« {op} » attend une liste")


def _nombre(valeur: Any) -> Decimal | None:
    if isinstance(valeur, bool) or valeur is None:
        return None
    try:
        return Decimal(str(valeur))
    except (InvalidOperation, ValueError):
        return None


def _feuille(condition: Mapping[str, Any], faits: Mapping[str, Any]) -> bool:
    fait = faits.get(condition["fact"], _ABSENT)
    op = condition["op"]
    if op == "exists":
        attendu = condition.get("value", True)
        present = fait is not _ABSENT and fait is not None and fait != ""
        return present is bool(attendu)
    if fait is _ABSENT or fait is None:
        return False
    valeur = condition.get("value")
    if op == "eq":
        return fait == valeur
    if op == "ne":
        return fait != valeur
    if op == "in":
        return fait in valeur
    if op == "not_in":
        return fait not in valeur
    a, b = _nombre(fait), _nombre(valeur)
    if a is None or b is None:
        return False
    return {"gt": a > b, "gte": a >= b, "lt": a < b, "lte": a <= b}[op]


def evaluer(condition: Any, faits: Mapping[str, Any]) -> bool:
    if condition is None:
        return True
    if "all" in condition:
        return all(evaluer(c, faits) for c in condition["all"])
    if "any" in condition:
        return any(evaluer(c, faits) for c in condition["any"])
    if "not" in condition:
        return not evaluer(condition["not"], faits)
    return _feuille(condition, faits)


def _decrire(condition: Mapping[str, Any]) -> str:
    op = condition["op"]
    if op == "exists":
        return f"{condition['fact']} renseigné" if condition.get("value", True) else f"{condition['fact']} absent"
    return f"{condition['fact']} {op} {condition.get('value')!r}"


def expliquer(condition: Any, faits: Mapping[str, Any]) -> list[str]:
    """Feuilles vérifiées qui rendent la condition vraie (pour « pourquoi cet élément ? »)."""
    if condition is None or not evaluer(condition, faits):
        return []
    if "all" in condition:
        return [d for c in condition["all"] for d in expliquer(c, faits)]
    if "any" in condition:
        return next((expliquer(c, faits) for c in condition["any"] if evaluer(c, faits)), [])
    if "not" in condition:
        return [f"non ({', '.join(_decrire(f) for f in _feuilles(condition['not']))})"]
    return [_decrire(condition)]


def _feuilles(condition: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    for cle in ("all", "any"):
        if cle in condition:
            return [f for c in condition[cle] for f in _feuilles(c)]
    if "not" in condition:
        return _feuilles(condition["not"])
    return [condition]
