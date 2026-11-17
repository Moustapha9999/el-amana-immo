"""Seed des règles de correspondance — toujours ``A_VALIDER``, idempotent.

Source primaire : fichier SCD ``Correspondance_BAL_SM_*.xlsx`` (onglet Correspondance).
Aucune activation automatique. Les règles ``ACTIVE`` / ``REJECTED`` existantes ne sont
jamais réécrites par ce seed.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.models.reporting_bcm_sm import RbcmMappingRule, RbcmMappingRuleSource, RbcmMappingVersion

_BASIS_MAP = {
    "SD": "SD",
    "SC": "SC",
    "D": "D",
    "C": "C",
    "SIGNED": "SIGNED",
}

SOURCE_NAME = "CORRESPONDANCE_SCD"


def _norm_compte(raw: Any) -> str | None:
    if raw is None or raw == "":
        return None
    if isinstance(raw, float) and raw == int(raw):
        return str(int(raw))
    if isinstance(raw, int):
        return str(raw)
    s = str(raw).strip()
    return s or None


def _norm_code(raw: Any) -> str:
    if raw is None or raw == "":
        return ""
    if isinstance(raw, float) and raw == int(raw):
        return str(int(raw))
    if isinstance(raw, int):
        return str(raw)
    return str(raw).strip()


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def business_key(r: dict) -> tuple:
    excl = tuple(sorted(r.get("exclusions") or []))
    return (
        r["cell_ref"],
        r["match_type"],
        r["pattern"],
        r["amount_basis"],
        int(r["sign_multiplier"]),
        excl,
    )


def parse_correspondance_xlsx(path: Path) -> list[dict]:
    """Parse brut : une entrée par ligne Excel exploitable (compte numérique)."""
    wb = load_workbook(path, read_only=True, data_only=True)
    ws = wb["Correspondance"] if "Correspondance" in wb.sheetnames else wb.active
    rules: list[dict] = []
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i < 4:
            continue
        cells = list(row)
        if not cells or all(c is None or c == "" for c in cells[:10]):
            continue
        compte = _norm_compte(cells[1] if len(cells) > 1 else None)
        if not compte or not compte[0].isdigit():
            continue
        base_raw = str(cells[5]).strip().upper() if len(cells) > 5 and cells[5] is not None else ""
        sens = cells[6] if len(cells) > 6 else None
        try:
            sign = int(sens) if sens is not None else 1
        except (TypeError, ValueError):
            sign = 1
        if sign not in (-1, 1):
            sign = 1
        code_bcm = _norm_code(cells[8] if len(cells) > 8 else None)
        rubrique = str(cells[9]).strip() if len(cells) > 9 and cells[9] is not None else ""
        colonne_sm = str(cells[10]).strip() if len(cells) > 10 and cells[10] is not None else None
        cle_ctrl = _norm_code(cells[11]) if len(cells) > 11 else ""

        match_type = "EXACT"
        pattern = compte
        exclusions: list[str] = []
        anomalies: list[str] = []
        if compte.endswith("*") or compte.endswith("%"):
            match_type = "PREFIX"
            pattern = compte.rstrip("*%")
            anomalies.append("PREFIX_MARKED_IN_SOURCE")
        if not code_bcm:
            anomalies.append("CODE_BCM_ABSENT")
        if not base_raw:
            anomalies.append("BASE_ABSENTE")
        elif base_raw not in _BASIS_MAP:
            anomalies.append(f"BASE_INCONNUE:{base_raw}")
        if not rubrique:
            anomalies.append("RUBRIQUE_ABSENTE")

        cell_ref = f"BCM:{code_bcm}" if code_bcm else f"ROW:{i + 1}"
        entry = {
            "source_id": f"CORR-R{i + 1}",
            "excel_row": i + 1,
            "cell_ref": cell_ref,
            "code_bcm": code_bcm or None,
            "match_type": match_type,
            "pattern": pattern,
            "exclusions": exclusions,
            "amount_basis": _BASIS_MAP.get(base_raw, base_raw or "SD"),
            "signed_balance_mode": "NATURAL",
            "sign_multiplier": sign,
            "priority": 100,
            "provenance": "CORRESPONDANCE",
            "lifecycle_status": "A_VALIDER",
            "notes": rubrique or None,
            "anomalies": anomalies,
            "source_payload": {
                "row": i + 1,
                "classe": str(cells[0]).strip() if cells[0] is not None else None,
                "libelle": str(cells[2]).strip() if len(cells) > 2 and cells[2] is not None else None,
                "code_bcm": code_bcm,
                "rubrique": rubrique,
                "base_raw": base_raw,
                "colonne_sm": colonne_sm,
                "cle_controle": cle_ctrl or None,
            },
        }
        entry["rule_key"] = "|".join(str(x) for x in business_key(entry))
        rules.append(entry)
    wb.close()
    return rules


def dedupe_business_rules(raw_rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """Regroupe les lignes Excel en règles métier uniques (clé business_key)."""
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in raw_rows:
        groups[r["rule_key"]].append(r)
    unique: list[dict] = []
    duplicate_groups: list[dict] = []
    for key, group in groups.items():
        primary = dict(group[0])
        primary["source_ids"] = [g["source_id"] for g in group]
        primary["excel_rows"] = [g["excel_row"] for g in group]
        primary["duplicate_count"] = len(group)
        if len(group) > 1:
            duplicate_groups.append(
                {"rule_key": key, "n": len(group), "sources": primary["source_ids"]}
            )
            primary["anomalies"] = list(primary.get("anomalies") or []) + [
                f"DOUBLON_EXCEL_x{len(group)}"
            ]
        unique.append(primary)
    unique.sort(key=lambda r: (r["cell_ref"], r["pattern"], r["amount_basis"]))
    return unique, duplicate_groups


def analyze_conflicts(raw_rows: list[dict]) -> list[dict]:
    soft: dict[tuple, list[dict]] = defaultdict(list)
    for r in raw_rows:
        soft[(r["cell_ref"], r["match_type"], r["pattern"])].append(r)
    conflicts = []
    for (cell, _mt, pattern), group in soft.items():
        variants = sorted({(g["amount_basis"], g["sign_multiplier"]) for g in group})
        if len(variants) > 1:
            conflicts.append(
                {
                    "cell_ref": cell,
                    "pattern": pattern,
                    "variants": variants,
                    "sources": [g["source_id"] for g in group],
                    "note": "Même compte/cellule avec bases ou signes différents (ex. D22)",
                }
            )
    return conflicts


def dry_run_correspondance(path: Path) -> dict:
    """Analyse complète sans écriture DB."""
    sha = file_sha256(path)
    raw = parse_correspondance_xlsx(path)
    unique, dup_groups = dedupe_business_rules(raw)
    conflicts = analyze_conflicts(raw)

    compte_to_cells: dict[str, set[str]] = defaultdict(set)
    cell_to_comptes: dict[str, set[str]] = defaultdict(set)
    for r in unique:
        compte_to_cells[r["pattern"]].add(r["cell_ref"])
        cell_to_comptes[r["cell_ref"]].add(r["pattern"])

    multi_cell = {c: sorted(v) for c, v in compte_to_cells.items() if len(v) > 1}
    multi_compte = {c: sorted(v) for c, v in cell_to_comptes.items() if len(v) > 1}
    incomplete = [r for r in unique if r.get("anomalies")]
    prefix_n = sum(1 for r in unique if r["match_type"] == "PREFIX")

    return {
        "source_file": str(path),
        "source_sha256": sha,
        "excel_rows": len(raw),
        "unique_business_rules": len(unique),
        "duplicate_groups": len(dup_groups),
        "duplicate_extra_lines": sum(g["n"] - 1 for g in dup_groups),
        "exact_rules": len(unique) - prefix_n,
        "prefix_rules": prefix_n,
        "unique_cells": len(cell_to_comptes),
        "multi_cell_comptes": len(multi_cell),
        "multi_compte_cells": len(multi_compte),
        "conflicts_base_sign": conflicts,
        "incomplete_count": len(incomplete),
        "anomaly_counts": dict(Counter(a for r in unique for a in (r.get("anomalies") or []))),
        "lifecycle_forced": "A_VALIDER",
        "t1_reference_115": 115,
        "t1_reference_67_unmapped": 67,
        "candidates": unique,
        "duplicate_group_details": dup_groups,
        "multi_cell_comptes_detail": multi_cell,
        "comparison_note": (
            "242 = lignes Excel compte→BCM du fichier SCD. "
            "115 (T1/Claude) n'est pas un décompte reproductible depuis ce seul fichier "
            "(43 codes BCM uniques dans Correspondance/Contrôle). "
            "Le seed conserve les 242 règles métier uniques EXACT, toutes A_VALIDER."
        ),
    }


async def find_version_by_fingerprint(
    db: AsyncSession, fingerprint: str
) -> RbcmMappingVersion | None:
    rows = (await db.scalars(select(RbcmMappingVersion))).all()
    for v in rows:
        notes = v.notes or ""
        if f"sha256={fingerprint}" in notes:
            return v
    return None


async def seed_from_correspondance(
    db: AsyncSession,
    *,
    path: Path,
    user: User | None = None,
    label: str = "Correspondance SCD initiale A_VALIDER",
    force_new_version: bool = False,
) -> dict:
    """Insert idempotent : même empreinte fichier → pas de doublon.

    - Crée une ``RbcmMappingVersion`` courante si nécessaire.
    - Insère uniquement des règles ``A_VALIDER``.
    - Ne modifie jamais les règles ``ACTIVE`` / ``REJECTED`` d'autres versions.
    """
    report = dry_run_correspondance(path)
    sha = report["source_sha256"]
    existing = await find_version_by_fingerprint(db, sha)
    if existing is not None and not force_new_version:
        n_rules = int(
            await db.scalar(
                select(func.count()).select_from(RbcmMappingRule).where(
                    RbcmMappingRule.mapping_version_id == existing.id
                )
            )
            or 0
        )
        return {
            "status": "SKIPPED_IDEMPOTENT",
            "version_id": str(existing.id),
            "rules_in_version": n_rules,
            "source_sha256": sha,
            "dry_run": {k: v for k, v in report.items() if k != "candidates"},
        }

    # Ne pas toucher aux règles ACTIVE existantes : nouvelle version seulement.
    for v in (await db.scalars(select(RbcmMappingVersion).where(RbcmMappingVersion.is_current.is_(True)))).all():
        v.is_current = False

    version = RbcmMappingVersion(
        label=label,
        notes=(
            f"Import SCD {path.name} — {report['unique_business_rules']} règles A_VALIDER ; "
            f"sha256={sha} ; D01 non tranché ; aucune activation"
        ),
        is_current=True,
        created_by_id=user.id if user else None,
    )
    db.add(version)
    await db.flush()

    inserted = 0
    for r in report["candidates"]:
        assert r["lifecycle_status"] == "A_VALIDER"
        rule = RbcmMappingRule(
            mapping_version_id=version.id,
            cell_ref=r["cell_ref"],
            match_type=r["match_type"],
            pattern=r["pattern"],
            exclusions=r["exclusions"] or None,
            amount_basis=r["amount_basis"],
            signed_balance_mode=r["signed_balance_mode"],
            sign_multiplier=r["sign_multiplier"],
            priority=r["priority"],
            provenance=r["provenance"],
            lifecycle_status="A_VALIDER",
            notes=r.get("notes"),
            divergence_group=(
                "MULTI_CELL" if r["pattern"] in report["multi_cell_comptes_detail"] else None
            ),
        )
        db.add(rule)
        await db.flush()
        payload = dict(r.get("source_payload") or {})
        payload["source_ids"] = r.get("source_ids")
        payload["rule_key"] = r.get("rule_key")
        payload["anomalies"] = r.get("anomalies")
        db.add(
            RbcmMappingRuleSource(
                rule_id=rule.id,
                source_name=SOURCE_NAME,
                source_payload=payload,
            )
        )
        inserted += 1

    await db.flush()
    return {
        "status": "INSERTED",
        "version_id": str(version.id),
        "rules_inserted": inserted,
        "source_sha256": sha,
        "all_a_valider": True,
        "active_inserted": 0,
        "dry_run": {k: v for k, v in report.items() if k != "candidates"},
    }


def export_candidates_jsonl(path: Path, out: Path) -> dict:
    report = dry_run_correspondance(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for r in report["candidates"]:
            f.write(
                json.dumps(
                    {
                        "source_id": r["source_ids"][0] if r.get("source_ids") else r["source_id"],
                        "source_ids": r.get("source_ids"),
                        "cell_ref": r["cell_ref"],
                        "compte_or_prefix": r["pattern"],
                        "match_type": r["match_type"],
                        "amount_basis": r["amount_basis"],
                        "sign_multiplier": r["sign_multiplier"],
                        "exclusions": r["exclusions"],
                        "provenance": r["provenance"],
                        "lifecycle_status": "A_VALIDER",
                        "notes": r.get("notes"),
                        "anomalies": r.get("anomalies") or [],
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    meta = {k: v for k, v in report.items() if k not in ("candidates", "multi_cell_comptes_detail")}
    meta["jsonl"] = str(out)
    return meta
