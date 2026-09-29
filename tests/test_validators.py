"""Tests de las reglas tributarias. Sin LLM ni red."""

from datetime import date

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.config import UMBRAL_MONTO_ALTO
from app.db.models import Factura
from app.db.repositorio import existe_factura
from app.extraction.schemas import FacturaExtraida
from app.validators import rut
from app.validators.reglas import Codigo, Severidad, iva_esperado, validar
from samples.cases import CASOS

HOY = date(2026, 9, 30)


def _factura(**kw) -> FacturaExtraida:
    base = dict(
        rut_emisor="76900010-0", razon_social_emisor="Ferretería Ficticia",
        rut_receptor="76900001-1", tipo_dte=33, folio=1, fecha=date(2026, 9, 1),
        neto=100_000, iva=19_000, exento=0, total=119_000,
    )
    base.update(kw)
    return FacturaExtraida(**base)


def _codigos(hallazgos) -> list[str]:
    return sorted(h.codigo.value for h in hallazgos)


# --- RUT ------------------------------------------------------------------------


@pytest.mark.parametrize(
    "valor",
    ["12345678-5", "12.345.678-5", "11111111-1", "10000013-K", "10000013-k", "10000004-0",
     " 76900010-0 ", "123456785"],
)
def test_rut_valido(valor):
    assert rut.es_valido(valor)


@pytest.mark.parametrize(
    "valor", ["12345678-4", "12345678-K", "", "abc", "12345678-", "0-0", "123456789-5"]
)
def test_rut_invalido(valor):
    assert not rut.es_valido(valor)


def test_normalizar():
    assert rut.normalizar("76.900.043-7") == (76900043, "7")
    assert rut.normalizar("no-es-rut") is None


# --- reglas una por una ---------------------------------------------------------------


def test_factura_limpia_sin_hallazgos():
    assert validar(_factura(), hoy=HOY) == []


@pytest.mark.parametrize(("neto", "iva"), [(3_999, 760), (1, 0), (3, 1), (250_000, 47_500)])
def test_iva_esperado_redondeo(neto, iva):
    assert iva_esperado(neto) == iva


def test_iva_tolera_un_peso():
    assert validar(_factura(iva=19_001, total=119_001), hoy=HOY) == []


def test_iva_incorrecto():
    h = validar(_factura(iva=18_000, total=118_000), hoy=HOY)
    assert _codigos(h) == ["IVA_INCORRECTO"]
    assert "esperado $19.000" in h[0].mensaje


def test_exenta_con_iva_es_error():
    h = validar(_factura(tipo_dte=34, neto=0, iva=1_000, exento=50_000, total=51_000), hoy=HOY)
    assert _codigos(h) == ["IVA_INCORRECTO"]


def test_exenta_correcta():
    assert validar(_factura(tipo_dte=34, neto=0, iva=0, exento=50_000, total=50_000), hoy=HOY) == []


def test_total_no_cuadra():
    assert _codigos(validar(_factura(total=120_000), hoy=HOY)) == ["TOTAL_NO_CUADRA"]


def test_ruts_invalidos():
    h = validar(_factura(rut_emisor="76900010-5", rut_receptor="76900001-9"), hoy=HOY)
    assert _codigos(h) == ["RUT_EMISOR_INVALIDO", "RUT_RECEPTOR_INVALIDO"]


def test_duplicado():
    assert _codigos(validar(_factura(), hoy=HOY, es_duplicado=True)) == ["DUPLICADO"]


def test_fecha_futura_y_hoy():
    assert _codigos(validar(_factura(fecha=date(2026, 10, 1)), hoy=HOY)) == ["FECHA_FUTURA"]
    assert validar(_factura(fecha=HOY), hoy=HOY) == []


def test_monto_alto_es_severidad_media():
    neto = 4_300_000
    iva = iva_esperado(neto)
    h = validar(_factura(neto=neto, iva=iva, total=neto + iva), hoy=HOY)
    assert _codigos(h) == ["MONTO_ALTO"]
    assert h[0].severidad == Severidad.MEDIA
    assert neto + iva >= UMBRAL_MONTO_ALTO


# --- contra los 20 casos de prueba -------------------------------------------------------


def test_reglas_coinciden_con_los_20_casos():
    """Procesa el lote en orden, como lo hará el agente, y compara con la pauta."""
    vistos: set[tuple[str, int, int]] = set()
    for caso in CASOS:
        factura = FacturaExtraida.model_validate(caso.campos_esperados())
        clave = (factura.rut_emisor, factura.tipo_dte, factura.folio)
        hallazgos = validar(factura, hoy=HOY, es_duplicado=clave in vistos)
        vistos.add(clave)

        # POSIBLE_INYECCION lo detecta el guardrail (tarjeta 8), no las reglas.
        esperados = sorted(c for c in caso.hallazgos if c != "POSIBLE_INYECCION")
        assert _codigos(hallazgos) == esperados, caso.id


def test_codigos_cubren_la_pauta():
    pauta = {c for caso in CASOS for c in caso.hallazgos} - {"POSIBLE_INYECCION"}
    assert pauta == {c.value for c in Codigo}


# --- duplicados en base de datos -------------------------------------------------------------


def test_existe_factura_en_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        assert not existe_factura(s, "76900010-0", 33, 1001)
        s.add(Factura(rut_emisor="76900010-0", razon_social_emisor="X", rut_receptor="76900001-1",
                      tipo_dte=33, folio=1001, fecha=date(2026, 9, 1), neto=1, iva=0, total=1))
        s.commit()
        assert existe_factura(s, "76900010-0", 33, 1001)
        assert not existe_factura(s, "76900010-0", 61, 1001)  # otro tipo: no es duplicado
