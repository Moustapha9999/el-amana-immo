from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.models.enums import TypeNotification
from app.schemas.common import ORMModel


class NotificationRead(ORMModel):
    id: UUID
    type_notification: TypeNotification
    titre: str
    message: str
    lu: bool
    created_at: datetime


class AuditLogRead(ORMModel):
    id: UUID
    user_id: UUID | None
    user_email: str | None = None
    action: str
    entity: str
    entity_id: str | None
    ip_address: str | None
    created_at: datetime


class DashboardKpi(BaseModel):
    nombre_immobilisations: int
    valeur_brute_totale: float
    vnc_totale: float
    dotation_periode: float
    annee_reference: int


class DashboardChartPoint(BaseModel):
    label: str
    value: float
    key: str = ""


class DashboardFiltresActifs(BaseModel):
    statut: str | None = None
    famille: str | None = None
    mois: int | None = None


class DashboardComposition(BaseModel):
    valeur_brute: float
    cumul_amortissement: float
    vnc: float


class DashboardCharts(BaseModel):
    par_statut: list[DashboardChartPoint]
    par_famille: list[DashboardChartPoint]
    dotations_mensuelles: list[DashboardChartPoint]
    evolution_vnc: list[DashboardChartPoint]
    composition: DashboardComposition
    filtres_actifs: DashboardFiltresActifs
