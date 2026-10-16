import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, Column, DateTime, Float, String, Text

from foreguard.db.base import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class RequestLog(Base):
    """
    Persiste cada requisição analisada pelo Foreguard.
    Serve para auditoria, análise forense e retreinamento do modelo.
    """
    __tablename__ = "request_logs"

    id          = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    timestamp   = Column(DateTime(timezone=True), default=_utcnow, nullable=False, index=True)

    # Dados da requisição
    method      = Column(String(10), nullable=False)
    path        = Column(Text, nullable=False)
    ip          = Column(String(45), nullable=False, index=True)
    user_agent  = Column(Text, nullable=True)

    # Resultado da análise
    risk_score  = Column(Float, nullable=False)
    risk_level  = Column(String(10), nullable=False, index=True)
    reasons     = Column(JSON, nullable=False, default=list)

    # Payload completo (para auditoria)
    raw_request = Column(JSON, nullable=True)

    def __repr__(self):
        return f"<RequestLog id={self.id} score={self.risk_score} level={self.risk_level}>"
