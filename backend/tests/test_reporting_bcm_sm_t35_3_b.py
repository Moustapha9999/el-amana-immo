"""T3.5-3-B — schéma documentaire, stockage, seed (DOC-02/03/04/09/29–36 partiels)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.models.reporting_bcm_sm import RbcmDeliverable, RbcmDocumentDecision, RbcmTemplate
from app.services.reporting_bcm_sm.template_seed import (
    EXPECTED_FORMULA_COUNT,
    EXPECTED_SHEETS,
    inventory_official_xlsx,
)
from app.services.reporting_bcm_sm.template_storage import (
    OFFICIAL_SHA256,
    copy_official_template,
    file_sha256,
    template_dest_dir,
)

DOC_B = {
    "DOC-02",
    "DOC-03",
    "DOC-04",
    "DOC-09",
    "DOC-29",
    "DOC-30",
    "DOC-31",
    "DOC-33",
    "DOC-34",
    "DOC-35",
    "DOC-36",
}


def _official_xlsx() -> Path:
    candidates = [
        Path("/workspace/BEA-SM-10-2026.xlsx"),
        Path("/data/BEA-SM-10-2026.xlsx"),
        Path("/app/../BEA-SM-10-2026.xlsx"),
        Path(__file__).resolve().parents[2] / "BEA-SM-10-2026.xlsx",
    ]
    for p in candidates:
        if p.is_file():
            return p
    pytest.skip("BEA-SM-10-2026.xlsx introuvable")


def test_doc_02_sha_officiel():
    path = _official_xlsx()
    sha = file_sha256(path)
    assert sha.lower() == OFFICIAL_SHA256.lower()
    assert path.stat().st_size == 78202


def test_doc_31_path_traversal():
    with pytest.raises(AppError) as ei:
        template_dest_dir("not-a-uuid")
    assert ei.value.code == "TEMPLATE_PATH_UNSAFE"


def test_doc_30_sha_mismatch(tmp_path):
    bogus = tmp_path / "BEA-SM-10-2026.xlsx"
    bogus.write_bytes(b"not-the-official-canvas")
    with pytest.raises(AppError) as ei:
        copy_official_template(bogus, uuid4(), expected_sha256=OFFICIAL_SHA256)
    assert ei.value.code == "TEMPLATE_SHA_MISMATCH"


def test_doc_30_missing_file(tmp_path):
    with pytest.raises(AppError) as ei:
        copy_official_template(tmp_path / "absent.xlsx", uuid4())
    assert ei.value.code == "TEMPLATE_NOT_FOUND"


def test_inventory_formulas_i147_h31():
    cells, report = inventory_official_xlsx(_official_xlsx())
    assert report["sheet_count"] == 8
    assert report["formula_count"] == EXPECTED_FORMULA_COUNT
    assert list(EXPECTED_SHEETS) == report["sheets"]
    assert "AVERTISSEMENT" not in report["sheets"]
    assert report["october_constants"] == 9
    assert report["has_i147"] is True
    assert report["h31_nature"] == "CANVAS_SCALE_FORMULA"
    assert report["info_c9_formula"] == "='ETAT A'!D146"
    assert report["info_leaves"] == 14
    i147 = next(c for c in cells if c.document_cell_key == "A:CTRL:I147")
    assert i147.formula_text == "=+H147-H81"
    assert i147.writable is False
    h31 = next(c for c in cells if c.document_cell_key == "RCR:H31")
    assert h31.formula_text == "='CALCUL FPN'!C39*10"
    assert any(c.document_cell_key == "A:102:D" and c.nature == "OCTOBER_CONSTANT_FORMULA" for c in cells)


def test_doc_04_decided_by_nullable():
    col = RbcmDocumentDecision.__table__.c.decided_by_id
    assert col.nullable is True
    fks = list(col.foreign_keys)
    assert fks and "SET NULL" in str(fks[0].ondelete).upper()


def _check_sql(table) -> str:
    return " ".join(str(c.sqltext) for c in table.constraints if c.name and c.name.startswith("ck_"))


def test_doc_33_generated_null_seq():
    sql = _check_sql(RbcmDeliverable.__table__)
    assert "GENERATED" in sql
    assert "document_seq IS NULL" in sql
    assert "VALIDATED" not in sql


def test_no_validated_on_template():
    sql = _check_sql(RbcmTemplate.__table__)
    assert "CURRENT" in sql
    assert "VALIDATED" not in sql


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
            has = await conn.scalar(text("SELECT to_regclass('public.rbcm_template')"))
    except Exception:
        await engine.dispose()
        pytest.skip("PostgreSQL indisponible")
    if dbname != "bea_digital":
        await engine.dispose()
        pytest.skip(f"Base inattendue {dbname}")
    if addr and not str(addr).startswith("172.18.") and addr not in ("127.0.0.1", "::1"):
        await engine.dispose()
        pytest.skip(f"Hôte non local {addr}")
    if ver != "20261116_rbcm_05" or not has:
        await engine.dispose()
        pytest.skip("rbcm_05 non appliquée")
    return engine


def test_doc_09_29_pg_schema():
    async def _run():
        engine = await _pg()
        try:
            async with engine.connect() as conn:
                idx = await conn.scalar(
                    text(
                        """
                        SELECT indexdef FROM pg_indexes
                        WHERE indexname = 'uq_rbcm_deliverable_campaign_seq'
                        """
                    )
                )
                assert idx and "document_seq" in idx and "WHERE" in idx.upper()
                fk = await conn.scalar(
                    text(
                        """
                        SELECT pg_get_constraintdef(oid) FROM pg_constraint
                        WHERE conname = 'fk_rbcm_deliverable_template'
                        """
                    )
                )
                assert fk and "RESTRICT" in fk
                decided = await conn.scalar(
                    text(
                        """
                        SELECT is_nullable FROM information_schema.columns
                        WHERE table_name='rbcm_document_decision' AND column_name='decided_by_id'
                        """
                    )
                )
                assert decided == "YES"
                campaigns = await conn.scalar(text("SELECT COUNT(*) FROM rbcm_campaign"))
                mapping = await conn.scalar(
                    text("SELECT COUNT(*) FROM rbcm_mapping_rule WHERE lifecycle_status='A_VALIDER'")
                )
                active = await conn.scalar(
                    text("SELECT COUNT(*) FROM rbcm_mapping_rule WHERE lifecycle_status='ACTIVE'")
                )
                assert campaigns == 2
                assert mapping == 242
                assert active == 0
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_doc_03_34_35_36_seed_idempotent():
    async def _run():
        from app.services.reporting_bcm_sm.template_seed import seed_official_template

        engine = await _pg()
        Session = async_sessionmaker(engine, expire_on_commit=False)
        xlsx = _official_xlsx()
        try:
            async with Session() as db:
                first = await seed_official_template(db, xlsx)
                await db.commit()
                second = await seed_official_template(db, xlsx)
                await db.commit()
                cells = (
                    await db.execute(
                        text(
                            """
                            SELECT nature, document_cell_key, formula_text
                            FROM rbcm_template_cell c
                            JOIN rbcm_template t ON t.id = c.template_id
                            WHERE t.sha256 = :sha
                            """
                        ),
                        {"sha": OFFICIAL_SHA256},
                    )
                ).all()
        finally:
            await engine.dispose()
        assert first["sha256"].lower() == OFFICIAL_SHA256.lower()
        assert second["idempotent"] is True
        assert second["template_id"] == first["template_id"]
        stored = Path(first["stored_path"])
        assert stored.is_file() or Path("/app/storage/uploads").joinpath(
            *stored.parts[stored.parts.index("reporting-bcm-sm"):]
        ).is_file()
        keys = {r[1] for r in cells}
        natures = {r[1]: r[0] for r in cells}
        assert "A:CTRL:I147" in keys
        assert natures.get("RCR:H31") == "CANVAS_SCALE_FORMULA"
        formulas = [r for r in cells if r[2]]
        assert len(formulas) == EXPECTED_FORMULA_COUNT
        constants = [r for r in cells if r[0] == "OCTOBER_CONSTANT_FORMULA"]
        assert len(constants) == 9

    asyncio.run(_run())
