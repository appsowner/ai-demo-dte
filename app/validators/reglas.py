"""Reglas tributarias determinísticas. Sin LLM: exactas, testeables y auditables.

Cada regla devuelve hallazgos con un código estable, que usan el agente (tarjeta 5)
y las evals (tarjeta 7). POSIBLE_INYECCION y COSTO_EXCEDIDO los emiten los guardrails
(app/guardrails), no estas reglas.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import BaseModel

from app.config import TASA_IVA, UMBRAL_MONTO_ALTO
from app.extraction.schemas import FacturaExtraida
from app.validators import rut

TOLERANCIA_IVA = 1  # pesos, por redondeos del emisor


class Codigo(StrEnum):
    RUT_EMISOR_INVALIDO = "RUT_EMISOR_INVALIDO"
    RUT_RECEPTOR_INVALIDO = "RUT_RECEPTOR_INVALIDO"
    IVA_INCORRECTO = "IVA_INCORRECTO"
    TOTAL_NO_CUADRA = "TOTAL_NO_CUADRA"
    DUPLICADO = "DUPLICADO"
    FECHA_FUTURA = "FECHA_FUTURA"
    MONTO_ALTO = "MONTO_ALTO"
    # Guardrails (app/guardrails)
    POSIBLE_INYECCION = "POSIBLE_INYECCION"
    COSTO_EXCEDIDO = "COSTO_EXCEDIDO"


class Severidad(StrEnum):
    ALTA = "alta"  # error en el documento: no se puede registrar sin revisión
    MEDIA = "media"  # documento correcto, pero la política exige que lo vea una persona


class Hallazgo(BaseModel):
    codigo: Codigo
    severidad: Severidad
    mensaje: str


def iva_esperado(neto: int) -> int:
    """IVA sobre el neto, redondeado hacia arriba en ,5 (no el redondeo bancario de round())."""
    return (neto * TASA_IVA + 50) // 100


def _clp(monto: int) -> str:
    return "$" + f"{monto:,}".replace(",", ".")


def validar(factura: FacturaExtraida, *, hoy: date, es_duplicado: bool = False) -> list[Hallazgo]:
    """Aplica todas las reglas y devuelve los hallazgos (lista vacía = documento limpio)."""
    h: list[Hallazgo] = []
    f = factura

    if not rut.es_valido(f.rut_emisor):
        h.append(Hallazgo(codigo=Codigo.RUT_EMISOR_INVALIDO, severidad=Severidad.ALTA,
                          mensaje=f"El RUT del emisor {f.rut_emisor} no es válido."))
    if not rut.es_valido(f.rut_receptor):
        h.append(Hallazgo(codigo=Codigo.RUT_RECEPTOR_INVALIDO, severidad=Severidad.ALTA,
                          mensaje=f"El RUT del receptor {f.rut_receptor} no es válido."))

    if f.tipo_dte == 34:
        if f.iva != 0 or f.neto != 0:
            h.append(Hallazgo(codigo=Codigo.IVA_INCORRECTO, severidad=Severidad.ALTA,
                              mensaje="Una factura exenta (tipo 34) no puede tener neto ni IVA."))
    else:
        esperado = iva_esperado(f.neto)
        if abs(f.iva - esperado) > TOLERANCIA_IVA:
            h.append(Hallazgo(codigo=Codigo.IVA_INCORRECTO, severidad=Severidad.ALTA,
                              mensaje=f"IVA {_clp(f.iva)} no corresponde al {TASA_IVA}% del neto "
                                      f"{_clp(f.neto)} (esperado {_clp(esperado)})."))

    suma = f.neto + f.iva + f.exento
    if f.total != suma:
        h.append(Hallazgo(codigo=Codigo.TOTAL_NO_CUADRA, severidad=Severidad.ALTA,
                          mensaje=f"Total {_clp(f.total)} no coincide con neto + IVA + exento "
                                  f"({_clp(suma)})."))

    if es_duplicado:
        h.append(Hallazgo(codigo=Codigo.DUPLICADO, severidad=Severidad.ALTA,
                          mensaje=f"Ya existe el documento tipo {f.tipo_dte} folio {f.folio} "
                                  f"del emisor {f.rut_emisor}."))

    if f.fecha > hoy:
        h.append(Hallazgo(codigo=Codigo.FECHA_FUTURA, severidad=Severidad.ALTA,
                          mensaje=f"La fecha de emisión {f.fecha.isoformat()} es futura."))

    if f.total >= UMBRAL_MONTO_ALTO:
        h.append(Hallazgo(codigo=Codigo.MONTO_ALTO, severidad=Severidad.MEDIA,
                          mensaje=f"Total {_clp(f.total)} igual o superior al umbral de "
                                  f"revisión ({_clp(UMBRAL_MONTO_ALTO)})."))
    return h
