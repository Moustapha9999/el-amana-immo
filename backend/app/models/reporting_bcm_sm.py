"""Reporting BCM SM — modèles SQLAlchemy (préfixe ``rbcm_``).

P2 (implémentation) : UNIQUE (bank_code, period_year, period_month, campaign_version)
+ au plus une campagne non clôturée par période (contrôle service).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text as sa_text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin
from app.services.reporting_bcm_sm.constants import (
    CAMPAIGN_STATUSES,
    CONTROL_CATEGORIES,
    CONTROL_RESOLUTION_STATES,
    CONTROL_RUN_RESULTS,
    ECART_STATES,
    IMPORT_FILE_TYPES,
    IMPORT_STATUSES,
    MAPPING_LIFECYCLES,
    NCG_ORIENTATION_CURRENCIES,
    NCG_ORIENTATION_OPERATIONS,
    NCG_ORIENTATION_RESIDENCES,
    NCG_ORIENTATION_SHEETS,
    NCG_ORIENTATION_STATUSES,
    PARAMETER_VALUE_STATUSES,
)


def _fk(cible: str, ondelete: str = "RESTRICT") -> ForeignKey:
    return ForeignKey(cible, ondelete=ondelete)


def _user_fk(nullable: bool = True) -> Mapped[uuid.UUID | None]:
    return mapped_column(UUID(as_uuid=True), _fk("users.id", "SET NULL"), nullable=nullable)


_STATUS_LIST = ", ".join(f"'{s}'" for s in CAMPAIGN_STATUSES)
_CTRL_CAT = ", ".join(f"'{s}'" for s in CONTROL_CATEGORIES)
_CTRL_RES = ", ".join(f"'{s}'" for s in CONTROL_RESOLUTION_STATES)
_CTRL_RUN = ", ".join(f"'{s}'" for s in CONTROL_RUN_RESULTS)
_IMPORT_TYPES = ", ".join(f"'{s}'" for s in IMPORT_FILE_TYPES)
_IMPORT_STATUSES = ", ".join(f"'{s}'" for s in IMPORT_STATUSES)
_MAP_LIFE = ", ".join(f"'{s}'" for s in MAPPING_LIFECYCLES)
_PARAM_STAT = ", ".join(f"'{s}'" for s in PARAMETER_VALUE_STATUSES)
_ECART = ", ".join(f"'{s}'" for s in ECART_STATES)
_NCG_ORI_STAT = ", ".join(f"'{s}'" for s in NCG_ORIENTATION_STATUSES)
_NCG_ORI_OPS = ", ".join(f"'{s}'" for s in NCG_ORIENTATION_OPERATIONS)
_NCG_ORI_CUR = ", ".join(f"'{s}'" for s in NCG_ORIENTATION_CURRENCIES)
_NCG_ORI_RES = ", ".join(f"'{s}'" for s in NCG_ORIENTATION_RESIDENCES)
_NCG_ORI_SHEET = ", ".join(f"'{s}'" for s in NCG_ORIENTATION_SHEETS)


class RbcmCampaign(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "rbcm_campaign"
    __mapper_args__ = {"eager_defaults": True}
    __table_args__ = (
        UniqueConstraint(
            "bank_code",
            "period_year",
            "period_month",
            "campaign_version",
            name="uq_rbcm_campaign_period_version",
        ),
        CheckConstraint("period_month BETWEEN 1 AND 12", name="ck_rbcm_campaign_month"),
        CheckConstraint("campaign_version >= 1", name="ck_rbcm_campaign_version"),
        CheckConstraint(f"status IN ({_STATUS_LIST})", name="ck_rbcm_campaign_status"),
    )

    period_year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    period_month: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    closing_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    bank_code: Mapped[str] = mapped_column(String(16), nullable=False, default="BEA")
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="BROUILLON", index=True)
    campaign_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    reopened_from_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), _fk("rbcm_campaign.id", "RESTRICT"), nullable=True
    )
    preparer_id: Mapped[uuid.UUID | None] = _user_fk()
    reporting_owner_id: Mapped[uuid.UUID | None] = _user_fk()
    reporting_owner_set_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    controller_id: Mapped[uuid.UUID | None] = _user_fk()
    approver_id: Mapped[uuid.UUID | None] = _user_fk()
    mapping_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    template_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), _fk("rbcm_template.id", "RESTRICT"), nullable=True
    )
    current_batch_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class RbcmImport(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "rbcm_import"
    __mapper_args__ = {"eager_defaults": True}
    __table_args__ = (
        UniqueConstraint("campaign_id", "file_type", "sha256", name="uq_rbcm_import_sha"),
        CheckConstraint(f"file_type IN ({_IMPORT_TYPES})", name="ck_rbcm_import_type"),
        CheckConstraint(f"status IN ({_IMPORT_STATUSES})", name="ck_rbcm_import_status"),
    )

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), _fk("rbcm_campaign.id"), nullable=False, index=True
    )
    file_type: Mapped[str] = mapped_column(String(16), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="UPLOADED")
    period_year_detected: Mapped[int | None] = mapped_column(Integer, nullable=True)
    period_month_detected: Mapped[int | None] = mapped_column(Integer, nullable=True)
    control_report: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    uploaded_by_id: Mapped[uuid.UUID | None] = _user_fk()
    validated_by_id: Mapped[uuid.UUID | None] = _user_fk()
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    supersedes_import_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), _fk("rbcm_import.id", "SET NULL"), nullable=True
    )
    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sum_debit: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    sum_credit: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)


class RbcmBalanceNcg(UUIDPrimaryKeyMixin, Base):
    """Soldes agrégés par NCG (COND ou agrégation DET)."""

    __tablename__ = "rbcm_balance_ncg"
    __table_args__ = (
        UniqueConstraint("import_id", "ncg", name="uq_rbcm_balance_ncg"),
    )

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), _fk("rbcm_campaign.id"), nullable=False, index=True
    )
    import_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), _fk("rbcm_import.id"), nullable=False, index=True
    )
    source: Mapped[str] = mapped_column(String(16), nullable=False)  # BAL_DET | BAL_COND
    ncg: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    libelle: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tot_debit: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"))
    tot_credit: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RbcmImportLineDet(UUIDPrimaryKeyMixin, Base):
    """Lignes DET (détail compte / devise) — montants Numeric(18,2) après normalisation."""

    __tablename__ = "rbcm_import_line_det"

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), _fk("rbcm_campaign.id"), nullable=False, index=True
    )
    import_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), _fk("rbcm_import.id"), nullable=False, index=True
    )
    line_no: Mapped[int] = mapped_column(Integer, nullable=False)
    ncg: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    compte: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    libelle: Mapped[str | None] = mapped_column(String(255), nullable=True)
    devise: Mapped[str | None] = mapped_column(String(8), nullable=True)
    debit: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"))
    credit: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0"))
    raw: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class RbcmControlRun(UUIDPrimaryKeyMixin, Base):
    """Exécution de contrôles SM — snapshot append-only (T3.5-2)."""

    __tablename__ = "rbcm_control_run"
    __table_args__ = (
        CheckConstraint(f"result IN ({_CTRL_RUN})", name="ck_rbcm_control_run_result"),
    )

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), _fk("rbcm_campaign.id"), nullable=False, index=True
    )
    actor_id: Mapped[uuid.UUID | None] = _user_fk()
    result: Mapped[str] = mapped_column(String(24), nullable=False, default="OK")
    previous_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), _fk("rbcm_control_run.id", "SET NULL"), nullable=True
    )
    summary: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RbcmReconcileIssue(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "rbcm_reconcile_issue"
    __table_args__ = (
        CheckConstraint(
            f"category IS NULL OR category IN ({_CTRL_CAT})",
            name="ck_rbcm_reconcile_issue_category",
        ),
        CheckConstraint(
            f"resolution_state IN ({_CTRL_RES})",
            name="ck_rbcm_reconcile_issue_resolution",
        ),
    )

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), _fk("rbcm_campaign.id"), nullable=False, index=True
    )
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), _fk("rbcm_control_run.id", "SET NULL"), nullable=True, index=True
    )
    ncg: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default="WARNING")
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    resolved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    category: Mapped[str | None] = mapped_column(String(1), nullable=True, index=True)
    item_key: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    resolution_state: Mapped[str] = mapped_column(
        String(24), nullable=False, default="OPEN"
    )


class RbcmParameterDefinition(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "rbcm_parameter_definition"
    __table_args__ = (UniqueConstraint("code", name="uq_rbcm_parameter_definition_code"),)

    code: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    calculable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class RbcmParameterValue(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Append-only : une nouvelle saisie = nouvel enregistrement (pas de reconduction N−1)."""

    __tablename__ = "rbcm_parameter_value"
    __table_args__ = (
        CheckConstraint(f"status IN ({_PARAM_STAT})", name="ck_rbcm_parameter_value_status"),
    )

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), _fk("rbcm_campaign.id"), nullable=False, index=True
    )
    parameter_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    value: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    justification: Mapped[str | None] = mapped_column(Text, nullable=True)
    justificatif_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="EN_ATTENTE")
    authored_by_id: Mapped[uuid.UUID | None] = _user_fk()
    validated_by_id: Mapped[uuid.UUID | None] = _user_fk()
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    supersedes_value_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), _fk("rbcm_parameter_value.id", "SET NULL"), nullable=True
    )


