"""Modelos de datos de la extracción."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class FacturaExtraida(BaseModel):
    """Datos de un DTE tal como aparecen en el documento (sin corregir errores)."""

    rut_emisor: str = Field(description="RUT del emisor, formato 12345678-9, sin puntos")
    razon_social_emisor: str = Field(description="Razón social del emisor")
    rut_receptor: str = Field(description="RUT del receptor, formato 12345678-9, sin puntos")
    tipo_dte: Literal[33, 34, 61] = Field(
        description="33 factura electrónica, 34 factura exenta, 61 nota de crédito"
    )
    folio: int = Field(description="Número de folio del documento")
    fecha: date = Field(description="Fecha de emisión, formato AAAA-MM-DD")
    neto: int = Field(0, description="Monto neto en pesos, entero sin separadores")
    iva: int = Field(0, description="Monto de IVA en pesos, entero sin separadores")
    exento: int = Field(0, description="Monto exento en pesos, entero sin separadores")
    total: int = Field(description="Monto total en pesos, entero sin separadores")


class UsoLLM(BaseModel):
    """Consumo de una llamada al LLM, para observabilidad y control de costo."""

    modelo: str
    input_tokens: int
    output_tokens: int
    costo_usd: float
    latencia_ms: int


class ResultadoExtraccion(BaseModel):
    factura: FacturaExtraida
    fuente: Literal["xml", "pdf"]
    texto_documento: str = Field(
        "", description="Texto extraído del PDF; lo usa el detector de inyección (tarjeta 8)"
    )
    uso: UsoLLM | None = None
    version_prompt: str | None = None


class ErrorExtraccion(Exception):
    """El documento no se pudo leer o el LLM no devolvió datos válidos."""
