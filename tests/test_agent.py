"""Tests del agente de punta a punta vía API. Sin LLM real: se usa un cliente falso."""

import re
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.agent.decision import decidir, motivo
from app.api.routes import get_cliente_llm, get_hoy
from app.db.session import get_session
from app.extraction.schemas import UsoLLM
from app.main import app
from app.validators.reglas import Codigo, Hallazgo, Severidad
from samples.cases import CASOS
from samples.render_pdf import render_pdf
from samples.render_xml import render_xml

HOY = date(2026, 9, 30)
CASO = {c.id: c for c in CASOS}


class LLMFalso:
    """Devuelve los campos esperados del caso según el folio que aparece en el texto."""

    def __init__(self) -> None:
        self.llamadas = 0

    def extraer(self, texto: str):
        self.llamadas += 1
        folio = int(re.search(r"N°\s*(\d+)", texto).group(1))
        caso = next(c for c in CASOS if c.folio == folio)
        uso = UsoLLM(modelo="falso", input_tokens=900, output_tokens=70, costo_usd=0.0002,
                     latencia_ms=5)
        return caso.campos_esperados(), uso


@pytest.fixture
def llm():
    return LLMFalso()


@pytest.fixture
def client(llm):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    def _session():
        with Session(engine) as s:
            yield s

    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_hoy] = lambda: HOY
    app.dependency_overrides[get_cliente_llm] = lambda: llm
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _subir_xml(client, caso_id: str):
    caso = CASO[caso_id]
    return client.post("/facturas", files={"archivo": (f"{caso_id}.xml", render_xml(caso))})


def _codigos(respuesta: dict) -> list[str]:
    return sorted(h["codigo"] for h in respuesta["hallazgos"])


# --- decisión (función pura) ------------------------------------------------------------


def test_decidir():
    h = Hallazgo(codigo=Codigo.MONTO_ALTO, severidad=Severidad.MEDIA, mensaje="Monto alto.")
    assert decidir([]) == "registrar"
    assert decidir([h]) == "escalar"
    assert motivo([h]) == "Monto alto."
    assert "Sin hallazgos" in motivo([])


# --- lote completo ---------------------------------------------------------------------


def test_lote_de_20_xml_coincide_con_la_pauta(client, llm):
    for caso in CASOS:
        r = _subir_xml(client, caso.id)
        assert r.status_code == 200, (caso.id, r.text)
        body = r.json()
        # En XML no hay texto oculto: la inyección solo existe en el PDF (tarjeta 8).
        esperados = sorted(h for h in caso.hallazgos if h != "POSIBLE_INYECCION")
        assert _codigos(body) == esperados, caso.id
        assert body["decision"] == ("escalar" if esperados else "registrar"), caso.id
    assert llm.llamadas == 0  # los XML nunca usan el LLM

    registradas = client.get("/facturas", params={"estado": "registrada"}).json()
    pendientes = client.get("/revisiones").json()
    assert len(registradas) + len(pendientes) == 20


# --- PDF usa el LLM -----------------------------------------------------------------------


def test_pdf_pasa_por_el_llm(client, llm):
    caso = CASO["c03_valida_transportes"]
    r = client.post("/facturas", files={"archivo": ("c03.pdf", render_pdf(caso))})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["decision"] == "registrar"
    assert body["fuente"] == "pdf"
    assert body["uso_llm"]["input_tokens"] == 900
    assert llm.llamadas == 1


def test_pdf_sin_llm_configurado(client):
    app.dependency_overrides[get_cliente_llm] = lambda: None
    r = client.post("/facturas", files={"archivo": ("x.pdf", render_pdf(CASOS[0]))})
    assert r.status_code == 422
    assert "cliente LLM" in r.json()["detail"]


def test_archivo_no_soportado(client):
    r = client.post("/facturas", files={"archivo": ("x.zip", b"PK\x03\x04basura")})
    assert r.status_code == 422


# --- revisión humana ---------------------------------------------------------------------


def test_aprobar_factura_escalada(client):
    r = _subir_xml(client, "c09_monto_alto").json()
    assert r["decision"] == "escalar"
    assert r["revision_id"] is not None

    cola = client.get("/revisiones").json()
    assert [c["id"] for c in cola] == [r["revision_id"]]
    assert cola[0]["factura"]["estado"] == "en_revision"

    ok = client.post(f"/revisiones/{r['revision_id']}", json={"decision": "aprobada",
                                                              "comentario": "Proyecto autorizado"})
    assert ok.status_code == 200, ok.text
    assert ok.json()["factura"]["estado"] == "registrada"
    assert client.get("/revisiones").json() == []

    otra_vez = client.post(f"/revisiones/{r['revision_id']}", json={"decision": "rechazada"})
    assert otra_vez.status_code == 409


def test_rechazar_factura(client):
    r = _subir_xml(client, "c10_iva_incorrecto").json()
    ok = client.post(f"/revisiones/{r['revision_id']}", json={"decision": "rechazada"})
    assert ok.json()["factura"]["estado"] == "rechazada"
    resueltas = client.get("/revisiones", params={"decision": "rechazada"}).json()
    assert len(resueltas) == 1


def test_no_se_puede_aprobar_un_duplicado(client):
    assert _subir_xml(client, "c01_valida_ferreteria").json()["decision"] == "registrar"
    dup = _subir_xml(client, "c15_duplicado").json()
    assert _codigos(dup) == ["DUPLICADO"]
    r = client.post(f"/revisiones/{dup['revision_id']}", json={"decision": "aprobada"})
    assert r.status_code == 409


def test_revision_inexistente(client):
    assert client.post("/revisiones/999", json={"decision": "aprobada"}).status_code == 404
