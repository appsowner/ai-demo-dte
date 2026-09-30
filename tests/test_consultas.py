"""Tests de las consultas y del servidor MCP. Sin LLM ni red."""

import asyncio
import json
from datetime import date

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from app import consultas
from app.agent.procesar import procesar_documento
from mcp_server import server
from mcp_server.http_server import TokenBearer, hash_token
from samples.cases import CASOS
from samples.render_xml import render_xml

HOY = date(2026, 9, 30)
FERRETERIA = "76900010-0"


@pytest.fixture
def engine():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False},
                        poolclass=StaticPool)
    SQLModel.metadata.create_all(eng)
    with Session(eng) as s:
        for caso in CASOS:  # mismo flujo que samples/cargar.py
            procesar_documento(render_xml(caso), session=s, cliente_llm=None, hoy=HOY)
    return eng


@pytest.fixture
def session(engine):
    with Session(engine) as s:
        yield s


def _queda_registrada(caso) -> bool:
    # Al cargar XML no hay texto oculto, así que solo la inyección no basta para escalar
    # (eso llega con los guardrails de la tarjeta 8).
    return not [h for h in caso.hallazgos if h != "POSIBLE_INYECCION"]


REGISTRADAS = [c for c in CASOS if _queda_registrada(c)]


# --- consultas -----------------------------------------------------------------------


def test_iva_credito_septiembre(session):
    r = consultas.iva_credito_mes(session, 2026, 9)
    casos = [c for c in REGISTRADAS if c.fecha.month == 9]
    esperado = sum(c.iva for c in casos if c.tipo_dte != 61) - sum(
        c.iva for c in casos if c.tipo_dte == 61
    )
    assert r["iva_credito"] == esperado
    assert r["iva_notas_credito"] > 0  # c08 resta
    assert r["documentos_registrados"] == len(casos)
    assert r["documentos_excluidos"]["en_revision"] > 0


def test_iva_mes_sin_datos(session):
    r = consultas.iva_credito_mes(session, 2026, 1)
    assert r["iva_credito"] == 0 and r["documentos_registrados"] == 0


def test_iva_mes_invalido(session):
    with pytest.raises(consultas.ErrorConsulta):
        consultas.iva_credito_mes(session, 2026, 13)


def test_buscar_por_proveedor_con_puntos(session):
    r = consultas.buscar_facturas(session, rut_emisor="76.900.010-0")
    folios = {f["folio"] for f in r["facturas"]}
    esperados = {c.folio for c in CASOS if c.rut_emisor_efectivo == FERRETERIA}
    assert folios == esperados
    assert r["cantidad"] == sum(1 for c in CASOS if c.rut_emisor_efectivo == FERRETERIA)


def test_buscar_por_estado_y_limite(session):
    r = consultas.buscar_facturas(session, estado="registrada", limite=3)
    assert r["mostradas"] == 3
    assert r["cantidad"] == len(REGISTRADAS)
    assert all(f["estado"] == "registrada" for f in r["facturas"])


def test_buscar_parametros_invalidos(session):
    with pytest.raises(consultas.ErrorConsulta):
        consultas.buscar_facturas(session, estado="aprobada")
    with pytest.raises(consultas.ErrorConsulta):
        consultas.buscar_facturas(session, rut_emisor="no-es-rut")
    with pytest.raises(consultas.ErrorConsulta):
        consultas.buscar_facturas(session, desde=date(2026, 9, 30), hasta=date(2026, 9, 1))


def test_resumen_proveedor(session):
    r = consultas.resumen_proveedor(session, FERRETERIA)
    assert r["encontrado"]
    assert r["razon_social"].startswith("Ferretería")
    # c01 + c05 registradas, menos la nota de crédito c08
    c = {x.id: x for x in CASOS}
    esperado = c["c01_valida_ferreteria"].total + c["c05_redondeo_iva"].total \
        - c["c08_nota_credito_61"].total
    assert r["total_comprado_registrado"] == esperado
    assert r["documentos_por_estado"]["en_revision"] >= 1  # duplicado, IVA mal, inyección


def test_resumen_proveedor_inexistente(session):
    assert consultas.resumen_proveedor(session, "11111111-1")["encontrado"] is False


def test_revisiones_pendientes(session):
    r = consultas.revisiones_pendientes(session)
    assert r["cantidad"] == len(CASOS) - len(REGISTRADAS)
    assert all(p["hallazgos"] for p in r["pendientes"])


# --- servidor MCP (cliente en memoria, sin red) ------------------------------------------


def _texto(resultado) -> dict:
    contenido = getattr(resultado, "content", resultado)
    return json.loads(contenido[0].text)


def test_mcp_publica_las_herramientas(engine, monkeypatch):
    from fastmcp import Client

    monkeypatch.setattr(server, "ENGINE", engine)

    async def correr():
        async with Client(server.mcp) as client:
            nombres = {t.name for t in await client.list_tools()}
            iva = _texto(await client.call_tool("iva_credito_mes", {"anio": 2026, "mes": 9}))
            error = _texto(await client.call_tool("iva_credito_mes", {"anio": 2026, "mes": 13}))
            return nombres, iva, error

    nombres, iva, error = asyncio.run(correr())
    assert nombres == {"buscar_facturas", "resumen_proveedor", "iva_credito_mes",
                       "revisiones_pendientes"}
    assert iva["periodo"] == "2026-09" and iva["iva_credito"] > 0
    assert "mes" in error["error"]


# --- token del servidor HTTP --------------------------------------------------------------


def _app_protegida(token: str) -> TestClient:
    interna = Starlette(routes=[Route("/mcp", lambda r: PlainTextResponse("ok"))])
    return TestClient(TokenBearer(interna, hash_token(token)))


def test_http_sin_token_401():
    assert _app_protegida("secreto").get("/mcp").status_code == 401


def test_http_token_incorrecto_401():
    c = _app_protegida("secreto")
    assert c.get("/mcp", headers={"Authorization": "Bearer otro"}).status_code == 401


def test_http_token_correcto():
    c = _app_protegida("secreto")
    r = c.get("/mcp", headers={"Authorization": "Bearer secreto"})
    assert r.status_code == 200 and r.text == "ok"


def test_http_no_arranca_sin_hash():
    with pytest.raises(ValueError):
        TokenBearer(Starlette(), "")
