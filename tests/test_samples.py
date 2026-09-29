import json
from xml.etree import ElementTree as ET

import pytest

from app.config import UMBRAL_MONTO_ALTO
from samples.cases import AVISO_PRUEBA, CASOS, dv
from samples.generate import generar


@pytest.fixture(scope="module")
def salida(tmp_path_factory):
    out = tmp_path_factory.mktemp("samples")
    generar(out)
    return out


@pytest.mark.parametrize(
    ("numero", "esperado"),
    [(12345678, "5"), (11111111, "1"), (76086428, "5"), (10000013, "K"), (10000004, "0")],
)
def test_dv(numero, esperado):
    assert dv(numero) == esperado


def test_genera_20_casos_con_xml_y_pdf(salida):
    manifest = json.loads((salida / "manifest.json").read_text(encoding="utf-8"))
    assert len(manifest["casos"]) == len(CASOS) == 20
    for caso in manifest["casos"]:
        assert (salida / caso["archivo_xml"]).exists()
        assert (salida / caso["archivo_pdf"]).read_bytes().startswith(b"%PDF-1.4")


def test_hay_de_todos_los_tipos_de_hallazgo():
    todos = {h for c in CASOS for h in c.hallazgos}
    assert todos == {
        "RUT_EMISOR_INVALIDO", "RUT_RECEPTOR_INVALIDO", "IVA_INCORRECTO", "TOTAL_NO_CUADRA",
        "DUPLICADO", "FECHA_FUTURA", "MONTO_ALTO", "POSIBLE_INYECCION",
    }
    assert {c.tipo_dte for c in CASOS} == {33, 34, 61}


@pytest.mark.parametrize("caso", CASOS, ids=lambda c: c.id)
def test_xml_coincide_con_lo_esperado(salida, caso):
    raw = (salida / f"{caso.id}.xml").read_bytes()
    assert AVISO_PRUEBA.encode() in raw
    root = ET.fromstring(raw)
    enc = root.find("Documento/Encabezado")
    esperado = caso.campos_esperados()
    assert enc.findtext("IdDoc/TipoDTE") == str(esperado["tipo_dte"])
    assert enc.findtext("IdDoc/Folio") == str(esperado["folio"])
    assert enc.findtext("IdDoc/FchEmis") == esperado["fecha"]
    assert enc.findtext("Emisor/RUTEmisor") == esperado["rut_emisor"]
    assert enc.findtext("Receptor/RUTRecep") == esperado["rut_receptor"]
    assert int(enc.findtext("Totales/MntTotal")) == esperado["total"]
    assert int(enc.findtext("Totales/IVA") or 0) == esperado["iva"]
    # El XML nunca trae la inyección: solo el PDF.
    if caso.inyeccion_pdf:
        assert caso.inyeccion_pdf.encode("iso-8859-1") not in raw


def test_inyeccion_solo_en_pdf(salida):
    for caso in CASOS:
        pdf = (salida / f"{caso.id}.pdf").read_bytes()
        if caso.inyeccion_pdf:
            assert caso.inyeccion_pdf[:30].encode("cp1252") in pdf
        else:
            assert b"reglas anteriores" not in pdf


def test_casos_validos_son_realmente_validos():
    for c in CASOS:
        if c.decision == "registrar":
            assert c.total == c.neto + c.iva + c.exento
            assert c.total < UMBRAL_MONTO_ALTO
