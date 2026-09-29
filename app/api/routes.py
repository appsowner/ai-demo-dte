"""Endpoints de la API: subir facturas y gestionar la cola de revisión humana."""

from __future__ import annotations

from datetime import UTC, date, datetime
from functools import lru_cache
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.agent.procesar import ResultadoProcesamiento, procesar_documento
from app.db.models import DecisionRevision, EstadoFactura, Factura, Revision
from app.db.repositorio import existe_factura
from app.db.session import get_session
from app.extraction.llm import ClienteLLM, crear_cliente
from app.extraction.schemas import ErrorExtraccion

TAMANO_MAXIMO_BYTES = 5 * 1024 * 1024

router = APIRouter()

SessionDep = Annotated[Session, Depends(get_session)]


def get_hoy() -> date:
    return date.today()


@lru_cache
def _cliente_por_defecto() -> ClienteLLM | None:
    try:
        return crear_cliente()
    except ErrorExtraccion:
        return None  # sin API key: los XML funcionan igual, los PDF responden 422


def get_cliente_llm() -> ClienteLLM | None:
    return _cliente_por_defecto()


# --- facturas -----------------------------------------------------------------------


@router.post("/facturas", response_model=ResultadoProcesamiento, tags=["facturas"])
def subir_factura(
    archivo: Annotated[UploadFile, File(description="DTE en XML o PDF")],
    session: SessionDep,
    cliente_llm: Annotated[ClienteLLM | None, Depends(get_cliente_llm)],
    hoy: Annotated[date, Depends(get_hoy)],
) -> ResultadoProcesamiento:
    """Procesa una factura: extrae, valida y la registra o la manda a revisión humana."""
    # Endpoint síncrono: FastAPI lo corre en un thread, así la llamada al LLM no bloquea.
    contenido = archivo.file.read()
    if len(contenido) > TAMANO_MAXIMO_BYTES:
        raise HTTPException(413, "El archivo supera 5 MB")
    try:
        return procesar_documento(contenido, session=session, cliente_llm=cliente_llm, hoy=hoy)
    except ErrorExtraccion as e:
        session.rollback()
        raise HTTPException(422, str(e)) from e


@router.get("/facturas", response_model=list[Factura], tags=["facturas"])
def listar_facturas(session: SessionDep, estado: EstadoFactura | None = None) -> list[Factura]:
    stmt = select(Factura).order_by(Factura.id)
    if estado:
        stmt = stmt.where(Factura.estado == estado.value)
    return list(session.exec(stmt).all())


# --- revisión humana ------------------------------------------------------------------


class RevisionOut(BaseModel):
    id: int
    decision: str
    motivo: str
    hallazgos: list[dict]
    comentario: str
    creada_en: datetime
    revisada_en: datetime | None
    factura: Factura


class DecisionHumana(BaseModel):
    decision: Literal["aprobada", "rechazada"]
    comentario: str = ""


def _revision_out(session: Session, rev: Revision) -> RevisionOut:
    return RevisionOut(**rev.model_dump(), factura=session.get(Factura, rev.factura_id))


@router.get("/revisiones", response_model=list[RevisionOut], tags=["revisión humana"])
def listar_revisiones(
    session: SessionDep, decision: DecisionRevision | None = DecisionRevision.PENDIENTE
) -> list[RevisionOut]:
    """Cola de revisión. Por defecto muestra solo las pendientes."""
    stmt = select(Revision).order_by(Revision.id)
    if decision:
        stmt = stmt.where(Revision.decision == decision.value)
    return [_revision_out(session, r) for r in session.exec(stmt).all()]


@router.post("/revisiones/{revision_id}", response_model=RevisionOut, tags=["revisión humana"])
def resolver_revision(
    revision_id: int, cuerpo: DecisionHumana, session: SessionDep
) -> RevisionOut:
    """Una persona aprueba (se registra) o rechaza la factura escalada."""
    rev = session.get(Revision, revision_id)
    if rev is None:
        raise HTTPException(404, "Revisión no encontrada")
    if rev.decision != DecisionRevision.PENDIENTE:
        raise HTTPException(409, f"La revisión ya fue resuelta ({rev.decision})")

    factura = session.get(Factura, rev.factura_id)
    if cuerpo.decision == "aprobada":
        if existe_factura(
            session, factura.rut_emisor, factura.tipo_dte, factura.folio,
            estados=[EstadoFactura.REGISTRADA], excluir_id=factura.id,
        ):
            raise HTTPException(
                409, "Ya existe una factura registrada con ese emisor, tipo y folio"
            )
        factura.estado = EstadoFactura.REGISTRADA
    else:
        factura.estado = EstadoFactura.RECHAZADA

    rev.decision = DecisionRevision(cuerpo.decision)
    rev.comentario = cuerpo.comentario
    rev.revisada_en = datetime.now(UTC)
    try:
        session.commit()
    except IntegrityError as e:
        session.rollback()
        raise HTTPException(409, "Conflicto al registrar la factura") from e
    session.refresh(rev)
    return _revision_out(session, rev)
