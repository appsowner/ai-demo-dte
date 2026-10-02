"""Descarga el corpus de normativa (normativa/fuentes.toml) a normativa/docs/.

Uso (en tu equipo, necesita internet):
    uv run python -m normativa.descargar            # descarga todo
    uv run python -m normativa.descargar --solo ley-19983,sii-uso-credito-fiscal

Por cada fuente genera normativa/docs/<id>.md con un encabezado (url, fecha, hash) y el texto.
- PDF  → texto con pypdf (página por página)
- HTML → texto principal con trafilatura (descarta menús y pie de página)
El hash permite saber si un documento cambió desde la última descarga (lo usará la ingesta).
"""

from __future__ import annotations

import argparse
import hashlib
import io
import re
import sys
import time
import tomllib
from datetime import UTC, datetime
from pathlib import Path

import httpx

BASE = Path(__file__).parent
FUENTES = BASE / "fuentes.toml"
DOCS = BASE / "docs"
UA = "ai-demo-dte/0.1 (demo de portafolio; corpus de normativa publica del SII)"
PAUSA_S = 1.0  # cortesía con el servidor del SII


def cargar_fuentes() -> list[dict]:
    return tomllib.loads(FUENTES.read_text(encoding="utf-8"))["fuente"]


def texto_pdf(contenido: bytes) -> str:
    from pypdf import PdfReader

    lector = PdfReader(io.BytesIO(contenido))
    paginas = [p.extract_text() or "" for p in lector.pages]
    return "\n\n".join(t.strip() for t in paginas if t.strip())


def decodificar(contenido: bytes) -> str:
    """Las páginas del SII mezclan UTF-8 y Windows-1252 (Latin-1). Si se adivina mal,
    aparecen caracteres rotos ("Electrˇnica", "żA partir") que arruinan la búsqueda."""
    try:
        return contenido.decode("utf-8")
    except UnicodeDecodeError:
        return contenido.decode("cp1252", errors="replace")


# Restos de navegación y maquetación que no aportan contenido y meten ruido en la búsqueda.
RUIDO = re.compile(
    r"^(compartir|normativa relacionada|preguntas frecuentes|volver|ir a siguiente paso"
    r"|\(ver imagen\))$",
    re.IGNORECASE,
)


def limpiar(texto: str) -> str:
    lineas = []
    for linea in texto.splitlines():
        linea = re.sub(r"\(ver imagen\)", "", linea, flags=re.IGNORECASE)
        linea = re.sub(r"[ \t]+", " ", linea).strip()
        sin_tabla = linea.replace("|", "").replace("\\", "").strip()
        if not sin_tabla or RUIDO.match(sin_tabla):
            continue  # filas de tabla vacías ("|  |  |") y botones de navegación
        lineas.append(linea)
    return "\n".join(lineas)


def texto_html(contenido: bytes) -> str:
    import trafilatura

    texto = trafilatura.extract(decodificar(contenido), include_tables=True, favor_recall=True)
    if not texto:
        raise ValueError("no se pudo extraer el texto principal del HTML")
    return texto.strip()


def es_pdf(url: str, resp: httpx.Response) -> bool:
    return url.lower().endswith(".pdf") or "pdf" in resp.headers.get("content-type", "")


def documento(fuente: dict, texto: str) -> str:
    # El título va también en el cuerpo: muchas FAQ del SII traen solo la respuesta,
    # y la pregunta ayuda a que la búsqueda encuentre el documento.
    texto = f"# {fuente['titulo']}\n\n{limpiar(texto)}"
    sha = hashlib.sha256(texto.encode("utf-8")).hexdigest()
    encabezado = "\n".join([
        "---",
        f"id: {fuente['id']}",
        f"titulo: \"{fuente['titulo']}\"",
        f"tipo: {fuente['tipo']}",
        f"url: {fuente['url']}",
        f"descargado: {datetime.now(UTC).isoformat(timespec='seconds')}",
        f"sha256: {sha}",
        "---",
    ])
    return f"{encabezado}\n\n{texto}\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Descarga el corpus de normativa.")
    parser.add_argument("--solo", help="ids separados por coma")
    args = parser.parse_args()

    fuentes = cargar_fuentes()
    if args.solo:
        pedidos = {x.strip() for x in args.solo.split(",")}
        fuentes = [f for f in fuentes if f["id"] in pedidos]

    DOCS.mkdir(parents=True, exist_ok=True)
    errores = 0
    with httpx.Client(timeout=30, follow_redirects=True, headers={"User-Agent": UA}) as http:
        for f in fuentes:
            try:
                resp = http.get(f["url"])
                resp.raise_for_status()
                if es_pdf(f["url"], resp):
                    texto = texto_pdf(resp.content)
                else:
                    texto = texto_html(resp.content)
                destino = DOCS / f"{f['id']}.md"
                destino.write_text(documento(f, texto), encoding="utf-8")
                print(f"✔ {f['id']:<38} {len(texto):>7} caracteres")
            except Exception as e:  # una fuente caída no detiene el resto
                errores += 1
                print(f"✘ {f['id']:<38} {e}", file=sys.stderr)
            time.sleep(PAUSA_S)

    print(f"\n{len(fuentes) - errores} descargadas, {errores} con error → {DOCS}")
    if errores:
        sys.exit(1)


if __name__ == "__main__":
    main()
