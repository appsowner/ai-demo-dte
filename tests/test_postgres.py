"""Pruebas de humo contra un Postgres real. Se saltan si no hay TEST_POSTGRES_URL.

Son de solo lectura (todo ocurre en una transacción que se revierte), así que no
modifican datos aunque apunten a una base con información.

    TEST_POSTGRES_URL=postgresql+psycopg://usuario:clave@localhost:5433/dte \\
        uv run pytest tests/test_postgres.py -v
"""

import os

import pytest
from sqlalchemy import text
from sqlmodel import SQLModel

from app.db import models  # noqa: F401  (registra las tablas en el metadata)
from app.db.session import crear_engine

URL = os.getenv("TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(not URL, reason="sin TEST_POSTGRES_URL")


def _en_transaccion_revertida(consulta: str):
    engine = crear_engine(URL)
    with engine.connect() as conn:
        trans = conn.begin()
        try:
            # En Postgres el DDL es transaccional: las tablas creadas aquí desaparecen
            # con el rollback si no existían antes.
            SQLModel.metadata.create_all(conn)
            return conn.execute(text(consulta)).scalar_one()
        finally:
            trans.rollback()


def test_indice_unico_es_parcial():
    definicion = _en_transaccion_revertida(
        "SELECT indexdef FROM pg_indexes WHERE indexname = 'uq_factura_registrada'"
    )
    assert "UNIQUE" in definicion
    assert "WHERE" in definicion and "registrada" in definicion


def test_pgvector_disponible():
    version = _en_transaccion_revertida(
        "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
    )
    assert version