class RbcmMappingVersion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "rbcm_mapping_version"

    label: Mapped[str] = mapped_column(String(200), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by_id: Mapped[uuid.UUID | None] = _user_fk()


class RbcmMappingRule(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "rbcm_mapping_rule"
    __table_args__ = (
        CheckConstraint(f"lifecycle_status IN ({_MAP_LIFE})", name="ck_rbcm_mapping_rule_life"),
    )

    mapping_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), _fk("rbcm_mapping_version.id"), nullable=False, index=True
    )
    cell_ref: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    match_type: Mapped[str] = mapped_column(String(16), nullable=False, default="EXACT")  # EXACT|PREFIX
    pattern: Mapped[str] = mapped_column(String(64), nullable=False)
    exclusions: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    amount_basis: Mapped[str] = mapped_column(String(16), nullable=False, default="SIGNED")
    signed_balance_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="NATURAL")
    sign_multiplier: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    provenance: Mapped[str] = mapped_column(String(32), nullable=False, default="CORRESPONDANCE")
    divergence_group: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lifecycle_status: Mapped[str] = mapped_column(String(16), nullable=False, default="A_VALIDER")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class RbcmMappingRuleSource(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "rbcm_mapping_rule_source"

    rule_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), _fk("rbcm_mapping_rule.id"), nullable=False, index=True
    )
    source_name: Mapped[str] = mapped_column(String(64), nullable=False)
    source_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RbcmUnmappedRubric(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """67 rubriques sans règle — jamais zéro automatique."""

    __tablename__ = "rbcm_unmapped_rubric"
    __table_args__ = (UniqueConstraint("cell_ref", name="uq_rbcm_unmapped_rubric_cell"),)

    cell_ref: Mapped[str] = mapped_column(String(32), nullable=False)
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="NON_RESOLUE")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class RbcmNcgOrientation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Orientation métier NCG → cellule SM. Alimente le catalogue central une fois VALIDE_ACTIF.

    Append-only logique : désactivation / rejet sans suppression. Jamais d'activation automatique.
    Générique (tous les mois), jamais liée à une campagne.
    """

    __tablename__ = "rbcm_ncg_orientation"
    __table_args__ = (
        CheckConstraint(f"status IN ({_NCG_ORI_STAT})", name="ck_rbcm_ncg_orientation_status"),
        CheckConstraint(f"operation IN ({_NCG_ORI_OPS})", name="ck_rbcm_ncg_orientation_operation"),
        CheckConstraint(f"currency_scope IN ({_NCG_ORI_CUR})", name="ck_rbcm_ncg_orientation_currency"),
        CheckConstraint(f"residence_scope IN ({_NCG_ORI_RES})", name="ck_rbcm_ncg_orientation_residence"),
        CheckConstraint(f"sheet IN ({_NCG_ORI_SHEET})", name="ck_rbcm_ncg_orientation_sheet"),
        Index(
            "ix_rbcm_ncg_orientation_active_key",
            "ncg",
            "cell_ref",
            "operation",
            "currency_scope",
        ),
    )

    ncg: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    ncg_libelle: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sheet: Mapped[str] = mapped_column(String(16), nullable=False)
    cell_ref: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    currency_scope: Mapped[str] = mapped_column(String(16), nullable=False, default="ALL")
    residence_scope: Mapped[str] = mapped_column(String(16), nullable=False, default="RESIDENTS")
    operation: Mapped[str | None] = mapped_column(String(16), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="A_ORIENTER", index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    prepared_by_id: Mapped[uuid.UUID | None] = _user_fk()
    prepared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    submitted_by_id: Mapped[uuid.UUID | None] = _user_fk()
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    validated_by_id: Mapped[uuid.UUID | None] = _user_fk()
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_by_id: Mapped[uuid.UUID | None] = _user_fk()
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deactivated_by_id: Mapped[uuid.UUID | None] = _user_fk()
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), _fk("rbcm_ncg_orientation.id", "SET NULL"), nullable=True
    )


class RbcmCalculationRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "rbcm_calculation_run"

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), _fk("rbcm_campaign.id"), nullable=False, index=True
    )
    engine_version: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="RUNNING")
    fingerprint_imports: Mapped[str | None] = mapped_column(String(64), nullable=True)
    fingerprint_mapping: Mapped[str | None] = mapped_column(String(64), nullable=True)
    fingerprint_params: Mapped[str | None] = mapped_column(String(64), nullable=True)
    fingerprint_template: Mapped[str | None] = mapped_column(String(64), nullable=True)
    started_by_id: Mapped[uuid.UUID | None] = _user_fk()
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    report: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class RbcmCellResult(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "rbcm_cell_result"
    __table_args__ = (UniqueConstraint("run_id", "cell_ref", name="uq_rbcm_cell_result_run_cell"),)

    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), _fk("rbcm_calculation_run.id"), nullable=False, index=True
    )
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), _fk("rbcm_campaign.id"), nullable=False, index=True
    )
    cell_ref: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    calculated_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    retained_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    value_status: Mapped[str] = mapped_column(String(32), nullable=False, default="NON_RENSEIGNE")
    traces: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RbcmCellDecision(UUIDPrimaryKeyMixin, Base):
    """Append-only strict — pas d'UPDATE des champs de fond."""

    __tablename__ = "rbcm_cell_decision"

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), _fk("rbcm_campaign.id"), nullable=False, index=True
    )
    cell_ref: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    calculation_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), _fk("rbcm_calculation_run.id", "SET NULL"), nullable=True
    )
    calculated_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    decided_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    decision_type: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_by_id: Mapped[uuid.UUID | None] = _user_fk()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    reviewed_by_id: Mapped[uuid.UUID | None] = _user_fk()
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    supersedes_decision_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), _fk("rbcm_cell_decision.id", "SET NULL"), nullable=True
    )


