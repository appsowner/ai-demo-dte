"""Genera el XML de un caso con la estructura de un DTE del SII.

Estructura simplificada: incluye Encabezado (IdDoc, Emisor, Receptor, Totales), Detalle y
Referencia. No incluye TED (timbre) ni firma electrónica: son documentos de prueba.
"""

from __future__ import annotations

from xml.etree import ElementTree as ET

from app.config import TASA_IVA
from samples.cases import AVISO_PRUEBA, RECEPTOR, Caso


def _sub(parent: ET.Element, tag: str, text: object | None = None) -> ET.Element:
    el = ET.SubElement(parent, tag)
    if text is not None:
        el.text = str(text)
    return el


def render_xml(caso: Caso) -> bytes:
    dte = ET.Element("DTE", version="1.0")
    doc = _sub(dte, "Documento")
    doc.set("ID", f"T{caso.tipo_dte}F{caso.folio}")

    enc = _sub(doc, "Encabezado")
    id_doc = _sub(enc, "IdDoc")
    _sub(id_doc, "TipoDTE", caso.tipo_dte)
    _sub(id_doc, "Folio", caso.folio)
    _sub(id_doc, "FchEmis", caso.fecha.isoformat())

    emi = _sub(enc, "Emisor")
    _sub(emi, "RUTEmisor", caso.rut_emisor_efectivo)
    _sub(emi, "RznSoc", caso.emisor.razon_social)
    _sub(emi, "GiroEmis", caso.emisor.giro)
    _sub(emi, "DirOrigen", caso.emisor.direccion)
    _sub(emi, "CmnaOrigen", caso.emisor.comuna)

    rec = _sub(enc, "Receptor")
    _sub(rec, "RUTRecep", caso.rut_receptor_efectivo)
    _sub(rec, "RznSocRecep", RECEPTOR.razon_social)
    _sub(rec, "GiroRecep", RECEPTOR.giro)
    _sub(rec, "DirRecep", RECEPTOR.direccion)
    _sub(rec, "CmnaRecep", RECEPTOR.comuna)

    tot = _sub(enc, "Totales")
    if caso.tipo_dte != 34:
        _sub(tot, "MntNeto", caso.neto)
    if caso.exento:
        _sub(tot, "MntExe", caso.exento)
    if caso.tipo_dte != 34:
        _sub(tot, "TasaIVA", TASA_IVA)
        _sub(tot, "IVA", caso.iva)
    _sub(tot, "MntTotal", caso.total)

    for n, item in enumerate(caso.items, start=1):
        det = _sub(doc, "Detalle")
        _sub(det, "NroLinDet", n)
        if item.exento:
            _sub(det, "IndExe", 1)
        _sub(det, "NmbItem", item.nombre)
        _sub(det, "QtyItem", item.cantidad)
        _sub(det, "PrcItem", item.precio)
        _sub(det, "MontoItem", item.monto)

    if caso.referencia:
        ref = _sub(doc, "Referencia")
        _sub(ref, "NroLinRef", 1)
        _sub(ref, "TpoDocRef", caso.referencia.tipo_dte)
        _sub(ref, "FolioRef", caso.referencia.folio)
        _sub(ref, "FchRef", caso.referencia.fecha.isoformat())
        _sub(ref, "CodRef", 3)  # 3 = corrige montos
        _sub(ref, "RazonRef", caso.referencia.razon)

    ET.indent(dte)
    cuerpo = ET.tostring(dte, encoding="unicode")
    xml = (
        '<?xml version="1.0" encoding="ISO-8859-1"?>\n'
        f"<!-- {AVISO_PRUEBA}. Datos ficticios, sin TED ni firma. -->\n"
        f"{cuerpo}\n"
    )
    return xml.encode("iso-8859-1")
