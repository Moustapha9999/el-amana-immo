"""Revue complémentaire T3.5-2 — permissions, concurrence PG, échec technique, caisse."""

from __future__ import annotations

import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.models import User
from app.models.reporting_bcm_sm import RbcmCampaign
from app.services.permission_service import user_has_permission_codes
from app.services.reporting_bcm_sm import access as rbcm_access
from app.services.reporting_bcm_sm import control_service as ctrl
from app.services.reporting_bcm_sm import parameter_service as ps
from app.services.reporting_bcm_sm.constants import (
    PERM_CONTROL,
    PERM_IMPORT,
    PERM_PARAMS,
    PERM_PREPARE,
    PERM_VIEW,
)

BANK = "T352R"


def test_view_cannot_write():
    have = {PERM_VIEW}
    assert rbcm_access.can_saisir_parametre(have) is False
    assert rbcm_access.can_lancer_controles(have) is False
    assert rbcm_access.can_importer(have) is False
    assert user_has_permission_codes(have, PERM_VIEW) is True


def test_controleur_peut_saisir():
    have = {PERM_VIEW, PERM_CONTROL}
    assert rbcm_access.can_saisir_parametre(have) is True
    assert rbcm_access.can_lancer_controles(have) is True


def test_prepare_et_import_peuvent_contribuer():
    assert rbcm_access.can_saisir_parametre({PERM_PREPARE}) is True
    assert rbcm_access.can_lancer_controles({PERM_PREPARE}) is True
    assert rbcm_access.can_importer({PERM_PREPARE}) is True
    assert rbcm_access.can_lancer_controles({PERM_IMPORT}) is True
    assert rbcm_access.can_saisir_parametre({PERM_PARAMS}) is True


def test_catalogue_controleur_a_la_saisie():
    from app.data.plateforme_catalogue import ROLE_PERMISSIONS

    assert PERM_PARAMS in ROLE_PERMISSIONS["reporting-bcm-sm.controleur"]
    assert PERM_PREPARE in ROLE_PERMISSIONS["reporting-bcm-sm.controleur"]
    assert PERM_VIEW in ROLE_PERMISSIONS["reporting-bcm-sm.lecteur"]
    assert PERM_PARAMS not in ROLE_PERMISSIONS["reporting-bcm-sm.lecteur"]
    assert PERM_PREPARE not in ROLE_PERMISSIONS["reporting-bcm-sm.lecteur"]
    assert "reporting-bcm-sm.approve" not in ROLE_PERMISSIONS["reporting-bcm-sm.controleur"]


def test_caisse_devises_pas_dupliquee_en_c():
    async def _run():
        db = MagicMock()
        db.scalars = AsyncMock(return_value=MagicMock(all=lambda: []))
        camp = MagicMock(id=uuid4())
        with patch.object(ctrl.parameter_service, "current_values", AsyncMock(return_value=[])):
            rows = await ctrl._category_c_params(db, campaign=camp, run_id=uuid4())
        keys = {i.item_key for i in rows}
        assert "PARAM:caisse_devises" not in keys
        assert "FPN:ANNEXES" in keys

    asyncio.run(_run())


def test_parametre_absent_nul_zero():
    assert ctrl.param_is_filled(None, None) is False
    assert ctrl.param_is_filled(None, "EN_ATTENTE") is False
    assert ctrl.display_amount(None) is None
    assert ctrl.param_is_filled(Decimal("0.00"), "CALCULE") is True
    assert ctrl.display_amount(Decimal("0.00")) == "0.00"


def test_expected_value_id_obligatoire_si_valeur_existante():
    async def _run():
        camp = MagicMock(status="RAPPROCHEE", id=uuid4())
        prev = MagicMock(id=uuid4(), status="SAISI")
        db = MagicMock()
        db.execute = AsyncMock()
        db.scalar = AsyncMock(return_value=prev)
        with pytest.raises(AppError) as ei:
            await ps.set_parameter(
                db,
                campaign=camp,
                user=MagicMock(id=uuid4()),
                parameter_code="projets",
                value=Decimal("2.00"),
                source="SAISIE",
                justification="motif",
                expected_value_id=None,
            )
        assert ei.value.code == "PARAM_VERSION_REQUIRED"

    asyncio.run(_run())


def test_anomaly_historique_pas_mutee_dans_le_service():
    src = ctrl.__file__
    text = open(src, encoding="utf-8").read()
    assert "await db.delete" not in text
    assert "issue.resolution_state =" not in text


def _host_database_url() -> str:
    """Les tests tournent hors Docker : l’hôte `postgres` du compose n’est pas résolvable."""
    url = get_settings().database_url
    return url.replace("@postgres:", "@127.0.0.1:")


