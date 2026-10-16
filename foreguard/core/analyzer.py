"""
Orquestra o fluxo completo de análise:
extração de features → ML (ou regras) → score → nível → recomendação
"""
from loguru import logger

from foreguard.config import get_settings
from foreguard.core.extractor import FeatureExtractor
from foreguard.core.ml_model import ml_model as default_ml_model
from foreguard.core.rules import RulesEngine


class Analyzer:
    def __init__(self, ml_model=None):
        self.extractor = FeatureExtractor()
        self.rules     = RulesEngine()
        self.ml_model  = ml_model if ml_model is not None else default_ml_model

    def analyze(self, request: dict) -> dict:
        """
        Recebe o dicionário da requisição e retorna o resultado completo da análise.
        """
        # 1. Extrai features
        features = self.extractor.extract(request)

        # 2. Calcula score — ML se disponível, regras caso contrário
        if self.ml_model.available:
            try:
                score = self.ml_model.predict(features)
                # Complementa com reasons das regras (ML não explica por si só)
                rule_result = self.rules.evaluate(features)
                reasons = rule_result.reasons or ["Classificado pelo modelo ML como tráfego suspeito"]
                source = "ml"
            except Exception as e:
                logger.warning(f"Fallback para regras: {e}")
                rule_result = self.rules.evaluate(features)
                score   = rule_result.score
                reasons = rule_result.reasons
                source  = "rules_fallback"
        else:
            rule_result = self.rules.evaluate(features)
            score   = rule_result.score
            reasons = rule_result.reasons
            source  = "rules"

        level          = self._classify(score)
        recommendation = self._recommend(score)

        return {
            "risk_score":     score,
            "risk_level":     level,
            "reasons":        reasons,
            "recommendation": recommendation,
            "analysis_source": source,
            "features":       features,   # útil para debug / auditoria
        }

    def _classify(self, score: float) -> str:
        settings = get_settings()
        if score >= settings.THRESHOLD_CRITICAL:
            return "CRITICAL"
        elif score >= settings.THRESHOLD_HIGH:
            return "HIGH"
        elif score >= settings.THRESHOLD_MEDIUM:
            return "MEDIUM"
        return "LOW"

    def _recommend(self, score: float) -> str:
        settings = get_settings()
        if score >= settings.THRESHOLD_CRITICAL:
            return "LOCKDOWN: Bloqueie toda a aplicação e notifique a equipe de segurança imediatamente"
        elif score >= settings.THRESHOLD_HIGH:
            return "BAN_USER: Bloqueie este usuário/IP por 24 horas"
        elif score >= settings.THRESHOLD_MEDIUM:
            return "CHALLENGE: Aplique CAPTCHA ou solicite reautenticação"
        return "ALLOW: Requisição aparentemente segura"


# Singleton
analyzer = Analyzer()
