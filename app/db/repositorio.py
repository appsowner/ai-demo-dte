"""Consultas a la base de datos que necesitan las reglas y el agente."""

from __future__ import annotations

from collections.abc import Iterable

from sqlmodel import Session, select

from app.db.models import EstadoFactura, Factura

# Un documento rechazado no cuenta como duplicado: el emisor puede reenviarlo corregido.
ESTADOS_VIGENTES = (EstadoFactura.REGISTRADA, EstadoFactura.EN_REVISION)


def existe_factura(
    session: Session,
    rut_emisor: str,
    tipo_dte: int,
    folio: int,
    estados: Iterable[EstadoFactura] = ESTADOS_VIGENTES,
    excluir_id: int | None = None,
) -> bool:
    """True si ya hay un documento con la misma clave (emisor, tipo, folio) en esos estados."""
    stmt = select(Factura.id).where(
        Factura.rut_emisor == rut_emisor,
        Factura.tipo_dte == tipo_dte,
        Factura.folio == folio,
        Factura.estado.in_([e.value for e in estados]),
    )
    if excluir_id is not None:
        stmt = stmt.where(Factura.id != excluir_id)
    return session.exec(stmt).first() is not None
