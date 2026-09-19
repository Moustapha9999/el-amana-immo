from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field

from app.schemas.auth import UserRead


class PlateformeModuleRead(BaseModel):
    id: str
    titre: str
    description: str
    route: str | None = None
    entry_path: str | None = None
    statut: str
    status_message: str = ""
    version: str | None = None
    access_allowed: bool | None = None
    block_reason: str | None = None
    maintenance_ends_at: str | None = None
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


class PlateformeHubModuleRead(BaseModel):
    id: str
    titre: str
    description: str | None = None
    route: str | None = None
    entry_path: str | None = None
    statut: str
    status_message: str = ""
    accessible: bool | None = None
    espace_id: str | None = None
    espace_titre: str | None = None
    espace_route: str | None = None


class PlateformeHubEtatRead(BaseModel):
    ok: bool
    departements: int
    modules: int
    modules_actifs: int
    maintenance: int
    developpement: int
    suspendus: int
    par_statut: dict[str, int] = Field(default_factory=dict)


class PlateformeHubKpiRead(BaseModel):
    key: str
    label: str
    value: int
    hint: str | None = None


class PlateformeHubComponentEtatRead(BaseModel):
    key: str
    label: str
    ok: bool | None = None
    status: str
    status_label: str


class PlateformeHubEtatPlateformeRead(BaseModel):
    ok: bool
    verifie_at: str
    fuseau: str = "Africa/Nouakchott"
    components: list[PlateformeHubComponentEtatRead] = Field(default_factory=list)


class PlateformeHubSeriePointRead(BaseModel):
    date: str
    label: str
    count: int


class PlateformeHubSummaryRead(BaseModel):
    vue: str = "utilisateur"
    user_full_name: str | None = None
    departements_accessibles: int
    departements_visibles: int
    modules_accessibles: int
    modules_ouverts: int
    notifications_non_lues: int
    sessions_actives: int = 0
    kpis: list[PlateformeHubKpiRead] = Field(default_factory=list)
    plateforme: PlateformeHubEtatRead
    etat_plateforme: PlateformeHubEtatPlateformeRead | None = None
    activite_jours: int = 7
    activite_serie: list[PlateformeHubSeriePointRead] = Field(default_factory=list)
    mes_modules: list[PlateformeHubModuleRead] = Field(default_factory=list)
    modules_recents: list[PlateformeHubModuleRead] = Field(default_factory=list)


class PlateformeHubActivityRead(BaseModel):
    id: str
    action: str
    entity: str
    entity_id: str | None = None
    espace_code: str | None = None
    module_code: str | None = None
    created_at: str | None = None
    who: str | None = None
    label: str


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
    notifications_non_lues: int = 0
    documents_ged: int = 0


class CoreAdminChartPoint(BaseModel):
    label: str
    key: str
    value: int


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


class CoreAdminDashboardCharts(BaseModel):
    activite_7j: list[CoreAdminChartPoint] = Field(default_factory=list)
    sessions: list[CoreAdminChartPoint] = Field(default_factory=list)
    connexions: list[CoreAdminChartPoint] = Field(default_factory=list)
    modules: list[CoreAdminChartPoint] = Field(default_factory=list)


class CoreAdminDashboardRead(BaseModel):
    kpis: CoreAdminKpi
    charts: CoreAdminDashboardCharts = Field(default_factory=CoreAdminDashboardCharts)
    activite: list[CoreAdminActivityItem] = Field(default_factory=list)
    etat: dict[str, CoreAdminHealthItem] = Field(default_factory=dict)
    fuseau: str = "Africa/Nouakchott"
    app_name: str = "BEA DIGITAL"
    ops: dict | None = None


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


class CoreAdminCatalogueKpis(BaseModel):
    total: int
    actifs: int
    bientot: int
    inactifs: int


class CoreAdminEspaceWrite(BaseModel):
    code: str = Field(min_length=2, max_length=80)
    label: str = Field(min_length=1, max_length=120)
    description: str = ""
    route: str | None = Field(default=None, max_length=160)
    statut: Literal["actif", "bientot", "inactif"] = "bientot"
    sort_order: int = Field(default=0, ge=0, le=9999)


class CoreAdminEspaceUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None
    route: str | None = Field(default=None, max_length=160)
    statut: Literal["actif", "bientot", "inactif"] | None = None
    sort_order: int | None = Field(default=None, ge=0, le=9999)


class CoreAdminModuleSummary(BaseModel):
    id: str
    code: str
    label: str
    statut: str
    is_active: bool
    locked: bool


class CoreAdminEspaceRead(BaseModel):
    id: str
    code: str
    label: str
    description: str
    route: str | None = None
    statut: str
    sort_order: int
    is_active: bool
    locked: bool
    modules_count: int = 0
    users_count: int = 0
    created_at: str | None = None
    updated_at: str | None = None


