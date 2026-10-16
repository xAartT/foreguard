import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, Depends
from loguru import logger
from sqlalchemy.orm import sessionmaker

from foreguard.api.schemas import AnalysisResponse, IncomingRequest
from foreguard.api.security import limit_request_size
from foreguard.config import get_settings
from foreguard.core.analyzer import analyzer
from foreguard.core.masking import mask_request
from foreguard.db.models import RequestLog
from foreguard.db.session import get_session_factory


def _analyze(incoming: IncomingRequest) -> tuple[AnalysisResponse, dict]:
    """Executa a análise; devolve a resposta e a requisição original (não mascarada)."""
    log_id = str(uuid.uuid4())
    timestamp = datetime.now(UTC)
    raw_request = incoming.model_dump()

    result = analyzer.analyze(raw_request)

    logger.info(
        f"[{log_id}] {incoming.method} {incoming.path} | "
        f"IP={incoming.ip} | "
        f"score={result['risk_score']} | "
        f"level={result['risk_level']} | "
        f"source={result['analysis_source']}"
    )

    response = AnalysisResponse(
        log_id          = log_id,
        timestamp       = timestamp,
        risk_score      = result["risk_score"],
        risk_level      = result["risk_level"],
        reasons         = result["reasons"],
        recommendation  = result["recommendation"],
        analysis_source = result["analysis_source"],
    )
    return response, raw_request


def persist_log(factory: sessionmaker, response: AnalysisResponse, raw_request: dict) -> None:
    """
    Grava a análise depois da resposta (BackgroundTasks).
    Nunca propaga erro: falha de banco custa o log, não a análise.
    """
    db = None
    try:
        masked = mask_request(raw_request, get_settings().MASK_FIELDS)
        db = factory()
        db.add(RequestLog(
            id = response.log_id,
            timestamp = response.timestamp,
            method = raw_request["method"],
            path = raw_request["path"],
            ip = raw_request["ip"],
            user_agent = raw_request.get("user_agent"),
            risk_score = response.risk_score,
            risk_level = response.risk_level,
            reasons = response.reasons,
            raw_request = masked,
        ))
        db.commit()
    except Exception:
        if db is not None:
            db.rollback()
        logger.exception(f"[{response.log_id}] Falha ao persistir análise")
    finally:
        if db is not None:
            db.close()


# Síncronas de propósito: a análise é CPU-bound e roda no threadpool.

def analyze_request(incoming: IncomingRequest) -> AnalysisResponse:
    """LOG_STORAGE=client — analisa e devolve; o armazenamento é do cliente."""
    response, _ = _analyze(incoming)
    return response


def analyze_and_store(
    incoming: IncomingRequest,
    background: BackgroundTasks,
    factory: sessionmaker = Depends(get_session_factory),
) -> AnalysisResponse:
    """LOG_STORAGE=database — analisa, responde e grava em segundo plano."""
    response, raw_request = _analyze(incoming)
    background.add_task(persist_log, factory, response, raw_request)
    return response


def build_router(log_storage: str) -> APIRouter:
    router = APIRouter()
    endpoint = analyze_and_store if log_storage == "database" else analyze_request
    router.add_api_route(
        "/analyze", endpoint, methods=["POST"],
        response_model=AnalysisResponse,
        dependencies=[Depends(limit_request_size)],
        summary="Analisa o risco de uma requisição",
    )
    return router
