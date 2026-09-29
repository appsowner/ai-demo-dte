"""Extracción de texto de un PDF."""

from __future__ import annotations

import io

from pypdf import PdfReader

from app.extraction.schemas import ErrorExtraccion


def extraer_texto(contenido: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(contenido))
        texto = "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as e:  # pypdf lanza distintos tipos según el daño del archivo
        raise ErrorExtraccion(f"PDF ilegible: {e}") from e
    if not texto.strip():
        raise ErrorExtraccion("El PDF no tiene texto extraíble (¿es una imagen escaneada?)")
    return texto
