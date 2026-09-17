from pydantic import BaseModel, EmailStr, Field

from app.schemas.auth import UserRead


class PlateformeModuleRead(BaseModel):
    id: str
    titre: str
    description: str
    route: str | None = None
    entry_path: str | None = None
    statut: str
    accessible: bool
    espace_id: str | None = None
    espace_titre: str | None = None
    espace_route: str | None = None


class PlateformeEspaceRead(BaseModel):
    id: str
    titre: str
    description: str
    route: str | None = None
    statut: str
    accessible: bool
    modules: list[PlateformeModuleRead] = Field(default_factory=list)


class CorePermissionRead(BaseModel):
    code: str
    label: str
    module: str


class CoreRoleRead(BaseModel):
    code: str
    label: str
    description: str
    permission_codes: list[str] = Field(default_factory=list)


class CoreGedStatus(BaseModel):
    statut: str
    table: str
    storage: str


class CoreManifestRead(BaseModel):
    """Inventaire du CORE commun à tous les départements."""

    chain: str
    espaces: list[PlateformeEspaceRead]
    permissions: list[CorePermissionRead]
    roles: list[CoreRoleRead]
    ged: CoreGedStatus


class CoreAdminKpi(BaseModel):
    utilisateurs: int
    utilisateurs_actifs: int
    departements: int
    modules: int
    modules_actifs: int
    sessions_actives: int
    alertes_securite: int
    actions_aujourd_hui: int


class CoreAdminActivityItem(BaseModel):
    id: str
    who: str
    email: str | None = None
    action: str
    entity: str
    entity_id: str | None = None
    module: str | None = None
    espace: str | None = None
    created_at: str | None = None


class CoreAdminHealthItem(BaseModel):
    ok: bool
    label: str


class CoreAdminDashboardRead(BaseModel):
    kpis: CoreAdminKpi
    activite: list[CoreAdminActivityItem] = Field(default_factory=list)
    etat: dict[str, CoreAdminHealthItem] = Field(default_factory=dict)
    fuseau: str = "Africa/Nouakchott"


class CoreAdminUserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=8)
    phone: str | None = Field(default=None, max_length=40)
    is_superuser: bool = False
    role_codes: list[str] = Field(default_factory=list)
    espace_codes: list[str] = Field(default_factory=list)
    module_codes: list[str] = Field(default_factory=list)


class CoreAdminUserUpdate(BaseModel):
    email: EmailStr | None = None
    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    phone: str | None = None
    password: str | None = Field(default=None, min_length=8)
    is_superuser: bool | None = None
    role_codes: list[str] | None = None
    espace_codes: list[str] | None = None
    module_codes: list[str] | None = None


class CoreAdminResetAccess(BaseModel):
    password: str = Field(min_length=8)


class CoreAdminUserSession(BaseModel):
    id: str
    kind: str
    module_code: str | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    created_at: str | None = None
    expires_at: str | None = None
    revoked_at: str | None = None
    active: bool


class CoreAdminUserFiche(UserRead):
    sessions: list[CoreAdminUserSession] = Field(default_factory=list)
    activite: list[CoreAdminActivityItem] = Field(default_factory=list)


class CoreAdminUserKpis(BaseModel):
    total: int
    actifs: int
    inactifs: int
    superusers: int
    totp: int
    jamais_connectes: int


class CoreAdminUserListRead(BaseModel):
    items: list[UserRead]
    total: int
    page: int
    size: int
    kpis: CoreAdminUserKpis
