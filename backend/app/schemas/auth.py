from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from app.schemas.common import ORMModel


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    totp_code: str | None = Field(default=None, max_length=8)


class RefreshRequest(BaseModel):
    refresh_token: str


class RoleRead(ORMModel):
    id: UUID
    code: str
    label: str


class PermissionRead(ORMModel):
    id: UUID
    code: str
    label: str
    module: str


class UserRead(ORMModel):
    id: UUID
    email: EmailStr
    full_name: str
    is_superuser: bool
    is_active: bool
    roles: list[RoleRead] = []
    agence_id: UUID | None = None
    last_login_at: datetime | None = None
    totp_enabled: bool = False


class TotpSetupResponse(BaseModel):
    secret: str
    otpauth_url: str
    qr_image_base64: str


class TotpEnableRequest(BaseModel):
    code: str = Field(min_length=6, max_length=8)


class TotpDisableRequest(BaseModel):
    code: str = Field(min_length=6, max_length=8)
    password: str = Field(min_length=8)


class TotpStatusResponse(BaseModel):
    enabled: bool
    pending_setup: bool


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str
    password: str = Field(min_length=8)
    role_codes: list[str] = Field(default_factory=list)
    is_superuser: bool = False
    agence_id: UUID | None = None


class UserUpdate(BaseModel):
    email: EmailStr | None = None
    full_name: str | None = None
    phone: str | None = None
    password: str | None = Field(default=None, min_length=8)
    is_active: bool | None = None
    is_superuser: bool | None = None
    role_codes: list[str] | None = None
    agence_id: UUID | None = None


class ImmobilisationImportResponse(BaseModel):
    created: int
    errors: list[str]


class BankImmoImportResponse(BaseModel):
    created: int
    amortissements_created: int
    errors: list[str]
    totaux_par_compte: list[dict]
    reports_created: int = 0
    negatives: int = 0


class BankImmoPurgeResponse(BaseModel):
    deleted: int
    message: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8)


class ForgotPasswordResponse(BaseModel):
    message: str
    reset_token: str | None = None
    account_found: bool = False
    dev_mode: bool = False
    expires_in_seconds: int | None = None


class RoleCreate(BaseModel):
    code: str
    label: str
    description: str | None = None
    permission_codes: list[str] = Field(default_factory=list)
