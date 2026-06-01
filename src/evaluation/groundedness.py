"""
GroundednessChecker — verifica que los hallazgos del audit_engine estén
anclados en el texto fuente del acta.

Responde a la crítica: "¿cómo sabés que el audit_engine no alucina?"
Cada hallazgo recibe un score de anclaje textual (0-1) calculado con
token-overlap (Jaccard) sobre una ventana deslizante de 100 palabras.

Umbral < 0.15 → hallazgo marcado como [BAJA_EVIDENCIA] (posible alucinación).
"""

from __future__ import annotations

import re
import unicodedata


def sha16(text: str) -> str:
    """Hash SHA-256 truncado a 16 hex chars para reproducibilidad de prompts."""
    import hashlib

    return hashlib.sha256(text.encode()).hexdigest()[:16]


STOPWORDS_ES = frozenset(
    "de la el los las un una unos unas y o a en con por para que del al es se "
    "su sus al del lo le les me te nos vos fue ser ha sido".split()
)
WINDOW_SIZE = 100
LOW_EVIDENCE_THRESHOLD = 0.15
LOW_EVIDENCE_PREFIX = "[BAJA_EVIDENCIA] "


def _tokenize(text: str) -> list[str]:
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    tokens = re.findall(r"[a-z0-9]+", text)
    return [t for t in tokens if t not in STOPWORDS_ES and len(t) > 2]


def _jaccard(set_a: frozenset, set_b: frozenset) -> float:
    if not set_a and not set_b:
        return 0.0
    inter = len(set_a & set_b)
    union = len(set_a | set_b)
    return inter / union if union > 0 else 0.0


class GroundednessChecker:
    """Verifica anclaje textual de hallazgos en el texto fuente."""

    def score_hallazgo(self, hallazgo: str, source_text: str) -> float:
        """
        Calcula score de anclaje (0-1) del hallazgo respecto al texto fuente.

        Usa ventana deslizante de WINDOW_SIZE tokens para encontrar la región
        del texto que mejor se solapa con los tokens del hallazgo.
        """
        h_tokens = frozenset(_tokenize(hallazgo))
        if not h_tokens:
            return 0.0

        s_tokens = _tokenize(source_text)
        if not s_tokens:
            return 0.0

        best = 0.0
        for i in range(0, len(s_tokens), max(1, WINDOW_SIZE // 4)):
            window = frozenset(s_tokens[i : i + WINDOW_SIZE])
            score = _jaccard(h_tokens, window)
            if score > best:
                best = score
            if best > 0.9:
                break

        return round(best, 4)

    def check_all(self, hallazgos: list[str], source_text: str) -> dict:
        """
        Calcula scores para una lista de hallazgos.

        Retorna:
            scores: score por hallazgo (mismo orden)
            avg: promedio
            low_evidence_indices: índices con score < umbral
        """
        scores = [self.score_hallazgo(h, source_text) for h in hallazgos]
        avg = sum(scores) / len(scores) if scores else 0.0
        low = [i for i, s in enumerate(scores) if s < LOW_EVIDENCE_THRESHOLD]
        return {"scores": scores, "avg": round(avg, 4), "low_evidence_indices": low}

    def flag_low_evidence(self, hallazgos: list[str], scores: list[float]) -> list[str]:
        """Prefija [BAJA_EVIDENCIA] en hallazgos con score bajo."""
        result = []
        for h, s in zip(hallazgos, scores, strict=False):
            if s < LOW_EVIDENCE_THRESHOLD and not h.startswith(LOW_EVIDENCE_PREFIX):
                result.append(LOW_EVIDENCE_PREFIX + h)
            else:
                result.append(h)
        return result
