"""T3.5-3-C — graphe Decimal, WORK, convention C:STRUCT (DOC-01, 08, 11–14, 22–26, 28, 32, 34–35)."""

from __future__ import annotations

import asyncio
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from openpyxl import load_workbook
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.models import User
from app.models.reporting_bcm_sm import RbcmCampaign
from app.services.reporting_bcm_sm.document_graph import (
    STAT_CONTROLE,
    STAT_NON_INTERP,
    STAT_NON_RENSEIGNE,
    STAT_PARTIELLE,
    STAT_PROVISOIRE_D09,
    evaluate_graph,
)
from app.services.reporting_bcm_sm.document_keys import STRUCT_KEYS_C, document_key_ok
from app.services.reporting_bcm_sm.formula_parser import FormulaSyntaxError, parse_formula
from app.services.reporting_bcm_sm.template_seed import inventory_official_xlsx
from app.services.reporting_bcm_sm.template_storage import file_sha256

BANK = "T353C"
OCTOBER_LITERALS = ("588160767", "2873218", "5874268360", "150000000", "331024347.65")


def _official_xlsx() -> Path:
    candidates = [
        Path("/workspace/BEA-SM-10-2026.xlsx"),
        Path("/data/BEA-SM-10-2026.xlsx"),
        Path(__file__).resolve().parents[2] / "BEA-SM-10-2026.xlsx",
    ]
    for p in candidates:
        if p.is_file():
            return p
    pytest.skip("BEA-SM-10-2026.xlsx introuvable")


def _specs_as_cells():
    specs, report = inventory_official_xlsx(_official_xlsx())
    cells = [
        SimpleNamespace(
            document_cell_key=s.document_cell_key,
            sheet_name=s.sheet_name,
            excel_address=s.excel_address,
            nature=s.nature,
            formula_text=s.formula_text,
            writable=s.writable,
            axis=s.axis,
            completeness_group=s.completeness_group,
        )
        for s in specs
    ]
    return cells, report


def test_doc_struct_keys_and_regex():
    cells, _ = _specs_as_cells()
    keys = {c.document_cell_key for c in cells}
    for k in STRUCT_KEYS_C:
        assert k in keys
    assert "C:HDR:F44" not in keys
    hdr = [c for c in cells if ":HDR:" in c.document_cell_key]
    assert all(c.nature == "HEADER" for c in hdr)
    assert all(document_key_ok(c.document_cell_key) for c in cells)


def test_all_official_formulas_parse():
    cells, report = _specs_as_cells()
    assert report["formula_count"] == 663
    errors = []
    for c in cells:
        if not c.formula_text:
            continue
        try:
            parse_formula(c.formula_text)
        except FormulaSyntaxError as exc:
            errors.append(f"{c.document_cell_key} {c.formula_text!r}: {exc}")
    assert errors == []


def test_doc_11_14_22_35_graph_unit():
    cells, _ = _specs_as_cells()
    graph = evaluate_graph(
        cells,
        overlay={"A:102:F": Decimal("100.00")},
        canvas={},
    )
    h9 = graph.get("A:102:H")
    assert h9 is not None
    assert h9.status == STAT_PARTIELLE
    assert h9.value is None
    d9 = graph.get("A:102:D")
    assert d9 is not None and d9.status == STAT_NON_RENSEIGNE
    c36 = graph.get("FPN:C36")
    assert c36 is not None and c36.status == STAT_NON_INTERP
    assert c36.value is None
    l11 = graph.get("B:104:L")
    i8 = graph.get("C:103:I")
    assert l11 is not None and l11.status == STAT_CONTROLE
    assert i8 is not None and i8.status == STAT_CONTROLE
    for key in ("RCR:H28", "LIQ:C26", "FPAI:C16"):
        node = graph.get(key)
        assert node is not None
        assert node.status == STAT_NON_INTERP
        assert node.value is None
    h31 = graph.get("RCR:H31")
    assert h31 is not None
    assert h31.nature == "CANVAS_SCALE_FORMULA"
    assert h31.status == STAT_NON_INTERP
    assert h31.value is None
    d09 = graph.get("B:207:E")
    assert d09 is not None and d09.status == STAT_PROVISOIRE_D09
    i147 = graph.get("A:CTRL:I147")
    assert i147 is not None and i147.formula_text == "=+H147-H81"


def _database_url() -> str:
    url = get_settings().database_url
    if Path("/.dockerenv").exists():
        return url
    return url.replace("@postgres:", "@127.0.0.1:")