class CoreAdminEspaceFiche(CoreAdminEspaceRead):
    modules: list[CoreAdminModuleSummary] = Field(default_factory=list)


class CoreAdminEspaceListRead(BaseModel):
    items: list[CoreAdminEspaceRead]
    total: int
    page: int
    size: int
    kpis: CoreAdminCatalogueKpis


ModuleStatut = Literal[
    "actif",
    "bientot",
    "inactif",
    "developpement",
    "mise_a_jour",
    "maintenance",
    "suspendu",
    "bloque",
    "archive",
]


class CoreAdminModuleWrite(BaseModel):
    code: str = Field(min_length=2, max_length=80)
    espace_id: str
    label: str = Field(min_length=1, max_length=160)
    description: str = ""
    entry_path: str | None = Field(default=None, max_length=160)
    statut: ModuleStatut = "bientot"
    sort_order: int = Field(default=0, ge=0, le=9999)


class CoreAdminModuleUpdate(BaseModel):
    espace_id: str | None = None
    label: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = None
    entry_path: str | None = Field(default=None, max_length=160)
    statut: ModuleStatut | None = None
    sort_order: int | None = Field(default=None, ge=0, le=9999)


class CoreAdminModuleRead(BaseModel):
    id: str
    code: str
    label: str
    description: str
    entry_path: str | None = None
    statut: str
    status_message: str = ""
    version: str = "1.0.0"
    sort_order: int
    is_active: bool
    locked: bool
    espace_id: str
    espace_code: str
    espace_label: str
    users_count: int = 0
    created_at: str | None = None
    updated_at: str | None = None


class PlatformBackupCreate(BaseModel):
    level: Literal["global", "departement", "module"]
    backup_type: Literal[
        "automatique",
        "manuelle",
        "avant_maintenance",
        "avant_mise_a_jour",
        "avant_migration",
        "securite_recovery",
    ] = "manuelle"
    espace_code: str | None = None
    module_code: str | None = None
    label: str | None = None


class PlatformRestoreRequest(BaseModel):
    acknowledge_dependencies: bool = False


class ModuleStatusUpdate(BaseModel):
    statut: ModuleStatut
    status_message: str | None = None
    maintenance_starts_at: datetime | None = None
    maintenance_ends_at: datetime | None = None
    admins_bypass_maintenance: bool | None = None
    notify: bool = True


class GlobalMaintenanceUpdate(BaseModel):
    enabled: bool
    title: str = ""
    message: str = ""
    ends_at: str | None = None
    admins_bypass: bool = True


class ModuleVersionCreate(BaseModel):
    version: str = Field(min_length=1, max_length=40)
    notes: str = ""
    set_current: bool = True
    create_backup: bool = True
    activate_maintenance: bool = False


class CoreAdminModuleListRead(BaseModel):
    items: list[CoreAdminModuleRead]
    total: int
    page: int
    size: int
    kpis: CoreAdminCatalogueKpis


class CoreAdminEspaceOption(BaseModel):
    id: str
    code: str
    label: str
    is_active: bool


class CoreAdminModuleOptions(BaseModel):
    espaces: list[CoreAdminEspaceOption] = Field(default_factory=list)


class CoreAdminRbacKpis(BaseModel):
    total: int
    systeme: int
    custom: int
    with_users: int = 0
    unused: int = 0


class CoreAdminRoleWrite(BaseModel):
    code: str = Field(min_length=2, max_length=50)
    label: str = Field(min_length=1, max_length=120)
    description: str = ""
    permission_codes: list[str] = Field(default_factory=list)


class CoreAdminRoleUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None
    permission_codes: list[str] | None = None


class CoreAdminPermissionSummary(BaseModel):
    id: str
    code: str
    label: str
    module: str
    locked: bool


class CoreAdminRoleSummary(BaseModel):
    id: str
    code: str
    label: str
    locked: bool


class CoreAdminRoleRead(BaseModel):
    id: str
    code: str
    label: str
    description: str
    locked: bool
    permissions_count: int = 0
    users_count: int = 0
    created_at: str | None = None
    updated_at: str | None = None


class CoreAdminRoleFiche(CoreAdminRoleRead):
    permission_codes: list[str] = Field(default_factory=list)
    permissions: list[CoreAdminPermissionSummary] = Field(default_factory=list)


class CoreAdminRoleListRead(BaseModel):
    items: list[CoreAdminRoleRead]
    total: int
    page: int
    size: int
    kpis: CoreAdminRbacKpis


