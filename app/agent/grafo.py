"""Grafo del agente con LangGraph.

    START → extraer → seguridad → validar → decidir ─┬─ registrar → END
                                                     └─ escalar   → END   (revisión humana)

"seguridad" corre los guardrails (prompt injection y costo) antes de las reglas.

La revisión humana es asíncrona: la factura queda en la tabla Revision con estado
"pendiente" hasta que una persona la aprueba o rechaza desde la API. Así la cola
sobrevive a reinicios y se puede consultar, auditar y medir.
"""

from __future__ import annotations

from datetime import date
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from sqlmodel import Session

from app.agent.decision import Decision, decidir, motivo
from app.db.models import EstadoFactura, Factura, Revision
from app.db.repositorio import existe_factura
from app.extraction.llm import ClienteLLM
from app.extraction.schemas import ResultadoExtraccion
from app.extraction.service import extraer_documento
from app.guardrails.costo import revisar_costo
from app.guardrails.inyeccion import detectar_inyeccion
from app.validators.reglas import Hallazgo, validar


class EstadoAgente(TypedDict, total=False):
    contenido: bytes
    extraccion: ResultadoExtraccion
    hallazgos_seguridad: list[Hallazgo]
    hallazgos: list[Hallazgo]
    decision: Decision
    motivo: str
    factura_id: int
    revision_id: int | None


def construir_grafo(session: Session, cliente_llm: ClienteLLM | None, hoy: date):
    def nodo_extraer(estado: EstadoAgente) -> EstadoAgente:
        return {"extraccion": extraer_documento(estado["contenido"], cliente_llm)}

    def nodo_seguridad(estado: EstadoAgente) -> EstadoAgente:
        ext = estado["extraccion"]
        # PDF: texto extraído. XML: el propio XML (un atacante también podría escribir ahí).
        texto = ext.texto_documento or estado["contenido"].decode("latin-1", errors="ignore")
        return {"hallazgos_seguridad": detectar_inyeccion(texto) + revisar_costo(ext.uso)}

    def nodo_validar(estado: EstadoAgente) -> EstadoAgente:
        f = estado["extraccion"].factura
        duplicado = existe_factura(session, f.rut_emisor, f.tipo_dte, f.folio)
        reglas = validar(f, hoy=hoy, es_duplicado=duplicado)
        return {"hallazgos": estado.get("hallazgos_seguridad", []) + reglas}

    def nodo_decidir(estado: EstadoAgente) -> EstadoAgente:
        hallazgos = estado["hallazgos"]
        return {"decision": decidir(hallazgos), "motivo": motivo(hallazgos)}

    def _guardar_factura(estado: EstadoAgente, estado_factura: EstadoFactura) -> Factura:
        ext = estado["extraccion"]
        factura = Factura(**ext.factura.model_dump(), estado=estado_factura, fuente=ext.fuente)
        session.add(factura)
        session.flush()  # asigna id sin cerrar la transacción
        return factura

    def nodo_registrar(estado: EstadoAgente) -> EstadoAgente:
        factura = _guardar_factura(estado, EstadoFactura.REGISTRADA)
        session.commit()
        return {"factura_id": factura.id, "revision_id": None}

    def nodo_escalar(estado: EstadoAgente) -> EstadoAgente:
        factura = _guardar_factura(estado, EstadoFactura.EN_REVISION)
        revision = Revision(
            factura_id=factura.id,
            hallazgos=[h.model_dump(mode="json") for h in estado["hallazgos"]],
            motivo=estado["motivo"],
        )
        session.add(revision)
        session.commit()
        return {"factura_id": factura.id, "revision_id": revision.id}

    g = StateGraph(EstadoAgente)
    g.add_node("extraer", nodo_extraer)
    g.add_node("seguridad", nodo_seguridad)
    g.add_node("validar", nodo_validar)
    g.add_node("decidir", nodo_decidir)
    g.add_node("registrar", nodo_registrar)
    g.add_node("escalar", nodo_escalar)

    g.add_edge(START, "extraer")
    g.add_edge("extraer", "seguridad")
    g.add_edge("seguridad", "validar")
    g.add_edge("validar", "decidir")
    def elegir_camino(estado: EstadoAgente) -> Decision:
        # Función con nombre (no lambda): así aparece legible en las trazas.
        return estado["decision"]

    g.add_conditional_edges(
        "decidir", elegir_camino, {"registrar": "registrar", "escalar": "escalar"}
    )
    g.add_edge("registrar", END)
    g.add_edge("escalar", END)
    return g.compile()