async def _pg():
    engine = create_async_engine(_database_url(), poolclass=NullPool, connect_args={"timeout": 8})
    try:
        async with engine.connect() as conn:
            dbname = await conn.scalar(text("SELECT current_database()"))
            addr = await conn.scalar(text("SELECT host(inet_server_addr())"))
            ver = await conn.scalar(text("SELECT version_num FROM alembic_version"))
            bea = await conn.scalar(
                text(
                    """
                    SELECT COUNT(*) FROM rbcm_campaign
                    WHERE bank_code='BEA' AND period_year=2026 AND period_month IN (1,11)
                    """
                )
            )
    except Exception:
        await engine.dispose()
        pytest.skip("PostgreSQL indisponible")
    if dbname != "bea_digital":
        await engine.dispose()
        pytest.skip(f"Base inattendue {dbname}")
    if addr and not str(addr).startswith("172.18.") and addr not in ("127.0.0.1", "::1"):
        await engine.dispose()
        pytest.skip(f"Hôte non local {addr}")
    if ver != "20261116_rbcm_05":
        await engine.dispose()
        pytest.skip("rbcm_05 absente")
    if bea != 2:
        await engine.dispose()
        pytest.skip("SM BEA 01/11 2026 absentes — stop")
    return engine


async def _cleanup(engine) -> None:
    from app.services.reporting_bcm_sm.work_fill import work_dest_dir

    async with engine.begin() as conn:
        ids = (
            await conn.execute(text("SELECT id FROM rbcm_campaign WHERE bank_code = :b"), {"b": BANK})
        ).scalars().all()
        await conn.execute(
            text(
                """
                DELETE FROM rbcm_document_decision WHERE campaign_id IN
                  (SELECT id FROM rbcm_campaign WHERE bank_code = :b)
                """
            ),
            {"b": BANK},
        )
        await conn.execute(
            text(
                """
                DELETE FROM rbcm_deliverable WHERE campaign_id IN
                  (SELECT id FROM rbcm_campaign WHERE bank_code = :b)
                """
            ),
            {"b": BANK},
        )
        await conn.execute(
            text("DELETE FROM rbcm_validation_event WHERE campaign_id IN (SELECT id FROM rbcm_campaign WHERE bank_code = :b)"),
            {"b": BANK},
        )
        await conn.execute(
            text("DELETE FROM rbcm_reporting_owner_history WHERE campaign_id IN (SELECT id FROM rbcm_campaign WHERE bank_code = :b)"),
            {"b": BANK},
        )
        await conn.execute(text("DELETE FROM rbcm_campaign WHERE bank_code = :b"), {"b": BANK})
    for cid in ids:
        dest = work_dest_dir(cid)
        if dest.is_dir():
            for p in dest.glob("*"):
                p.unlink(missing_ok=True)


