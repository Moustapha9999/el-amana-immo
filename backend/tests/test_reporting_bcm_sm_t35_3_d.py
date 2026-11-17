"""T3.5-3-D — API documents WORK : liste, détail, téléchargement, SHA, audit."""

from __future__ import annotations

import hashlib
import inspect
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.exceptions import AppError
from app.main import app
from app.models import User
from app.models.reporting_bcm_sm import RbcmCampaign, RbcmDeliverable
from app.services.reporting_bcm_sm.constants import PERM_EXPORT, PERM_VIEW
from app.services.reporting_bcm_sm.document_access import (
    WORK_DISCLAIMER,
    document_public_dict,
    resolve_deliverable_file,
    safe_download_name,
    sm_period_filename,
)
from app.services.reporting_bcm_sm.template_storage import file_sha256

BANK = "T353D"
API = "/api/v1/reporting-bcm-sm"


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
            text(
                "DELETE FROM rbcm_validation_event WHERE campaign_id IN "
                "(SELECT id FROM rbcm_campaign WHERE bank_code = :b)"
            ),
            {"b": BANK},
        )
        await conn.execute(
            text(
                "DELETE FROM rbcm_reporting_owner_history WHERE campaign_id IN "
                "(SELECT id FROM rbcm_campaign WHERE bank_code = :b)"
            ),
            {"b": BANK},
        )
        await conn.execute(text("DELETE FROM rbcm_campaign WHERE bank_code = :b"), {"b": BANK})
    for cid in ids:
        dest = work_dest_dir(cid)
        if dest.is_dir():
            for p in dest.glob("*"):
                p.unlink(missing_ok=True)
            exports = dest.parent / "exports"
            if exports.is_dir():
                for p in exports.glob("*"):
                    p.unlink(missing_ok=True)


def _install_auth(user: User) -> None:
    async def fake_user():
        return user

    app.dependency_overrides[get_current_user] = fake_user
    seen: set[int] = set()
    stack = []
    for route in app.routes:
        dep = getattr(route, "dependant", None)
        if dep is not None:
            stack.append(dep)
    while stack:
        cur = stack.pop()
        for d in cur.dependencies:
            stack.append(d)
            fn = d.call
            if fn is None or id(fn) in seen:
                continue
            seen.add(id(fn))
            if getattr(fn, "__name__", "") != "_checker":
                continue
            try:
                params = inspect.signature(fn).parameters
            except (TypeError, ValueError):
                continue
            if "credentials" in params:
                app.dependency_overrides[fn] = fake_user


def _clear_auth() -> None:
    app.dependency_overrides.clear()


def test_public_dict_never_exposes_path_or_validated():
    d = SimpleNamespace(
        id=uuid.uuid4(),
        campaign_id=uuid.uuid4(),
        kind="EXCEL",
        filename="BEA-SM-WORK.xlsx",
        stored_path="/secret/work.xlsx",
        sha256="abc",
        status="WORK",
        document_seq=2,
        created_at=None,
        created_by_id=None,
        template_id=uuid.uuid4(),
        superseded_by_id=None,
        warnings={"stored_path": "/secret", "cells_written": 3},
    )
    pub = document_public_dict(d)
    assert "stored_path" not in pub
    assert pub["status"] == "WORK"
    assert pub["regulatory_validated"] is False
    assert pub["is_current_work"] is True
    assert pub["work_disclaimer"] == WORK_DISCLAIMER
    assert "VALIDATED" not in pub["status"]
    with pytest.raises(AppError) as ei:
        safe_download_name("../etc/passwd.xlsx")
    assert ei.value.code == "TEMPLATE_PATH_UNSAFE"
    assert safe_download_name("BEA-SM-2099-03-WORK-v2.xlsx") == "BEA-SM-2099-03-WORK-v2.xlsx"
    assert sm_period_filename(2026, 1) == "SM-01-2026.xlsx"
    assert sm_period_filename(2026, 2) == "SM-02-2026.xlsx"
    assert sm_period_filename(2026, 10) == "SM-10-2026.xlsx"
    pub_named = document_public_dict(d, period_year=2026, period_month=1)
    assert pub_named["filename"] == "SM-01-2026.xlsx"


