"""Pydantic request/response models for API contract v1.

Field names stay snake_case exactly as documented in docs/API-CONTRACT.md.
Additive changes only.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

API_VERSION = 1


class HealthResponse(BaseModel):
    status: str
    app: str
    version: str
    api: int
    platform: str
    model: str | None = None
    engine: str | None = None
    capabilities: list[str] = Field(default_factory=list)
    paired_devices: int = 0
    uptime_s: int = 0


class PairClaimRequest(BaseModel):
    device_id: str = Field(min_length=8, max_length=64)
    device_name: str = Field(min_length=1, max_length=64)
    pin: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")
    app_version: str = Field(default="", max_length=32)
    api: int = API_VERSION

    @model_validator(mode="after")
    def _api_version(self) -> PairClaimRequest:
        if self.api != API_VERSION:
            raise ValueError("Unsupported API version")
        return self


class QrClaimRequest(BaseModel):
    qr_token: str = Field(min_length=8, max_length=128)
    device_id: str = Field(min_length=8, max_length=64)
    device_name: str = Field(min_length=1, max_length=64)
    app_version: str = Field(default="", max_length=32)
    api: int = API_VERSION

    @model_validator(mode="after")
    def _api_version(self) -> QrClaimRequest:
        if self.api != API_VERSION:
            raise ValueError("Unsupported API version")
        return self


class PairResponse(BaseModel):
    token: str
    expires_at: int
    laptop_name: str
    api: int = API_VERSION
    host: str
    port: int


class RefreshRequest(BaseModel):
    device_id: str = Field(min_length=8, max_length=64)


class RefreshResponse(BaseModel):
    token: str
    expires_at: int


class DeviceInfo(BaseModel):
    device_id: str
    name: str
    paired_at: int
    last_seen: int
    current: bool = False


class DevicesResponse(BaseModel):
    devices: list[DeviceInfo]


class RevokeResponse(BaseModel):
    revoked: bool


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=12000)


class ChatRequest(BaseModel):
    conversation_id: str = Field(min_length=1, max_length=128)
    persona: Literal["maya", "teacher"] = "maya"
    messages: list[ChatMessage] = Field(min_length=1, max_length=24)

    @model_validator(mode="after")
    def _total_chars(self) -> ChatRequest:
        if sum(len(message.content) for message in self.messages) > 12000:
            raise ValueError("Conversation too large")
        return self


class PendingActionInfo(BaseModel):
    confirm_token: str
    description: str
    action: str
    expires_in: int


class ChatResponse(BaseModel):
    conversation_id: str
    reply: str
    model: str | None = None
    engine: str | None = None
    elapsed_ms: int = 0
    pending_action: PendingActionInfo | None = None


class VoiceTtsRequest(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    engine: Literal["sapi", "piper", "auto"] = "auto"
    voice: str | None = Field(default=None, max_length=64)
    lang: str = Field(default="en", max_length=16)
    speed: float = Field(default=1.0, ge=0.5, le=2.0)


class PcCommandRequest(BaseModel):
    action: str = Field(min_length=1, max_length=64)
    params: dict[str, Any] = Field(default_factory=dict)
    confirm_token: str | None = Field(default=None, max_length=128)


class PcCommandResponse(BaseModel):
    status: str
    result: dict[str, Any] | None = None
    reason: str | None = None
    confirm_token: str | None = None
    description: str | None = None
    expires_in: int | None = None


class PcConfirmRequest(BaseModel):
    confirm_token: str = Field(min_length=8, max_length=128)


class PcCancelRequest(BaseModel):
    confirm_token: str = Field(min_length=8, max_length=128)


class WakeStatusResponse(BaseModel):
    listening: bool
    clap: bool = True
    name: bool = True


class WakeListenRequest(BaseModel):
    seconds: int = Field(default=60, ge=1, le=300)


class WakeListenResponse(BaseModel):
    listening: bool
    expires_at: int


class WakeStopResponse(BaseModel):
    listening: bool
