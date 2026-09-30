from datetime import UTC, date, datetime
from enum import StrEnum

from sqlalchemy import JSON, Column, Index, String, text
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
    # Solo puede haber UNA factura registrada por (emisor, tipo, folio). Los duplicados sí
    # pueden existir en revisión o rechazados, para que un humano los vea en la cola.
    __table_args__ = (
        Index(
            "uq_factura_registrada",
            "rut_emisor",
            "tipo_dte",
            "folio",
            unique=True,
            sqlite_where=text("estado = 'registrada'"),
        ),
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
    # Se guarda como texto ('registrada', ...) para que el índice parcial funcione.
    # Valores posibles: ver EstadoFactura.
    estado: str = Field(default=EstadoFactura.EN_REVISION.value, sa_type=String(20))
    fuente: str = "xml"
    creada_en: datetime = Field(default_factory=_ahora)


class Revision(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    factura_id: int = Field(foreign_key="factura.id", index=True)
    hallazgos: list[dict] = Field(default_factory=list, sa_column=Column(JSON))
    motivo: str = ""
    # Valores posibles: ver DecisionRevision.
    decision: str = Field(default=DecisionRevision.PENDIENTE.value, sa_type=String(20))
    comentario: str = ""
    creada_en: datetime = Field(default_factory=_ahora)
    revisada_en: datetime | None = None