def test_resolve_file_security(tmp_path: Path):
    root = tmp_path / "uploads"
    camp = uuid.uuid4()
    work = root / "reporting-bcm-sm" / str(camp) / "work"
    work.mkdir(parents=True)
    ok = work / "ok.xlsx"
    ok.write_bytes(b"PK\x03\x04safe")
    outside = tmp_path / "secret.xlsx"
    outside.write_bytes(b"secret")
    sha = file_sha256(ok)

    def _ns(**extra):
        base = dict(
            campaign_id=camp,
            stored_path=str(ok),
            filename="ok.xlsx",
            sha256=sha,
        )
        base.update(extra)
        return SimpleNamespace(**base)

    with patch(
        "app.services.reporting_bcm_sm.document_access.resolved_upload_root",
        return_value=root.resolve(),
    ):
        assert resolve_deliverable_file(_ns()) == ok.resolve()
        with pytest.raises(AppError) as ei:
            resolve_deliverable_file(_ns(stored_path=str(outside)))
        assert ei.value.code == "TEMPLATE_PATH_UNSAFE"
        with pytest.raises(AppError) as ei:
            resolve_deliverable_file(_ns(stored_path=str(work / ".." / ".." / "secret.xlsx")))
        assert ei.value.code == "TEMPLATE_PATH_UNSAFE"
        with pytest.raises(AppError) as ei:
            resolve_deliverable_file(_ns(stored_path="/tmp/abs.xlsx"))
        assert ei.value.code == "TEMPLATE_PATH_UNSAFE"
        with pytest.raises(AppError) as ei:
            resolve_deliverable_file(_ns(stored_path=str(work / "missing.xlsx"), sha256=None))
        assert ei.value.code == "DELIVERABLE_FILE_MISSING"
        with pytest.raises(AppError) as ei:
            resolve_deliverable_file(_ns(sha256="0" * 64))
        assert ei.value.code == "WORK_SHA_MISMATCH"
        link = work / "link.xlsx"
        try:
            link.symlink_to(outside)
        except OSError:
            pytest.skip("symlink indisponible")
        with pytest.raises(AppError) as ei:
            resolve_deliverable_file(_ns(stored_path=str(link), sha256=None))
        assert ei.value.code == "TEMPLATE_PATH_UNSAFE"


def test_routes_permissions_declared():
    from app.api.v1.endpoints import reporting_bcm_sm as ep

    assert "PERM_VIEW" in inspect.getsource(ep.list_campaign_documents)
    assert "PERM_VIEW" in inspect.getsource(ep.get_campaign_document)
    assert "PERM_EXPORT" in inspect.getsource(ep.download_campaign_document)
    assert "PERM_VIEW" not in inspect.getsource(ep.download_campaign_document)
    assert "generate_work" not in inspect.getsource(ep.download_campaign_document)
    assert "generate_work" not in inspect.getsource(ep.list_campaign_documents)
    assert "engine.runner" not in inspect.getsource(ep.download_campaign_document)