class CoreAdminPermissionWrite(BaseModel):
    code: str = Field(min_length=3, max_length=100)
    label: str = Field(min_length=1, max_length=255)
    module: str | None = Field(default=None, max_length=80)


class CoreAdminPermissionUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=255)
    module: str | None = Field(default=None, min_length=1, max_length=80)


class CoreAdminPermissionRead(BaseModel):
    id: str
    code: str
    label: str
    module: str
    locked: bool
    roles_count: int = 0
    created_at: str | None = None
    updated_at: str | None = None


class CoreAdminPermissionFiche(CoreAdminPermissionRead):
    roles: list[CoreAdminRoleSummary] = Field(default_factory=list)


class CoreAdminPermissionListRead(BaseModel):
    items: list[CoreAdminPermissionRead]
    total: int
    page: int
    size: int
    kpis: CoreAdminRbacKpis


class CoreAdminRoleOptions(BaseModel):
    permissions: list[CoreAdminPermissionSummary] = Field(default_factory=list)
    modules: list[str] = Field(default_factory=list)


class CoreAdminPermissionOptions(BaseModel):
    modules: list[str] = Field(default_factory=list)


class CoreAdminMatrixKpis(BaseModel):
    roles: int
    permissions: int
    grants: int
    modules: int


class CoreAdminMatrixRead(BaseModel):
    roles: list[CoreAdminRoleSummary] = Field(default_factory=list)
    permissions: list[CoreAdminPermissionSummary] = Field(default_factory=list)
    grants: dict[str, list[str]] = Field(default_factory=dict)
    modules: list[str] = Field(default_factory=list)
    kpis: CoreAdminMatrixKpis


class CoreAdminMatrixGrantUpdate(BaseModel):
    role_id: str
    permission_code: str
    granted: bool


class CoreAdminMatrixGrantResult(BaseModel):
    role_id: str
    permission_code: str
    granted: bool


class CoreAdminSessionKpis(BaseModel):
    total: int
    actives: int
    platform: int
    module: int
    expirees: int
    revoquees: int


class CoreAdminSessionRead(BaseModel):
    id: str
    user_id: str
    user_email: str
    user_full_name: str
    kind: str
    module_code: str | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    created_at: str | None = None
    expires_at: str | None = None
    revoked_at: str | None = None
    active: bool
    is_current: bool = False


class CoreAdminSessionListRead(BaseModel):
    items: list[CoreAdminSessionRead]
    total: int
    page: int
    size: int
    kpis: CoreAdminSessionKpis
    current_session_id: str | None = None


class CoreAdminAuditKpis(BaseModel):
    total: int
    aujourd_hui: int
    logins: int
    mutations: int
    core: int


class CoreAdminAuditRead(BaseModel):
    id: str
    user_id: str | None = None
    user_email: str | None = None
    user_full_name: str | None = None
    action: str
    entity: str
    entity_id: str | None = None
    ip_address: str | None = None
    espace_code: str | None = None
    module_code: str | None = None
    session_id: str | None = None
    created_at: str | None = None


class CoreAdminAuditListRead(BaseModel):
    items: list[CoreAdminAuditRead]
    total: int
    page: int
    size: int
    kpis: CoreAdminAuditKpis
    modules: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)


class CoreAdminActivityKpis(BaseModel):
    total: int
    derniere_heure: int
    aujourd_hui: int
    modules: int


class CoreAdminActivityListRead(BaseModel):
    items: list[CoreAdminAuditRead]
    total: int
    page: int
    size: int
    kpis: CoreAdminActivityKpis


class CoreAdminAlertKpis(BaseModel):
    total: int
    echecs_fenetre: int
    succes_fenetre: int
    emails_suspects: int


class CoreAdminAlertRead(BaseModel):
    id: str
    email: str
    ip_address: str | None = None
    login_kind: str
    module_code: str | None = None
    success: bool
    created_at: str | None = None


class CoreAdminAlertListRead(BaseModel):
    items: list[CoreAdminAlertRead]
    total: int
    page: int
    size: int
    kpis: CoreAdminAlertKpis
    lockout_window_minutes: int
    lockout_max_failures: int


class CoreAdminNotificationKpis(BaseModel):
    total: int
    non_lues: int
    lues: int
    alertes: int = 0
    critiques: int = 0
    systeme: int = 0
    categories: dict[str, str] = {}
    priorites: dict[str, str] = {}


class CoreAdminNotificationRead(BaseModel):
    id: str
    user_id: str
    user_email: str | None = None
    user_full_name: str | None = None
    type_notification: str
    titre: str
    message: str
    lu: bool
    archived: bool = False
    entity: str | None = None
    entity_id: str | None = None
    espace_code: str | None = None
    module_code: str | None = None
    categorie: str = "systeme"
    categorie_label: str = "Système"
    priorite: str = "info"
    priorite_label: str = "Info"
    event_type: str | None = None
    event_code: str | None = None
    emetteur_type: str = "systeme"
    emetteur_label: str = "Système"
    destinataire_type: str = "utilisateur"
    destinataire_label: str | None = None
    created_at: str | None = None


