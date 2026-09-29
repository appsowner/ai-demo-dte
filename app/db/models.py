from datetime import UTC, date, datetime
from enum import StrEnum

from sqlalchemy import JSON, Column, UniqueConstraint
from sqlmodel import Field, SQLModel


class EstadoFactura(StrEnum):
    REGISTRADA = "registrada"
    EN_REVISION = "en_revision"
    RECHAZADA = "rechazada"


class DecisionRevision(StrEnum):
    PENDIENTE = "pendiente"
    APROBADA = "aprobada"
    RECHAZADA = "rechazada"


def _ahora() -> datetime:
    return datetime.now(UTC)


class Factura(SQLModel, table=True):
    __table_args__ = (
        UniqueConstraint("rut_emisor", "tipo_dte", "folio", name="uq_factura_emisor_tipo_folio"),
    )

    id: int | None = Field(default=None, primary_key=True)
    rut_emisor: str = Field(index=True)
    razon_social_emisor: str
    rut_receptor: str = Field(index=True)
    tipo_dte: int
    folio: int
    fecha: date
    neto: int = 0
    iva: int = 0
    exento: int = 0
    total: int
    estado: EstadoFactura = Field(default=EstadoFactura.EN_REVISION)
    creada_en: datetime = Field(default_factory=_ahora)


class Revision(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    factura_id: int = Field(foreign_key="factura.id", index=True)
    hallazgos: list[dict] = Field(default_factory=list, sa_column=Column(JSON))
    motivo: str = ""
    decision: DecisionRevision = Field(default=DecisionRevision.PENDIENTE)
    revisada_en: datetime | None = None
