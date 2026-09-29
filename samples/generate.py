"""Genera las facturas de prueba en samples/out/.

Uso:
    uv run python -m samples.generate            # escribe en samples/out/
    uv run python -m samples.generate --out DIR

Salida por caso: <id>.xml y <id>.pdf, más manifest.json con el resultado esperado
de todos los casos, en el orden en que deben procesarse.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from samples.cases import AVISO_PRUEBA, CASOS
from samples.render_pdf import render_pdf
from samples.render_xml import render_xml

SALIDA_DEFAULT = Path(__file__).parent / "out"


def generar(salida: Path = SALIDA_DEFAULT) -> dict:
    salida.mkdir(parents=True, exist_ok=True)
    for caso in CASOS:
        (salida / f"{caso.id}.xml").write_bytes(render_xml(caso))
        (salida / f"{caso.id}.pdf").write_bytes(render_pdf(caso))

    manifest = {
        "aviso": AVISO_PRUEBA,
        "nota": "Procesar en este orden: el caso de duplicado depende de uno anterior.",
        "casos": [c.esperado() for c in CASOS],
    }
    (salida / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Genera facturas DTE de prueba.")
    parser.add_argument("--out", type=Path, default=SALIDA_DEFAULT)
    args = parser.parse_args()
    manifest = generar(args.out)
    n = len(manifest["casos"])
    escalar = sum(1 for c in manifest["casos"] if c["decision"] == "escalar")
    print(f"{n} casos generados en {args.out} ({n - escalar} registrar, {escalar} escalar)")


if __name__ == "__main__":
    main()
