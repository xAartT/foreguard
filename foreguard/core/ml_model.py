"""
Módulo de inferência do modelo ML.
Carrega o modelo treinado (.pkl) e realiza predições.
Se o modelo não estiver disponível, o analyzer usa o
sistema de regras como fallback.
"""
from pathlib import Path

import numpy as np
from loguru import logger

from foreguard.config import get_settings

# Ordem das features deve ser IGUAL à usada no treinamento
FEATURE_ORDER = [
    "has_sqli", "has_xss", "has_path_traversal",
    "body_length", "path_length", "param_count", "payload_entropy",
    "ua_is_bot", "ua_is_empty", "ua_is_scanner",
    "ip_is_private", "ip_has_proxy_header",
    "has_suspicious_hdrs", "header_count", "has_jwt",
    "method_risk",
]


class MLModel:
    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else get_settings().ML_MODEL_PATH
        self.model = None
        self._load()

    def _load(self):
        if not self.path.exists():
            logger.info("Modelo ML não encontrado — usando regras estáticas como fallback")
            return
        try:
            import joblib
            self.model = joblib.load(self.path)
            logger.info(f"Modelo ML carregado: {self.path}")
        except Exception as e:
            logger.warning(f"Falha ao carregar modelo ML: {e}")
            self.model = None

    @property
    def available(self) -> bool:
        return self.model is not None

    def predict(self, features: dict) -> float:
        """
        Retorna score de risco entre 0.0 e 10.0.
        Usa a probabilidade da classe positiva (malicioso) * 10.
        """
        if not self.available:
            raise RuntimeError("Modelo não disponível")

        X = np.array([features.get(f, 0) for f in FEATURE_ORDER]).reshape(1, -1)

        try:
            proba = self.model.predict_proba(X)[0][1]
            return round(float(proba) * 10, 2)
        except Exception as e:
            logger.error(f"Erro na inferência ML: {e}")
            raise


# Instância singleton — carregada uma vez na inicialização da API
ml_model = MLModel()