async def _pg_engine():
    engine = create_async_engine(
        _host_database_url(),
        poolclass=NullPool,
        connect_args={"timeout": 8},
    )
    try:
        async with engine.connect() as conn:
            dbname = await conn.scalar(text("SELECT current_database()"))
            has = await conn.scalar(text("SELECT to_regclass('public.rbcm_control_run')"))
            failed_ok = await conn.scalar(
                text(
                    """
                    SELECT 1 FROM pg_constraint
                    WHERE conname = 'ck_rbcm_control_run_result'
                      AND pg_get_constraintdef(oid) LIKE '%FAILED%'
                    """
                )
            )
    except Exception:
        await engine.dispose()
        pytest.skip("PostgreSQL indisponible")
    if not has:
        await engine.dispose()
        pytest.skip("Table rbcm_control_run absente")
    if not failed_ok:
        await engine.dispose()
        pytest.skip("Contrainte FAILED absente (migration rbcm_04)")
    if dbname not in ("bea_digital", "bea_digital_test"):
        await engine.dispose()
        pytest.skip(f"Base inattendue {dbname}")
    return engine


async def _cleanup(engine) -> None:
    stmts = [
        "DELETE FROM rbcm_reconcile_issue WHERE campaign_id IN (SELECT id FROM rbcm_campaign WHERE bank_code = :b)",
        "DELETE FROM rbcm_control_result WHERE campaign_id IN (SELECT id FROM rbcm_campaign WHERE bank_code = :b)",
        "DELETE FROM rbcm_cell_result WHERE campaign_id IN (SELECT id FROM rbcm_campaign WHERE bank_code = :b)",
        "DELETE FROM rbcm_cell_decision WHERE campaign_id IN (SELECT id FROM rbcm_campaign WHERE bank_code = :b)",
        "DELETE FROM rbcm_ecart_snapshot WHERE campaign_id IN (SELECT id FROM rbcm_campaign WHERE bank_code = :b)",
        "DELETE FROM rbcm_deliverable WHERE campaign_id IN (SELECT id FROM rbcm_campaign WHERE bank_code = :b)",
        "UPDATE rbcm_control_run SET previous_run_id = NULL WHERE campaign_id IN (SELECT id FROM rbcm_campaign WHERE bank_code = :b)",
        "DELETE FROM rbcm_control_run WHERE campaign_id IN (SELECT id FROM rbcm_campaign WHERE bank_code = :b)",
        "DELETE FROM rbcm_parameter_value WHERE campaign_id IN (SELECT id FROM rbcm_campaign WHERE bank_code = :b)",
        "DELETE FROM rbcm_import_line_det WHERE import_id IN (SELECT id FROM rbcm_import WHERE campaign_id IN (SELECT id FROM rbcm_campaign WHERE bank_code = :b))",
        "DELETE FROM rbcm_balance_ncg WHERE campaign_id IN (SELECT id FROM rbcm_campaign WHERE bank_code = :b)",
        "DELETE FROM rbcm_import WHERE campaign_id IN (SELECT id FROM rbcm_campaign WHERE bank_code = :b)",
        "DELETE FROM rbcm_calculation_run WHERE campaign_id IN (SELECT id FROM rbcm_campaign WHERE bank_code = :b)",
        "DELETE FROM rbcm_reporting_owner_history WHERE campaign_id IN (SELECT id FROM rbcm_campaign WHERE bank_code = :b)",
        "DELETE FROM rbcm_validation_event WHERE campaign_id IN (SELECT id FROM rbcm_campaign WHERE bank_code = :b)",
        "DELETE FROM rbcm_campaign WHERE bank_code = :b",
    ]
    async with engine.begin() as conn:
        for sql in stmts:
            await conn.execute(text(sql), {"b": BANK})


async def _user(session: AsyncSession) -> User:
    user = await session.scalar(select(User).where(User.deleted_at.is_(None)).limit(1))
    if user is None:
        pytest.skip("Aucun utilisateur pour les tests PG")
    return user


async def _campaign(session: AsyncSession, user: User, month: int) -> RbcmCampaign:
    camp = RbcmCampaign(
        period_year=2099,
        period_month=month,
        bank_code=BANK,
        status="BROUILLON",
        campaign_version=1,
        preparer_id=user.id,
        reporting_owner_id=user.id,
        notes="T3.5-2 review isolation",
    )
    session.add(camp)
    await session.flush()
    return camp