def test_pg_struct_repair_and_work_docs():
    async def _run():
        from app.services.reporting_bcm_sm.template_seed import apply_struct_key_convention
        from app.services.reporting_bcm_sm.work_fill import generate_work

        engine = await _pg()
        Session = async_sessionmaker(engine, expire_on_commit=False)
        try:
            await _cleanup(engine)
            async with Session() as db:
                n = await apply_struct_key_convention(db)
                await db.commit()
                keys = set(
                    (
                        await db.execute(
                            text(
                                """
                                SELECT document_cell_key FROM rbcm_template_cell
                                WHERE document_cell_key IN
                                  ('C:STRUCT:F44','C:STRUCT:F46','C:STRUCT:F48','C:HDR:F44')
                                """
                            )
                        )
                    ).scalars()
                )
                assert "C:STRUCT:F44" in keys
                assert "C:HDR:F44" not in keys
                mapping = await db.scalar(
                    text("SELECT COUNT(*) FROM rbcm_mapping_rule WHERE lifecycle_status='A_VALIDER'")
                )
                active = await db.scalar(
                    text("SELECT COUNT(*) FROM rbcm_mapping_rule WHERE lifecycle_status='ACTIVE'")
                )
                assert mapping == 242 and active == 0
                user = await db.scalar(select(User).where(User.deleted_at.is_(None)).limit(1))
                if user is None:
                    pytest.skip("aucun utilisateur")
                camp = RbcmCampaign(
                    period_year=2099,
                    period_month=3,
                    bank_code=BANK,
                    status="BROUILLON",
                    campaign_version=1,
                    preparer_id=user.id,
                    notes="T3.5-3-C jetable",
                )
                db.add(camp)
                await db.commit()
                cid, uid = camp.id, user.id

            async def _one():
                async with Session() as s:
                    camp = await s.get(RbcmCampaign, cid)
                    user = await s.get(User, uid)
                    out = await generate_work(s, campaign=camp, user=user)
                    await s.commit()
                    return out

            first, second = await asyncio.gather(_one(), _one())
            seqs = sorted([first["document_seq"], second["document_seq"]])
            assert seqs == [1, 2]
            assert first["id"] != second["id"]
            newer = first if first["document_seq"] == 2 else second
            older = second if newer is first else first
            p1, p2 = Path(older["stored_path"]), Path(newer["stored_path"])
            assert p1.is_file() and p2.is_file()
            assert file_sha256(p1) == older["sha256"]
            assert file_sha256(p2) == newer["sha256"]
            wb = load_workbook(p2, data_only=False)
            assert wb.sheetnames[0] == "À LIRE"
            assert wb.sheetnames[1] == "AVERTISSEMENT"
            assert "ETAT A" in wb.sheetnames
            official = [s for s in wb.sheetnames if s not in ("AVERTISSEMENT", "À LIRE")]
            assert len(official) == 8
            cover = " ".join(
                str(wb["À LIRE"].cell(row=r, column=1).value or "") for r in range(1, 12)
            )
            assert "DOCUMENT DE TRAVAIL — NON VALIDÉ" in cover
            assert "03/2099" in cover or "mars 2099" in cover.lower()
            etat_a = wb["ETAT A"]
            blob = Path(p2).read_bytes()
            for lit in OCTOBER_LITERALS:
                assert lit.encode() not in blob
            assert etat_a["D9"].value in (None, "")
            assert etat_a["I147"].value == "=+H147-H81"
            rcr = wb["RATIO COUVERTURE DE RISQUE"]
            assert rcr["H31"].value == "='CALCUL FPN'!C39*10"
            for addr in ("E7", "E17", "E20", "E25"):
                assert rcr[addr].value in (None, "")
            info = wb["informations à fournir"]
            assert info["C9"].value == "='ETAT A'!D146"
            for addr in ("C6", "C8", "C10", "C20"):
                assert info[addr].value in (None, "")
            etat_b = wb["ETAT B"]
            assert etat_b["E46"].value is not None and "30%" in str(etat_b["E46"].value)
            avert = " ".join(str(wb["AVERTISSEMENT"].cell(row=r, column=1).value or "") for r in range(1, 8))
            assert "ne constitue pas une validation réglementaire" in avert
            assert "D9" in avert
            wb.close()

            async with Session() as db:
                works = (
                    await db.execute(
                        text(
                            """
                            SELECT status, document_seq FROM rbcm_deliverable
                            WHERE campaign_id = :c ORDER BY document_seq
                            """
                        ),
                        {"c": cid},
                    )
                ).all()
                assert [w[0] for w in works] == ["SUPERSEDED", "WORK"]
                assert [w[1] for w in works] == [1, 2]
                bea_tpl = await db.scalar(
                    text(
                        """
                        SELECT COUNT(*) FROM rbcm_campaign
                        WHERE bank_code='BEA' AND period_year=2026 AND period_month IN (1,11)
                          AND template_version_id IS NOT NULL
                        """
                    )
                )
                assert bea_tpl == 0
                mapping = await db.scalar(
                    text("SELECT COUNT(*) FROM rbcm_mapping_rule WHERE lifecycle_status='A_VALIDER'")
                )
                assert mapping == 242
        finally:
            await _cleanup(engine)
            await engine.dispose()

    asyncio.run(_run())


def test_doc_28_32_storage_and_rollback():
    async def _run():
        from app.services.reporting_bcm_sm import work_fill as wf

        engine = await _pg()
        Session = async_sessionmaker(engine, expire_on_commit=False)
        try:
            await _cleanup(engine)
            async with Session() as db:
                user = await db.scalar(select(User).where(User.deleted_at.is_(None)).limit(1))
                camp = RbcmCampaign(
                    period_year=2099,
                    period_month=4,
                    bank_code=BANK,
                    status="BROUILLON",
                    campaign_version=1,
                    notes="T3.5-3-C rollback",
                )
                db.add(camp)
                await db.commit()
                cid = camp.id
            async with Session() as db:
                camp = await db.get(RbcmCampaign, cid)
                first = await wf.generate_work(db, campaign=camp, user=None)
                await db.commit()
            first_path = Path(first["stored_path"])
            first_sha = first["sha256"]
            def _fail_load(*_a, **_k):
                raise OSError("stockage test")

            async with Session() as db:
                camp = await db.get(RbcmCampaign, cid)
                with patch.object(wf, "load_workbook", _fail_load):
                    with pytest.raises(AppError) as ei:
                        await wf.generate_work(db, campaign=camp, user=None)
                    assert ei.value.code == "STORAGE_UNAVAILABLE"
                    await db.rollback()
            assert first_path.is_file()
            assert file_sha256(first_path) == first_sha
            async with Session() as db:
                n_work = await db.scalar(
                    text("SELECT COUNT(*) FROM rbcm_deliverable WHERE campaign_id=:c AND status='WORK'"),
                    {"c": cid},
                )
                assert n_work == 1
        finally:
            await _cleanup(engine)
            await engine.dispose()

    asyncio.run(_run())
