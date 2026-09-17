from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, model_validator

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


class LogoutRequest(BaseModel):
    refresh_token: str | None = None


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
    phone: str | None = None
    is_superuser: bool
    is_active: bool
    roles: list[RoleRead] = []
    agence_id: UUID | None = None
    last_login_at: datetime | None = None
    created_at: datetime | None = None
    totp_enabled: bool = False
    espace_codes: list[str] = Field(default_factory=list)
    module_codes: list[str] = Field(default_factory=list)
    permission_codes: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def extract_access_codes(cls, data: Any) -> Any:
        if isinstance(data, dict):
            return data
        espaces = getattr(data, "espaces", None) or []
        modules = getattr(data, "modules", None) or []
        from app.services.permission_service import permission_codes_from_user

        perms = sorted(c for c in permission_codes_from_user(data) if c != "*")
        return {
            "id": data.id,
            "email": data.email,
            "full_name": data.full_name,
            "phone": getattr(data, "phone", None),
            "is_superuser": data.is_superuser,
            "is_active": data.is_active,
            "roles": data.roles,
            "agence_id": data.agence_id,
            "last_login_at": data.last_login_at,
            "created_at": getattr(data, "created_at", None),
            "totp_enabled": bool(data.totp_enabled),
            "espace_codes": [e.code for e in espaces],
            "module_codes": [m.code for m in modules],
            "permission_codes": perms,
        }


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
    phone: str | None = Field(default=None, max_length=40)
    role_codes: list[str] = Field(default_factory=list)
    is_superuser: bool = False
    agence_id: UUID | None = None
    espace_codes: list[str] | None = None
    module_codes: list[str] | None = None


class UserUpdate(BaseModel):
    email: EmailStr | None = None
    full_name: str | None = None
    phone: str | None = None
    password: str | None = Field(default=None, min_length=8)
    is_active: bool | None = None
    is_superuser: bool | None = None
    role_codes: list[str] | None = None
    agence_id: UUID | None = None
    espace_codes: list[str] | None = None
    module_codes: list[str] | None = None


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
