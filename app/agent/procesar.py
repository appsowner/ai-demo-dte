"""Punto de entrada del agente: procesa un documento y devuelve el resultado."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel
from sqlmodel import Session

from app.agent.decision import Decision
from app.agent.grafo import construir_grafo
from app.extraction.llm import ClienteLLM
from app.extraction.schemas import FacturaExtraida, UsoLLM
from app.validators.reglas import Hallazgo


class ResultadoProcesamiento(BaseModel):
    factura_id: int
    decision: Decision
    motivo: str
    hallazgos: list[Hallazgo]
    revision_id: int | None
    fuente: str
    factura: FacturaExtraida
    uso_llm: UsoLLM | None


def procesar_documento(
    contenido: bytes, *, session: Session, cliente_llm: ClienteLLM | None, hoy: date
) -> ResultadoProcesamiento:
    grafo = construir_grafo(session, cliente_llm, hoy)
    final = grafo.invoke({"contenido": contenido})
    ext = final["extraccion"]
    return ResultadoProcesamiento(
        factura_id=final["factura_id"],
        decision=final["decision"],
        motivo=final["motivo"],
        hallazgos=final["hallazgos"],
        revision_id=final.get("revision_id"),
        fuente=ext.fuente,
        factura=ext.factura,
        uso_llm=ext.uso,
    )
