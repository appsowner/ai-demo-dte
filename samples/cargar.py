"""Carga las facturas de prueba (XML) en la base de datos usando el agente.

No usa LLM (los XML se leen con código), así que no gasta crédito.
Sirve para tener datos que consultar desde el servidor MCP o la API.

Uso:
    uv run python -m samples.cargar           # falla si la base ya tiene facturas
    uv run python -m samples.cargar --reset   # borra todo y vuelve a cargar
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import date

from sqlmodel import Session, SQLModel, select

from app.agent.procesar import procesar_documento
from app.db.models import Factura
from app.db.session import create_db, engine
from samples.generate import SALIDA_DEFAULT, generar


def cargar(session: Session, hoy: date) -> Counter:
    if not (SALIDA_DEFAULT / "manifest.json").exists():
        generar(SALIDA_DEFAULT)
    manifest = json.loads((SALIDA_DEFAULT / "manifest.json").read_text(encoding="utf-8"))

    conteo: Counter = Counter()
    for caso in manifest["casos"]:  # en orden: el duplicado depende de un caso anterior
        contenido = (SALIDA_DEFAULT / caso["archivo_xml"]).read_bytes()
        r = procesar_documento(contenido, session=session, cliente_llm=None, hoy=hoy)
        conteo[r.decision] += 1
        marca = "✔" if r.decision == "registrar" else "⚠"
        print(f"{marca} {caso['id']:<28} {r.decision:<9} {', '.join(h.codigo for h in r.hallazgos)}")
    return conteo


def main() -> None:
    parser = argparse.ArgumentParser(description="Carga las facturas de prueba en la base.")
    parser.add_argument("--reset", action="store_true", help="Borra la base antes de cargar")
    args = parser.parse_args()

    if args.reset:
        SQLModel.metadata.drop_all(engine)
    create_db()

    with Session(engine) as s:
        if s.exec(select(Factura.id)).first() is not None:
            raise SystemExit("La base ya tiene facturas. Usa --reset para borrarla y recargar.")
        conteo = cargar(s, hoy=date.today())

    print(f"\n{conteo['registrar']} registradas, {conteo['escalar']} en revisión humana.")


if __name__ == "__main__":
    main()
