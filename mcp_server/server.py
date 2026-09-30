"""Servidor MCP de solo lectura sobre las facturas.

Expone las consultas de app/consultas.py como herramientas para asistentes (Claude
Desktop, etc.). El asistente decide qué herramienta llamar según la pregunta.

Ninguna herramienta modifica datos: aprobar o rechazar facturas es solo vía API,
por una persona.

Uso:
    uv run python -m mcp_server.server                 # stdio (Claude Desktop local)
    uv run python -m mcp_server.http_server            # HTTP con token (ver http_server.py)
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastmcp import FastMCP
from pydantic import Field
from sqlalchemy.engine import Engine
from sqlmodel import Session

from app import consultas
from app.db import session as db

INSTRUCCIONES = """\
Herramientas de consulta sobre facturas electrónicas chilenas (DTE) recibidas por la empresa.
Son de solo lectura. Montos en pesos chilenos (CLP), enteros.
Estados: 'registrada' (aceptada), 'en_revision' (esperando a una persona), 'rechazada'.
Solo las registradas cuentan para IVA crédito. Los RUT van como 76900010-0.
Todos los datos son ficticios (documentos de prueba).
"""

mcp = FastMCP("facturas-dte", instructions=INSTRUCCIONES)

# Motor de base de datos; los tests lo reemplazan por uno en memoria.
ENGINE: Engine | None = None


def _session() -> Session:
    return Session(ENGINE or db.engine)


def _ejecutar(fn, *args, **kwargs) -> dict:
    try:
        with _session() as s:
            return fn(s, *args, **kwargs)
    except consultas.ErrorConsulta as e:
        return {"error": str(e)}


@mcp.tool
def buscar_facturas(
    rut_emisor: Annotated[str | None, Field(description="RUT del proveedor, ej 76900010-0")] = None,
    desde: Annotated[date | None, Field(description="Fecha mínima AAAA-MM-DD")] = None,
    hasta: Annotated[date | None, Field(description="Fecha máxima AAAA-MM-DD")] = None,
    estado: Annotated[
        str | None, Field(description="registrada, en_revision o rechazada")
    ] = None,
    limite: Annotated[int, Field(description="Máximo de resultados (1-100)")] = 50,
) -> dict:
    """Busca facturas por proveedor, rango de fechas y/o estado."""
    return _ejecutar(consultas.buscar_facturas, rut_emisor, desde, hasta, estado, limite)


@mcp.tool
def resumen_proveedor(
    rut_emisor: Annotated[str, Field(description="RUT del proveedor, ej 76900010-0")],
) -> dict:
    """Resumen de un proveedor: documentos por estado, total comprado e IVA crédito."""
    return _ejecutar(consultas.resumen_proveedor, rut_emisor)


@mcp.tool
def iva_credito_mes(
    anio: Annotated[int, Field(description="Año, ej 2026")],
    mes: Annotated[int, Field(description="Mes 1-12")],
) -> dict:
    """IVA crédito fiscal de un mes: facturas registradas menos notas de crédito."""
    return _ejecutar(consultas.iva_credito_mes, anio, mes)


@mcp.tool
def revisiones_pendientes() -> dict:
    """Facturas que esperan revisión humana, con el motivo por el que fueron escaladas."""
    return _ejecutar(consultas.revisiones_pendientes)


def main() -> None:
    db.create_db()
    mcp.run()  # stdio por defecto


if __name__ == "__main__":
    main()