@pytest.mark.asyncio
async def test_pg_two_control_runs_same_sm_chained():
    engine = await _pg_engine()
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        await _cleanup(engine)
        async with factory() as s:
            user = await _user(s)
            camp = await _campaign(s, user, 1)
            await s.commit()
            cid = camp.id
            uid = user.id

        async def _run_one():
            async with factory() as s2:
                c = await s2.get(RbcmCampaign, cid)
                u = await s2.get(User, uid)
                out = await ctrl.run_sm_controls(s2, campaign=c, user=u)
                await s2.commit()
                return out["id"]

        id_a, id_b = await asyncio.gather(_run_one(), _run_one())
        assert id_a != id_b
        async with factory() as s:
            runs = await ctrl.list_runs(s, cid)
            assert len(runs) == 2
            later, earlier = runs[0], runs[1]
            assert later.previous_run_id == earlier.id
            assert later.result != "FAILED"
            n_issues = int(
                await s.scalar(
                    text("SELECT count(*) FROM rbcm_reconcile_issue WHERE campaign_id = :c"),
                    {"c": cid},
                )
                or 0
            )
            assert n_issues >= 2
    finally:
        await _cleanup(engine)
        await engine.dispose()


@pytest.mark.asyncio
async def test_pg_lock_timeout_second_session_same_sm():
    engine = await _pg_engine()
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        await _cleanup(engine)
        async with factory() as s:
            user = await _user(s)
            camp = await _campaign(s, user, 2)
            await s.commit()
            cid = camp.id

        async with factory() as s1:
            locked = await s1.scalar(
                select(RbcmCampaign).where(RbcmCampaign.id == cid).with_for_update()
            )
            assert locked is not None
            async with factory() as s2:
                await s2.execute(text("SET lock_timeout = '800ms'"))
                with pytest.raises(Exception) as ei:
                    await asyncio.wait_for(
                        s2.scalar(
                            select(RbcmCampaign).where(RbcmCampaign.id == cid).with_for_update()
                        ),
                        timeout=5,
                    )
                await s2.rollback()
            await s1.rollback()
        blob = f"{type(ei.value).__name__} {ei.value}".lower()
        assert "lock" in blob or "timeout" in blob or "cancel" in blob
    finally:
        await _cleanup(engine)
        await engine.dispose()


@pytest.mark.asyncio
async def test_pg_two_sm_controls_independent():
    engine = await _pg_engine()
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        await _cleanup(engine)
        async with factory() as s:
            user = await _user(s)
            a = await _campaign(s, user, 3)
            b = await _campaign(s, user, 4)
            await s.commit()
            ids = (a.id, b.id)
            uid = user.id

        async def _run(cid):
            async with factory() as s2:
                c = await s2.get(RbcmCampaign, cid)
                u = await s2.get(User, uid)
                out = await ctrl.run_sm_controls(s2, campaign=c, user=u)
                await s2.commit()
                return out["id"]

        ra, rb = await asyncio.gather(_run(ids[0]), _run(ids[1]))
        assert ra != rb
        async with factory() as s:
            for cid in ids:
                runs = await ctrl.list_runs(s, cid)
                assert len(runs) == 1
                assert runs[0].previous_run_id is None
    finally:
        await _cleanup(engine)
        await engine.dispose()


@pytest.mark.asyncio
async def test_pg_technical_failure_not_ok():
    engine = await _pg_engine()
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        await _cleanup(engine)
        async with factory() as s:
            user = await _user(s)
            camp = await _campaign(s, user, 5)
            await s.commit()
            cid = camp.id
            uid = user.id
        async with factory() as s:
            c = await s.get(RbcmCampaign, cid)
            u = await s.get(User, uid)
            with patch.object(ctrl, "_mapping_snapshot", AsyncMock(side_effect=RuntimeError("boom"))):
                with pytest.raises(AppError) as ei:
                    await ctrl.run_sm_controls(s, campaign=c, user=u)
            assert ei.value.code == "CONTROL_TECHNICAL_FAILURE"
            assert "n’a pas pu être conservé" not in ei.value.message
            await s.rollback()
        async with factory() as s:
            runs = await ctrl.list_runs(s, cid)
            assert runs
            assert runs[0].result == "FAILED"
            assert (runs[0].summary or {}).get("technical_failure") is True
            assert runs[0].result != "OK"
            n_ok = int(
                await s.scalar(
                    text(
                        "SELECT count(*) FROM rbcm_control_run WHERE campaign_id = :c AND result = 'OK'"
                    ),
                    {"c": cid},
                )
                or 0
            )
            assert n_ok == 0
    finally:
        await _cleanup(engine)
        await engine.dispose()


