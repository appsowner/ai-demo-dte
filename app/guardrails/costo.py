"""Guardrail de costo: una factura no debería consumir mucho más que el promedio.

Si una extracción supera el límite, algo raro pasa (un PDF gigante, texto de relleno para
gastar crédito, un modelo mal configurado). No se descarta: se escala a una persona.
"""

from __future__ import annotations

from app.config import MAX_COSTO_USD_POR_FACTURA, MAX_TOKENS_ENTRADA_POR_FACTURA
from app.extraction.schemas import UsoLLM
from app.validators.reglas import Codigo, Hallazgo, Severidad


def revisar_costo(uso: UsoLLM | None) -> list[Hallazgo]:
    if uso is None:  # XML: no se usó LLM
        return []
    motivos = []
    if uso.input_tokens > MAX_TOKENS_ENTRADA_POR_FACTURA:
        motivos.append(
            f"usó {uso.input_tokens} tokens de entrada (límite {MAX_TOKENS_ENTRADA_POR_FACTURA})"
        )
    if uso.costo_usd > MAX_COSTO_USD_POR_FACTURA:
        motivos.append(
            f"costó USD {uso.costo_usd:.5f} (límite USD {MAX_COSTO_USD_POR_FACTURA:.5f})"
        )
    if not motivos:
        return []
    return [
        Hallazgo(
            codigo=Codigo.COSTO_EXCEDIDO,
            severidad=Severidad.MEDIA,
            mensaje="La extracción " + " y ".join(motivos) + ".",
        )
    ]
