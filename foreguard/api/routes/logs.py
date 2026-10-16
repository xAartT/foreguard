from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc
from sqlalchemy.orm import Session

from foreguard.api.schemas import RISK_LEVELS, LogDetail, LogSummary
from foreguard.db.models import RequestLog
from foreguard.db.session import get_db

router = APIRouter()


@router.get("/logs", response_model=list[LogSummary])
def list_logs(
    limit:  int        = Query(default=50, ge=1, le=500),
    level:  str | None = Query(default=None),
    ip:     str | None = Query(default=None),
    db:     Session    = Depends(get_db),
):
    """Lista os logs mais recentes com filtros opcionais."""
    query = db.query(RequestLog).order_by(desc(RequestLog.timestamp))

    if level:
        level = level.upper()
        if level not in RISK_LEVELS:
            raise HTTPException(
                status_code=422,
                detail=f"level inválido — use um de {', '.join(RISK_LEVELS)}",
            )
        query = query.filter(RequestLog.risk_level == level)
    if ip:
        query = query.filter(RequestLog.ip == ip)

    return query.limit(limit).all()


@router.get("/logs/{log_id}", response_model=LogDetail)
def get_log(log_id: str, db: Session = Depends(get_db)):
    """Retorna um log específico pelo ID."""
    log = db.get(RequestLog, log_id)
    if not log:
        raise HTTPException(status_code=404, detail="Log não encontrado")
    return log