class CoreAdminNotificationListRead(BaseModel):
    items: list[CoreAdminNotificationRead]
    total: int
    page: int
    size: int
    kpis: CoreAdminNotificationKpis


class CoreAdminGedKpis(BaseModel):
    total: int
    modules: int
    taille_octets: int
    reservee: bool = True


class CoreAdminGedRead(BaseModel):
    id: str
    espace_code: str
    module_code: str
    entity: str
    entity_id: str
    filename: str
    mime_type: str | None = None
    size_bytes: int
    uploaded_by_id: str | None = None
    created_at: str | None = None


class CoreAdminGedListRead(BaseModel):
    items: list[CoreAdminGedRead]
    total: int
    page: int
    size: int
    kpis: CoreAdminGedKpis


class CoreAdminGeneralSettings(BaseModel):
    app_name: str
    app_env: str
    app_debug: bool
    api_v1_prefix: str
    fuseau: str = "Africa/Nouakchott"
    cors_origins: list[str] = Field(default_factory=list)
    upload_dir: str
    ged_dir: str
    access_token_expire_minutes: int
    refresh_token_expire_days: int
    module_refresh_token_expire_minutes: int


class CoreAdminSecuritySettings(BaseModel):
    login_lockout_window_minutes: int
    login_lockout_max_failures: int
    jwt_algorithm: str
    alertes_fenetre: int
    sessions_actives: int
    sessions_platform: int = 0
    sessions_module: int = 0
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 1
    module_refresh_token_expire_minutes: int = 45
    password_policy: dict = Field(default_factory=dict)
    mfa_required_for_core_admin: bool = False
    mfa_users_enabled: int = 0
    mfa_admins_without: int = 0
    rate_limit_enabled: bool = True
    rate_limit: dict = Field(default_factory=dict)
    security_headers_enabled: bool = True
    api_docs_enabled: bool = False
    cors_origins: list[str] = Field(default_factory=list)
    database_ssl: str = "non_verifie"
    secret_key_status: str = "configure"
    upload_dir_exists: bool = False
    ged_dir_exists: bool = False
    app_env: str = "development"
    app_debug: bool = False
    comptes_verrouilles: list[dict] = Field(default_factory=list)
    etat: dict[str, CoreAdminHealthItem] = Field(default_factory=dict)
    fuseau: str = "Africa/Nouakchott"
    verifie_at: str | None = None
    policy_source: str | None = None
    policy_updated_at: str | None = None
    policy_editable: bool = True


class CoreAdminSecurityPolicyUpdate(BaseModel):
    """PATCH politique — confirmation_phrase doit être CONFIRMER."""

    confirmation_phrase: str = Field(min_length=1, max_length=40)
    login_lockout_window_minutes: int | None = Field(default=None, ge=1, le=1440)
    login_lockout_max_failures: int | None = Field(default=None, ge=1, le=50)
    password_min_length: int | None = Field(default=None, ge=8, le=128)
    password_require_uppercase: bool | None = None
    password_require_lowercase: bool | None = None
    password_require_digit: bool | None = None
    password_require_special: bool | None = None
    mfa_required_for_core_admin: bool | None = None
    rate_limit_enabled: bool | None = None
    rate_limit_login_per_minute: int | None = Field(default=None, ge=1, le=10000)
    rate_limit_api_per_minute: int | None = Field(default=None, ge=1, le=10000)
    rate_limit_sensitive_per_minute: int | None = Field(default=None, ge=1, le=10000)
    rate_limit_password_reset_per_minute: int | None = Field(default=None, ge=1, le=10000)


class CoreAdminSecurityCheckItem(BaseModel):
    key: str
    label: str
    status: Literal["ok", "warn", "ko"]
    detail: str


class CoreAdminSecurityCheckRead(BaseModel):
    items: list[CoreAdminSecurityCheckItem] = Field(default_factory=list)
    ok_count: int = 0
    warn_count: int = 0
    ko_count: int = 0
    verifie_at: str
    fuseau: str = "Africa/Nouakchott"


class CoreAdminMaintenanceSettings(BaseModel):
    db_ok: bool
    skip_migrations: bool
    modules_actifs: int
    modules_total: int
    sessions_actives: int
    upload_dir_exists: bool
    ged_dir_exists: bool
    app_env: str
    etat: dict[str, CoreAdminHealthItem] = Field(default_factory=dict)
