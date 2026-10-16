from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

MIN_API_KEY_LENGTH = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Armazenamento dos logs: no Postgres do Foreguard ou por conta do cliente
    LOG_STORAGE: Literal["database", "client"] = "client"
    # Obrigatória só com LOG_STORAGE=database (startup da API, Alembic)
    DATABASE_URL: str | None = None
    # Chave compartilhada com o middleware (header X-Foreguard-Key)
    FOREGUARD_API_KEY: str | None = None

    API_HOST: str = "127.0.0.1"   # mesmo servidor da aplicação-cliente
    API_PORT: int = 8000
    DEBUG: bool = False

    THRESHOLD_MEDIUM: float = 3.0
    THRESHOLD_HIGH: float = 6.0
    THRESHOLD_CRITICAL: float = 8.0

    MAX_REQUEST_BYTES: int = 1_048_576   # corpo máximo de POST /v1/analyze
    MASK_FIELDS: list[str] = []          # campos extras mascarados no raw_request

    ML_MODEL_PATH: Path = Path("models") / "foreguard.pkl"
    LOG_DIR: Path | None = Path("logs")   # vazio desliga o log em arquivo

    @field_validator("DATABASE_URL", "FOREGUARD_API_KEY", "LOG_DIR", mode="before")
    @classmethod
    def _empty_as_none(cls, value):
        return None if value == "" else value


@lru_cache
def get_settings() -> Settings:
    """Settings carregadas sob demanda (cache); testes usam cache_clear()."""
    return Settings()
