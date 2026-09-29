"""Decisión del agente a partir de los hallazgos. Función pura: fácil de testear y auditar."""

from __future__ import annotations

from typing import Literal

from app.validators.reglas import Hallazgo

Decision = Literal["registrar", "escalar"]


def decidir(hallazgos: list[Hallazgo]) -> Decision:
    """Cualquier hallazgo (de severidad alta o media) manda la factura a revisión humana.

    El LLM no participa: la aprobación automática solo ocurre cuando las reglas no
    encuentran nada.
    """
    return "escalar" if hallazgos else "registrar"


def motivo(hallazgos: list[Hallazgo]) -> str:
    if not hallazgos:
        return "Sin hallazgos: el documento cumple todas las reglas."
    return " ".join(h.mensaje for h in hallazgos)