class RbcmEcartSnapshot(UUIDPrimaryKeyMixin, Base):
    """ECART calculé par campagne — jamais de constante 2 873 223 injectée."""

    __tablename__ = "rbcm_ecart_snapshot"
    __table_args__ = (
        CheckConstraint(f"state IN ({_ECART})", name="ck_rbcm_ecart_state"),
    )

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), _fk("rbcm_campaign.id"), nullable=False, index=True
    )
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), _fk("rbcm_calculation_run.id", "SET NULL"), nullable=True
    )
    amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    formula_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active_in_run: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    state: Mapped[str] = mapped_column(String(24), nullable=False, default="DESACTIVE")
    # Métadonnées documentaires uniquement (pas utilisées comme constante de calcul)
    historical_ref_2873223: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    historical_ref_2873218: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RbcmControlResult(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "rbcm_control_result"

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), _fk("rbcm_campaign.id"), nullable=False, index=True
    )
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), _fk("rbcm_calculation_run.id", "SET NULL"), nullable=True
    )
    control_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    result: Mapped[str] = mapped_column(String(16), nullable=False)  # OK | FAIL | SKIP
    justification: Mapped[str | None] = mapped_column(Text, nullable=True)
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class RbcmReportingOwnerHistory(UUIDPrimaryKeyMixin, Base):
    """Historique append-only des désignations de responsable du reporting."""

    __tablename__ = "rbcm_reporting_owner_history"

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), _fk("rbcm_campaign.id"), nullable=False, index=True
    )
    from_owner_id: Mapped[uuid.UUID | None] = _user_fk()
    to_owner_id: Mapped[uuid.UUID | None] = _user_fk()
    actor_id: Mapped[uuid.UUID | None] = _user_fk()
    motif: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RbcmValidationEvent(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "rbcm_validation_event"

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), _fk("rbcm_campaign.id"), nullable=False, index=True
    )
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(24), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(24), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor_id: Mapped[uuid.UUID | None] = _user_fk()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RbcmTemplate(UUIDPrimaryKeyMixin, Base):
    """Canevas officiel versionné — immuable (sha256 / stored_path jamais UPDATÉs)."""

    __tablename__ = "rbcm_template"
    __table_args__ = (
        UniqueConstraint("sha256", name="uq_rbcm_template_sha256"),
        UniqueConstraint("template_code", "version", name="uq_rbcm_template_code_version"),
        CheckConstraint("version >= 1", name="ck_rbcm_template_version"),
        CheckConstraint("status IN ('CURRENT','SUPERSEDED','ARCHIVED')", name="ck_rbcm_template_status"),
        Index(
            "uq_rbcm_template_current",
            "template_code",
            unique=True,
            postgresql_where=sa_text("status = 'CURRENT'"),
        ),
    )

    template_code: Mapped[str] = mapped_column(String(32), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    stored_path: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="CURRENT")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by_id: Mapped[uuid.UUID | None] = _user_fk()
    extra: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class RbcmTemplateCell(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "rbcm_template_cell"
    __table_args__ = (
        UniqueConstraint("template_id", "sheet_name", "excel_address", name="uq_rbcm_template_cell_addr"),
        UniqueConstraint("template_id", "document_cell_key", name="uq_rbcm_template_cell_key"),
        CheckConstraint(
            "nature IN ('HEADER','SEPARATOR','CANVAS_NORM','CANVAS_SCALE_FORMULA',"
            "'OCTOBER_LEAF','OCTOBER_CONSTANT_FORMULA','LEAF','STRUCTURAL_FORMULA',"
            "'D09_PCT','D09_REMAINDER','CONCORDANCE_IF','METIER_IF','RATIO_DIV')",
            name="ck_rbcm_template_cell_nature",
        ),
    )

    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), _fk("rbcm_template.id", "RESTRICT"), nullable=False, index=True
    )
    sheet_name: Mapped[str] = mapped_column(String(64), nullable=False)
    excel_address: Mapped[str] = mapped_column(String(8), nullable=False)
    document_cell_key: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    bcm_code: Mapped[str | None] = mapped_column(String(16), nullable=True)
    axis: Mapped[str | None] = mapped_column(String(4), nullable=True)
    nature: Mapped[str] = mapped_column(String(32), nullable=False)
    formula_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    writable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    completeness_group: Mapped[str | None] = mapped_column(String(32), nullable=True)
    extra: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class RbcmDeliverable(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "rbcm_deliverable"
    __table_args__ = (
        CheckConstraint(
            "(status = 'GENERATED' AND document_seq IS NULL AND template_id IS NULL) "
            "OR (status IN ('WORK', 'SUPERSEDED') AND document_seq IS NOT NULL "
            "AND document_seq >= 1 AND template_id IS NOT NULL)",
            name="ck_rbcm_deliverable_status_seq",
        ),
        Index(
            "uq_rbcm_deliverable_campaign_seq",
            "campaign_id",
            "document_seq",
            unique=True,
            postgresql_where=sa_text("document_seq IS NOT NULL"),
        ),
        Index(
            "uq_rbcm_deliverable_one_work",
            "campaign_id",
            unique=True,
            postgresql_where=sa_text("kind = 'EXCEL' AND status = 'WORK'"),
        ),
    )

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), _fk("rbcm_campaign.id"), nullable=False, index=True
    )
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), _fk("rbcm_calculation_run.id", "SET NULL"), nullable=True
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # EXCEL | PDF
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="GENERATED")
    warnings: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_by_id: Mapped[uuid.UUID | None] = _user_fk()
    template_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), _fk("rbcm_template.id", "RESTRICT"), nullable=True
    )
    document_seq: Mapped[int | None] = mapped_column(Integer, nullable=True)
    superseded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), _fk("rbcm_deliverable.id", "RESTRICT"), nullable=True
    )


