"""Consultas a la base de datos que necesitan las reglas y el agente."""

from __future__ import annotations

from sqlmodel import Session, select

from app.db.models import Factura


def existe_factura(session: Session, rut_emisor: str, tipo_dte: int, folio: int) -> bool:
    """True si ya hay un documento con la misma clave (emisor, tipo, folio)."""
    stmt = select(Factura.id).where(
        Factura.rut_emisor == rut_emisor,
        Factura.tipo_dte == tipo_dte,
        Factura.folio == folio,
    )
    return session.exec(stmt).first() is not None
