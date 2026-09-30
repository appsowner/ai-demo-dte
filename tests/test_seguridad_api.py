"""Tests de la API key. Sin LLM: solo se usan endpoints que no llaman al modelo."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.api.seguridad import ENV_VAR, hash_key
from app.db.session import get_session
from app.main import app

KEY = "clave-de-prueba"


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    def _session():
        with Session(engine) as s:
            yield s

    app.dependency_overrides[get_session] = _session
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_sin_configurar_la_api_queda_abierta(client, monkeypatch):
    monkeypatch.delenv(ENV_VAR, raising=False)
    assert client.get("/facturas").status_code == 200


def test_con_key_configurada_exige_header(client, monkeypatch):
    monkeypatch.setenv(ENV_VAR, hash_key(KEY))
    assert client.get("/facturas").status_code == 401
    assert client.get("/revisiones").status_code == 401
    assert client.post("/revisiones/1", json={"decision": "aprobada"}).status_code == 401
    assert client.post("/facturas", files={"archivo": ("x.xml", b"<x/>")}).status_code == 401


def test_key_incorrecta(client, monkeypatch):
    monkeypatch.setenv(ENV_VAR, hash_key(KEY))
    r = client.get("/facturas", headers={"X-API-Key": "otra"})
    assert r.status_code == 401


def test_key_correcta(client, monkeypatch):
    monkeypatch.setenv(ENV_VAR, hash_key(KEY))
    r = client.get("/facturas", headers={"X-API-Key": KEY})
    assert r.status_code == 200


def test_health_y_docs_siempre_abiertos(client, monkeypatch):
    monkeypatch.setenv(ENV_VAR, hash_key(KEY))
    assert client.get("/health").status_code == 200
    assert client.get("/docs").status_code == 200
