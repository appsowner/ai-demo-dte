"""Punto de entrada de la extracción: decide el camino según el tipo de archivo."""

from __future__ import annotations

from pydantic import ValidationError

from app.extraction.llm import VERSION_PROMPT, ClienteLLM
from app.extraction.pdf_text import extraer_texto
from app.extraction.schemas import ErrorExtraccion, FacturaExtraida, ResultadoExtraccion
from app.extraction.xml_parser import parse_xml


def detectar_formato(contenido: bytes) -> str:
    inicio = contenido.lstrip()[:5]
    if inicio.startswith(b"%PDF"):
        return "pdf"
    if inicio.startswith(b"<"):
        return "xml"
    raise ErrorExtraccion("Formato no soportado: se espera un DTE en XML o PDF")


def extraer_documento(
    contenido: bytes, cliente_llm: ClienteLLM | None = None
) -> ResultadoExtraccion:
    """XML → parser determinístico. PDF → texto + LLM con salida estructurada."""
    formato = detectar_formato(contenido)

    if formato == "xml":
        return ResultadoExtraccion(factura=parse_xml(contenido), fuente="xml")

    if cliente_llm is None:
        raise ErrorExtraccion("Se necesita un cliente LLM para leer PDFs")

    texto = extraer_texto(contenido)
    datos, uso = cliente_llm.extraer(texto)
    try:
        factura = FacturaExtraida.model_validate(datos)
    except ValidationError as e:
        n = e.error_count()
        raise ErrorExtraccion(f"El LLM devolvió datos inválidos: {n} errores") from e

    return ResultadoExtraccion(
        factura=factura,
        fuente="pdf",
        texto_documento=texto,
        uso=uso,
        version_prompt=VERSION_PROMPT,
    )