def test_pg_document_api():
    async def _run():
        from app.services.reporting_bcm_sm.work_fill import generate_work

        engine = await _pg()
        Session = async_sessionmaker(engine, expire_on_commit=False)
        try:
            await _cleanup(engine)
            async with Session() as db:
                mapping = await db.scalar(
                    text("SELECT COUNT(*) FROM rbcm_mapping_rule WHERE lifecycle_status='A_VALIDER'")
                )
                active = await db.scalar(
                    text("SELECT COUNT(*) FROM rbcm_mapping_rule WHERE lifecycle_status='ACTIVE'")
                )
                assert mapping == 242 and active == 0
                cells = await db.scalar(text("SELECT COUNT(*) FROM rbcm_cell_result"))
                assert cells == 92
                user = await db.scalar(select(User).where(User.deleted_at.is_(None)).limit(1))
                if user is None:
                    pytest.skip("aucun utilisateur")
                camp = RbcmCampaign(
                    period_year=2099,
                    period_month=5,
                    bank_code=BANK,
                    status="BROUILLON",
                    campaign_version=1,
                    preparer_id=user.id,
                    notes="T3.5-3-D jetable",
                )
                other = RbcmCampaign(
                    period_year=2099,
                    period_month=6,
                    bank_code=BANK,
                    status="BROUILLON",
                    campaign_version=1,
                    preparer_id=user.id,
                    notes="T3.5-3-D autre SM",
                )
                db.add_all([camp, other])
                await db.commit()
                cid, oid, uid = camp.id, other.id, user.id

            async with Session() as db:
                camp = await db.get(RbcmCampaign, cid)
                user = await db.get(User, uid)
                first = await generate_work(db, campaign=camp, user=user)
                await db.commit()
            async with Session() as db:
                camp = await db.get(RbcmCampaign, cid)
                user = await db.get(User, uid)
                second = await generate_work(db, campaign=camp, user=user)
                await db.commit()
            work_id = uuid.UUID(str(second["id"]))
            old_id = uuid.UUID(str(first["id"]))
            work_path = Path(second["stored_path"])
            work_sha = second["sha256"]
            n_before = 2

            async with Session() as db:
                gen = RbcmDeliverable(
                    campaign_id=cid,
                    kind="EXCEL",
                    filename="export-technique.xlsx",
                    stored_path=None,
                    status="GENERATED",
                    sha256=None,
                    warnings={"note": "technique"},
                )
                evil = RbcmDeliverable(
                    campaign_id=cid,
                    kind="EXCEL",
                    filename="escape.xlsx",
                    stored_path="/app/storage/uploads/reporting-bcm-sm/../../etc/passwd",
                    status="GENERATED",
                    sha256=None,
                )
                db.add_all([gen, evil])
                await db.commit()
                gen_id, evil_id = gen.id, evil.id
                user = await db.get(User, uid)

            _install_auth(user)
            try:
                transport = ASGITransport(app=app)
                async with AsyncClient(transport=transport, base_url="http://test") as ac:
                    view_only = patch(
                        "app.api.deps.load_user_permission_codes",
                        new=AsyncMock(return_value={PERM_VIEW}),
                    )
                    both = patch(
                        "app.api.deps.load_user_permission_codes",
                        new=AsyncMock(return_value={PERM_VIEW, PERM_EXPORT}),
                    )
                    none = patch(
                        "app.api.deps.load_user_permission_codes",
                        new=AsyncMock(return_value=set()),
                    )

                    with none:
                        r = await ac.get(f"{API}/campaigns/{cid}/documents")
                        assert r.status_code == 403, r.text
                        r = await ac.get(f"{API}/campaigns/{cid}/documents/{work_id}/download")
                        assert r.status_code == 403, r.text

                    with view_only:
                        r = await ac.get(f"{API}/campaigns/{cid}/documents")
                        assert r.status_code == 200, r.text
                        r = await ac.get(f"{API}/campaigns/{cid}/documents/{work_id}/download")
                        assert r.status_code == 403, r.text

                    with both, patch(
                        "app.services.reporting_bcm_sm.work_fill.generate_work",
                        new=AsyncMock(side_effect=AssertionError("GET ne doit pas régénérer")),
                    ):
                        r = await ac.get(f"{API}/campaigns/{cid}/documents")
                        assert r.status_code == 200, r.text
                        body = r.json()
                        assert body["total"] == 4
                        statuses = {it["status"] for it in body["items"]}
                        assert statuses == {"WORK", "SUPERSEDED", "GENERATED"}
                        assert "VALIDATED" not in statuses
                        for it in body["items"]:
                            assert "stored_path" not in it
                            assert it["regulatory_validated"] is False
                            if it["status"] == "WORK":
                                assert it["is_current_work"] is True
                                assert it["work_disclaimer"]
                                assert it["document_seq"] == 2
                                assert it["sha256_available"] is True
                            if it["status"] == "SUPERSEDED":
                                assert it["is_current_work"] is False
                                assert it["work_disclaimer"]
                                assert it["document_seq"] == 1

                        r = await ac.get(f"{API}/campaigns/{cid}/documents/{work_id}")
                        assert r.status_code == 200, r.text
                        detail = r.json()
                        assert "stored_path" not in detail
                        assert detail["status"] == "WORK"
                        assert "ne constitue pas une validation réglementaire" in (
                            detail["work_disclaimer"] or ""
                        )
                        assert detail["regulatory_validated"] is False
                        hist_status = {h["status"] for h in detail["history"]}
                        assert "WORK" in hist_status and "SUPERSEDED" in hist_status

                        r = await ac.get(f"{API}/campaigns/{cid}/documents/{work_id}/download")
                        assert r.status_code == 200, r.text
                        assert r.content[:2] == b"PK"
                        assert "attachment" in r.headers.get("content-disposition", "").lower()
                        got = hashlib.sha256(r.content).hexdigest()
                        assert got == work_sha

                        r = await ac.get(f"{API}/campaigns/{cid}/documents/{old_id}/download")
                        assert r.status_code == 200, r.text
                        assert r.content[:2] == b"PK"

                        r = await ac.get(f"{API}/campaigns/{oid}/documents/{work_id}")
                        assert r.status_code == 404, r.text
                        assert r.json().get("code") == "DELIVERABLE_NOT_FOUND"
                        r = await ac.get(f"{API}/campaigns/{oid}/documents/{work_id}/download")
                        assert r.status_code == 404, r.text

                        r = await ac.get(f"{API}/campaigns/{cid}/documents/{evil_id}/download")
                        assert r.status_code in (500, 404), r.text
                        assert r.json().get("code") in {
                            "TEMPLATE_PATH_UNSAFE",
                            "DELIVERABLE_FILE_MISSING",
                        }

                        backup = work_path.read_bytes()
                        work_path.write_bytes(backup + b"tamper")
                        r = await ac.get(f"{API}/campaigns/{cid}/documents/{work_id}/download")
                        assert r.status_code == 409, r.text
                        assert r.json().get("code") == "WORK_SHA_MISMATCH"
                        work_path.write_bytes(backup)

                        work_path.unlink()
                        r = await ac.get(f"{API}/campaigns/{cid}/documents/{work_id}/download")
                        assert r.status_code == 404, r.text
                        assert r.json().get("code") == "DELIVERABLE_FILE_MISSING"
                        work_path.write_bytes(backup)

                        r = await ac.get(f"{API}/campaigns/{cid}/documents/{gen_id}/download")
                        assert r.status_code == 404, r.text
                        assert r.json().get("code") == "DELIVERABLE_FILE_MISSING"

                async with Session() as db:
                    n_after = await db.scalar(
                        text("SELECT COUNT(*) FROM rbcm_deliverable WHERE campaign_id=:c"),
                        {"c": cid},
                    )
                    assert n_after == n_before + 2
                    work_n = await db.scalar(
                        text(
                            "SELECT COUNT(*) FROM rbcm_deliverable "
                            "WHERE campaign_id=:c AND status='WORK'"
                        ),
                        {"c": cid},
                    )
                    assert work_n == 1
                    actions = set(
                        (
                            await db.execute(
                                text(
                                    """
                                    SELECT DISTINCT action FROM audit_logs
                                    WHERE action LIKE 'rbcm.document%'
                                      AND (
                                        entity_id = :cid
                                        OR entity_id = :wid
                                        OR entity_id = :oid
                                        OR entity_id = :eid
                                        OR after_data->>'campaign_id' = :cid
                                      )
                                    """
                                ),
                                {
                                    "cid": str(cid),
                                    "wid": str(work_id),
                                    "oid": str(oid),
                                    "eid": str(evil_id),
                                },
                            )
                        ).scalars()
                    )
                    assert "rbcm.document.list" in actions
                    assert "rbcm.document.get" in actions
                    assert "rbcm.document.download" in actions
                    assert "rbcm.document.download_denied" in actions
                    denied_codes = {
                        row[0]
                        for row in (
                            await db.execute(
                                text(
                                    """
                                    SELECT after_data->>'code' FROM audit_logs
                                    WHERE action='rbcm.document.download_denied'
                                      AND after_data->>'campaign_id' = :cid
                                    """
                                ),
                                {"cid": str(cid)},
                            )
                        ).all()
                    }
                    assert "WORK_SHA_MISMATCH" in denied_codes
                    assert "DELIVERABLE_FILE_MISSING" in denied_codes
                    after_ok = (
                        await db.execute(
                            text(
                                """
                                SELECT after_data FROM audit_logs
                                WHERE action='rbcm.document.download'
                                  AND entity_id=:wid
                                ORDER BY created_at DESC LIMIT 1
                                """
                            ),
                            {"wid": str(work_id)},
                        )
                    ).scalar_one()
                    dumped = str(after_ok)
                    assert "stored_path" not in dumped
                    assert "PK" not in dumped
                    mapping = await db.scalar(
                        text("SELECT COUNT(*) FROM rbcm_mapping_rule WHERE lifecycle_status='A_VALIDER'")
                    )
                    active = await db.scalar(
                        text("SELECT COUNT(*) FROM rbcm_mapping_rule WHERE lifecycle_status='ACTIVE'")
                    )
                    assert mapping == 242 and active == 0
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
                    leftover_c = await db.scalar(
                        text("SELECT COUNT(*) FROM rbcm_campaign WHERE bank_code='T353C'")
                    )
                    assert leftover_c == 0
            finally:
                _clear_auth()
        finally:
            await _cleanup(engine)
            await engine.dispose()

    import asyncio

    asyncio.run(_run())
