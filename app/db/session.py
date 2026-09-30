import os
from collections.abc import Iterator

from sqlmodel import Session, SQLModel, create_engine

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./facturas.db")

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})


def create_db() -> None:
    # Importa los modelos para registrarlos en el metadata antes de crear tablas.
    from app.db import models  # noqa: F401

    SQLModel.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
