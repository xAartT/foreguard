from datetime import UTC, datetime
from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

RISK_LEVELS = ("LOW", "MEDIUM", "HIGH", "CRITICAL")


class IncomingRequest(BaseModel):
    method:       str
    path:         str
    headers:      dict[str, str | list[str]]
    body:         Any                               = None   # qualquer JSON
    query_params: dict[str, str | list[str]] | None = None
    ip:           str
    user_agent:   str | None                        = None
    jwt_token:    str | None                        = None

    model_config = {"json_schema_extra": {
        "example": {
            "method": "POST",
            "path": "/login",
            "headers": {"content-type": "application/json", "user-agent": "Mozilla/5.0"},
            "body": {"username": "admin", "password": "' OR '1'='1"},
            "query_params": {},
            "ip": "192.168.1.100",
            "user_agent": "Mozilla/5.0",
            "jwt_token": None
        }
    }}


class AnalysisResponse(BaseModel):
    log_id:          str
    timestamp:       datetime
    risk_score:      float = Field(..., ge=0.0, le=10.0)
    risk_level:      str   = Field(..., pattern="^(LOW|MEDIUM|HIGH|CRITICAL)$")
    reasons:         list[str]
    recommendation:  str
    analysis_source: str


class LogSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    log_id:     str = Field(validation_alias=AliasChoices("log_id", "id"))
    timestamp:  datetime
    method:     str
    path:       str
    ip:         str
    risk_score: float
    risk_level: str
    reasons:    list[str]

    @field_validator("timestamp")
    @classmethod
    def _as_utc(cls, value: datetime) -> datetime:
        # Bancos sem fuso (SQLite) devolvem datetime naive gravado em UTC
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


class LogDetail(LogSummary):
    user_agent:  str | None
    raw_request: Any | None
