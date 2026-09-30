"""Lectura determinística de un DTE en XML (sin LLM)."""

from __future__ import annotations

from xml.etree import ElementTree as ET

from pydantic import ValidationError

from app.extraction.schemas import ErrorExtraccion, FacturaExtraida


def _int(enc: ET.Element, ruta: str) -> int:
    valor = enc.findtext(ruta)
    return int(valor) if valor not in (None, "") else 0


def parse_xml(contenido: bytes) -> FacturaExtraida:
    try:
        root = ET.fromstring(contenido)
    except ET.ParseError as e:
        raise ErrorExtraccion(f"XML mal formado: {e}") from e

    enc = root.find("Documento/Encabezado")
    if enc is None:
        raise ErrorExtraccion("El XML no tiene Documento/Encabezado de un DTE")

    try:
        return FacturaExtraida(
            rut_emisor=enc.findtext("Emisor/RUTEmisor", ""),
            razon_social_emisor=enc.findtext("Emisor/RznSoc", ""),
            rut_receptor=enc.findtext("Receptor/RUTRecep", ""),
            tipo_dte=_int(enc, "IdDoc/TipoDTE"),
            folio=_int(enc, "IdDoc/Folio"),
            fecha=enc.findtext("IdDoc/FchEmis", ""),
            neto=_int(enc, "Totales/MntNeto"),
            iva=_int(enc, "Totales/IVA"),
            exento=_int(enc, "Totales/MntExe"),
            total=_int(enc, "Totales/MntTotal"),
        )
    except (ValidationError, ValueError) as e:
        raise ErrorExtraccion(f"Datos del XML inválidos: {e}") from e
