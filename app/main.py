from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db.session import create_db


@asynccontextmanager
async def lifespan(_: FastAPI):
    create_db()
    yield


app = FastAPI(title="Asistente de Facturas DTE", version="0.1.0", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