class RbcmDocumentDecision(UUIDPrimaryKeyMixin, Base):
    """Décisions documentaires append-only — jamais dans rbcm_cell_result."""

    __tablename__ = "rbcm_document_decision"
    __table_args__ = (
        CheckConstraint(
            "decision_type IN ('ZERO_CONFIRME','ZERO_MANUEL','VALEUR_DECIDEE','RETRAIT')",
            name="ck_rbcm_document_decision_type",
        ),
        Index("ix_rbcm_document_decision_current", "campaign_id", "document_cell_key", "decided_at"),
    )

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), _fk("rbcm_campaign.id"), nullable=False, index=True
    )
    template_cell_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), _fk("rbcm_template_cell.id", "RESTRICT"), nullable=False
    )
    document_cell_key: Mapped[str] = mapped_column(String(32), nullable=False)
    deliverable_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), _fk("rbcm_deliverable.id", "RESTRICT"), nullable=True
    )
    calculation_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), _fk("rbcm_calculation_run.id", "SET NULL"), nullable=True
    )
    calculated_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    decided_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    decision_type: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    justificatif_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_by_id: Mapped[uuid.UUID | None] = _user_fk()
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    supersedes_decision_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), _fk("rbcm_document_decision.id", "RESTRICT"), nullable=True
    )
