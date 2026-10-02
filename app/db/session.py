"""Conexión a la base de datos.

Desarrollo y tests: SQLite. Producción: Postgres 16 + pgvector. Solo cambia DATABASE_URL:
    sqlite:///./facturas.db
    postgresql+psycopg://usuario:clave@host:5432/base
"""

import os
from collections.abc import Iterator

from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./facturas.db")


def crear_engine(url: str) -> Engine:
    if url.startswith("sqlite"):
        # FastAPI atiende requests en varios threads: la conexión SQLite debe poder cruzarlos.
        return create_engine(url, connect_args={"check_same_thread": False})
    # Postgres: pool de conexiones reutilizables. pool_pre_ping descarta conexiones muertas
    # (reinicio de la base, corte de red) antes de usarlas, en vez de fallar el request.
    return create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=5)


engine = crear_engine(DATABASE_URL)


def create_db() -> None:
    # Importa los modelos para registrarlos en el metadata antes de crear tablas.
    from app.db import models  # noqa: F401

    SQLModel.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