@pytest.mark.asyncio
async def test_pg_param_concurrent_second_refused():
    engine = await _pg_engine()
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        await _cleanup(engine)
        async with factory() as s:
            user = await _user(s)
            camp = await _campaign(s, user, 6)
            await s.commit()
            cid = camp.id
            uid = user.id
        async with factory() as s:
            c = await s.get(RbcmCampaign, cid)
            u = await s.get(User, uid)
            await ps.set_parameter(
                s,
                campaign=c,
                user=u,
                parameter_code="projets",
                value=Decimal("10.00"),
                source="SAISIE",
                justification="premier",
            )
            await s.commit()
        async with factory() as s:
            c = await s.get(RbcmCampaign, cid)
            u = await s.get(User, uid)
            current = {p.parameter_code: p for p in await ps.current_values(s, cid)}
            stale = uuid4()
            with pytest.raises(AppError) as ei:
                await ps.set_parameter(
                    s,
                    campaign=c,
                    user=u,
                    parameter_code="projets",
                    value=Decimal("11.00"),
                    source="SAISIE",
                    justification="concurrent",
                    expected_value_id=stale,
                )
            assert ei.value.code == "PARAM_CONFLICT"
            row = await ps.set_parameter(
                s,
                campaign=c,
                user=u,
                parameter_code="projets",
                value=Decimal("12.00"),
                source="SAISIE",
                justification="ok",
                expected_value_id=current["projets"].id,
            )
            await s.commit()
            assert row.value == Decimal("12.00")
            hist, total = await ps.history(s, campaign_id=cid, parameter_code="projets")
            assert total >= 2
            assert hist[0].id != current["projets"].id
    finally:
        await _cleanup(engine)
        await engine.dispose()


@pytest.mark.asyncio
async def test_pg_param_two_sessions_second_refused():
    engine = await _pg_engine()
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        await _cleanup(engine)
        async with factory() as s:
            user = await _user(s)
            camp = await _campaign(s, user, 7)
            await s.commit()
            cid = camp.id
            uid = user.id

        started = asyncio.Event()

        async def _first():
            async with factory() as s:
                c = await s.get(RbcmCampaign, cid)
                u = await s.get(User, uid)
                row = await ps.set_parameter(
                    s,
                    campaign=c,
                    user=u,
                    parameter_code="projets",
                    value=Decimal("1.00"),
                    source="SAISIE",
                    justification="session-a",
                )
                started.set()
                await asyncio.sleep(0.4)
                await s.commit()
                return row.id

        async def _second():
            await started.wait()
            async with factory() as s:
                c = await s.get(RbcmCampaign, cid)
                u = await s.get(User, uid)
                with pytest.raises(AppError) as ei:
                    await ps.set_parameter(
                        s,
                        campaign=c,
                        user=u,
                        parameter_code="projets",
                        value=Decimal("2.00"),
                        source="SAISIE",
                        justification="session-b",
                    )
                assert ei.value.code in ("PARAM_VERSION_REQUIRED", "PARAM_CONFLICT")
                return ei.value.code

        first_id, _code = await asyncio.gather(_first(), _second())
        async with factory() as s:
            hist, total = await ps.history(s, campaign_id=cid, parameter_code="projets")
            assert total == 1
            assert hist[0].id == first_id
            assert hist[0].value == Decimal("1.00")
    finally:
        await _cleanup(engine)
        await engine.dispose()


@pytest.mark.asyncio
async def test_pg_does_not_touch_sm_novembre():
    engine = await _pg_engine()
    try:
        async with engine.connect() as conn:
            row = (
                await conn.execute(
                    text(
                        """
                        SELECT status,
                               (SELECT value FROM rbcm_parameter_value
                                 WHERE campaign_id = c.id AND parameter_code = 'caisse_devises'
                                 ORDER BY created_at DESC LIMIT 1) AS caisse,
                               (SELECT count(*) FROM rbcm_reconcile_issue WHERE campaign_id = c.id) AS issues
                        FROM rbcm_campaign c
                        WHERE period_year = 2026 AND period_month = 11 AND bank_code = 'BEA'
                        """
                    )
                )
            ).first()
            n_av = await conn.scalar(
                text("SELECT count(*) FROM rbcm_mapping_rule WHERE lifecycle_status = 'A_VALIDER'")
            )
        if row is None:
            pytest.skip("SM 11/2026 absente de cette base")
        assert row[0] == "CALCULEE"
        assert row[1] == Decimal("0.00")
        assert int(row[2]) >= 1
        assert int(n_av or 0) == 242
    finally:
        await engine.dispose()
