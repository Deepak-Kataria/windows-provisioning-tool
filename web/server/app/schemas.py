"""Pydantic request/response models."""
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Role = Literal["viewer", "technician", "admin"]


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class CodeIn(BaseModel):
    code: str = Field(min_length=6, max_length=12)


class LoginOut(BaseModel):
    next: Literal["mfa", "mfa_setup", "done"]
    csrf_token: str


class MfaSetupOut(BaseModel):
    secret: str
    otpauth_uri: str
    qr_svg: str = ""  # data: URI of an SVG QR code for the authenticator app


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    display_name: str
    role: Role
    is_active: bool
    totp_confirmed: bool
    must_change_password: bool
    created_at: datetime
    last_login_at: datetime | None
    locked_until: datetime | None


class MeOut(BaseModel):
    user: UserOut
    csrf_token: str


class UserCreateIn(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9._-]+$")
    display_name: str = Field(default="", max_length=128)
    role: Role = "viewer"
    password: str = Field(min_length=1, max_length=256)


class UserUpdateIn(BaseModel):
    display_name: str | None = Field(default=None, max_length=128)
    role: Role | None = None
    is_active: bool | None = None


class PasswordResetIn(BaseModel):
    password: str = Field(min_length=1, max_length=256)


class PasswordChangeIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)


class EnrollmentCodeIn(BaseModel):
    label: str = Field(default="", max_length=128)


class EnrollmentCodeOut(BaseModel):
    id: int
    code: str  # shown once
    label: str
    expires_at: datetime


class EnrollmentCodeInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    label: str
    created_at: datetime
    expires_at: datetime
    used_at: datetime | None
    machine_id: str | None


class AgentEnrollIn(BaseModel):
    code: str = Field(min_length=16, max_length=32)
    hostname: str = Field(min_length=1, max_length=255)
    agent_version: str = Field(default="", max_length=32)
    os_info: dict[str, Any] = Field(default_factory=dict)


class AgentEnrollOut(BaseModel):
    machine_id: str
    token: str
    heartbeat_seconds: int


class MachineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    hostname: str
    label: str
    enrolled_at: datetime
    last_seen_at: datetime | None
    last_ip: str
    agent_version: str
    os_info: dict[str, Any]
    revoked_at: datetime | None
    online: bool = False


class MachineUpdateIn(BaseModel):
    label: str | None = Field(default=None, max_length=128)


class JobCreateIn(BaseModel):
    action: str = Field(min_length=1, max_length=64)
    params: dict[str, Any] = Field(default_factory=dict)


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    machine_id: str
    action_id: str
    params: dict[str, Any]
    status: str
    created_by: int | None
    created_at: datetime
    sent_at: datetime | None
    started_at: datetime | None
    finished_at: datetime | None
    exit_code: int | None
    result: dict[str, Any] | None
    error: str


class JobLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    seq: int
    stream: str
    data: str
    ts: datetime


class AuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ts: datetime
    user_id: int | None
    username: str
    machine_id: str | None
    event: str
    detail: dict[str, Any]
    ip: str


class ActionOut(BaseModel):
    id: str
    title: str
    description: str
    min_role: Role
    params_schema: dict[str, Any]
    secret_params: list[str]
    timeout_seconds: int
