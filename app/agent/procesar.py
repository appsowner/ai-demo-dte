"""Punto de entrada del agente: procesa un documento y devuelve el resultado."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel
from sqlmodel import Session

from app import observabilidad as obs
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
    contenido: bytes,
    *,
    session: Session,
    cliente_llm: ClienteLLM | None,
    hoy: date,
    metadata: dict | None = None,
) -> ResultadoProcesamiento:
    """`metadata` se adjunta a la traza (origen, nombre de archivo, caso de eval...)."""
    grafo = construir_grafo(session, cliente_llm, hoy)
    meta = metadata or {}
    entrada = {"archivo": meta.get("archivo") or meta.get("caso"), "bytes": len(contenido)}
    with obs.traza_factura(meta, entrada=entrada) as traza:
        final = grafo.invoke({"contenido": contenido}, config=traza.config)
        ext = final["extraccion"]
        # Lo que un revisor necesita ver de un vistazo en la traza.
        traza.resultado(
            {
                "decision": final["decision"],
                "motivo": final["motivo"],
                "hallazgos": [h.codigo for h in final["hallazgos"]],
                "factura_id": final["factura_id"],
                "fuente": ext.fuente,
                "rut_emisor": ext.factura.rut_emisor,
                "folio": ext.factura.folio,
            }
        )
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
