"""Prueba manual de la extracción con el LLM real.

Uso (lee la API key desde .env):
    uv run --env-file .env python -m app.extraction.cli samples/out/c01_valida_ferreteria.pdf
    uv run --env-file .env python -m app.extraction.cli samples/out/*.pdf
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.extraction.schemas import ErrorExtraccion
from app.extraction.service import extraer_documento


def main() -> None:
    parser = argparse.ArgumentParser(description="Extrae datos de uno o más DTE (XML o PDF).")
    parser.add_argument("archivos", nargs="+", type=Path)
    args = parser.parse_args()

    cliente = None
    if any(a.suffix.lower() == ".pdf" for a in args.archivos):
        from app.extraction.llm import crear_cliente

        try:
            cliente = crear_cliente()
        except ErrorExtraccion as e:
            raise SystemExit(f"ERROR: {e}") from e

    costo_total = 0.0
    for archivo in args.archivos:
        print(f"\n=== {archivo.name}")
        try:
            r = extraer_documento(archivo.read_bytes(), cliente_llm=cliente)
        except ErrorExtraccion as e:
            print(f"ERROR: {e}")
            continue
        print(json.dumps(r.factura.model_dump(mode="json"), ensure_ascii=False, indent=2))
        if r.uso:
            costo_total += r.uso.costo_usd
            print(
                f"fuente={r.fuente} modelo={r.uso.modelo} tokens={r.uso.input_tokens}+"
                f"{r.uso.output_tokens} costo=${r.uso.costo_usd:.5f} latencia={r.uso.latencia_ms}ms"
            )
        else:
            print(f"fuente={r.fuente} (sin LLM)")
    print(f"\nCosto total estimado: ${costo_total:.5f} USD")


if __name__ == "__main__":
    main()
