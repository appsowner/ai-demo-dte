"""Tests de las métricas de evals y del runner en modo XML (sin LLM)."""

from evals.metricas import (
    CAMPOS,
    ResultadoCaso,
    comparar_campos,
    evaluar_umbrales,
    resumir,
)
from evals.run import ejecutar, reporte_markdown
from evals.umbrales import UMBRALES
from samples.cases import CASOS

ESPERADO = CASOS[0].campos_esperados()


def _caso(**kw) -> ResultadoCaso:
    base = dict(
        id="x", decision_esperada="registrar", decision_obtenida="registrar",
        hallazgos_esperados=[], hallazgos_obtenidos=[],
        campos=dict.fromkeys(CAMPOS, True),
    )
    base.update(kw)
    return ResultadoCaso(**base)


# --- métricas -------------------------------------------------------------------------


def test_comparar_campos_iguales_y_normaliza():
    obtenido = ESPERADO | {"rut_emisor": " " + ESPERADO["rut_emisor"].lower() + " "}
    assert all(comparar_campos(ESPERADO, obtenido).values())


def test_comparar_campos_detecta_diferencia_y_ausencia():
    r = comparar_campos(ESPERADO, ESPERADO | {"iva": 1})
    assert r["iva"] is False and r["total"] is True
    assert not any(comparar_campos(ESPERADO, None).values())


def test_resumir_calcula_proporciones():
    casos = [
        _caso(),
        _caso(decision_obtenida="escalar"),  # decisión mala
        _caso(campos=dict.fromkeys(CAMPOS, True) | {"iva": False}),  # 1 campo malo
        _caso(hallazgos_esperados=["POSIBLE_INYECCION"], decision_esperada="escalar",
              decision_obtenida="registrar"),  # inyección no detectada
    ]
    r = resumir(casos)
    assert r["decision"] == 0.5
    assert r["exactitud_campos"] == round(39 / 40, 4)
    assert r["exactitud_por_campo"]["iva"] == 0.75
    assert r["inyeccion_recall"] == 0.0
    assert r["inyeccion_falsos_positivos"] == 0


def test_falso_positivo_de_inyeccion():
    r = resumir([_caso(hallazgos_obtenidos=["POSIBLE_INYECCION"])])
    assert r["inyeccion_falsos_positivos"] == 1
    assert r["inyeccion_recall"] == 1.0  # no había casos con inyección esperada


def test_umbrales_bloqueantes_y_no_bloqueantes():
    resumen = {"exactitud_campos": 1.0, "decision": 0.5, "hallazgos_exactos": 1.0,
               "inyeccion_recall": 0.0}
    filas = {f["metrica"]: f for f in evaluar_umbrales(resumen, UMBRALES)}
    assert filas["exactitud_campos"]["ok"]
    assert not filas["decision"]["ok"] and filas["decision"]["bloqueante"]
    assert not filas["inyeccion_recall"]["ok"] and filas["inyeccion_recall"]["bloqueante"]


# --- runner completo en XML (sin LLM, gratis) --------------------------------------------


def test_runner_xml_contra_la_pauta():
    casos = ejecutar("xml")
    r = resumir(casos)
    assert r["casos"] == 20 and r["errores"] == 0
    assert r["exactitud_campos"] == 1.0  # el XML se lee con código: perfecto
    # Sin el guardrail (tarjeta 8), las 3 facturas con inyección no se detectan.
    assert r["inyeccion_recall"] == 0.0
    no_detectadas = {c.id for c in casos if c.inyeccion_esperada and not c.inyeccion_detectada}
    assert no_detectadas == {"c17_inyeccion_directa", "c18_inyeccion_sutil",
                             "c19_inyeccion_con_error"}
    # c17 y c18 solo tienen inyección: se registran cuando debían escalarse.
    assert r["decision"] == 0.9
    assert r["costo_total_usd"] == 0.0


def test_runner_filtra_casos_pero_procesa_en_orden():
    casos = ejecutar("xml", casos_ids=["c15_duplicado"])
    assert [c.id for c in casos] == ["c15_duplicado"]
    assert casos[0].hallazgos_obtenidos == ["DUPLICADO"]  # detectó el original c01


def test_reporte_markdown():
    casos = ejecutar("xml", casos_ids=["c01_valida_ferreteria", "c17_inyeccion_directa"])
    resumen = resumir(casos)
    md = reporte_markdown({"fecha": "hoy", "fuente": "xml", "modelo": "-", "prompt": "-"},
                          resumen, evaluar_umbrales(resumen, UMBRALES), casos)
    assert "## Métricas" in md
    assert "c17_inyeccion_directa" in md and "❌ bloquea" in md


def test_runner_pdf_con_guardrails_alcanza_la_pauta():
    """Con un LLM falso que extrae perfecto, el sistema completo debe dar 100% en todo."""
    import re

    from app.extraction.schemas import UsoLLM

    class LLMPerfecto:
        def extraer(self, texto):
            folio = int(re.search(r"N°\s*(\d+)", texto).group(1))
            caso = next(c for c in CASOS if c.folio == folio and c.id != "c15_duplicado")
            uso = UsoLLM(modelo="falso", input_tokens=900, output_tokens=70,
                         costo_usd=0.0002, latencia_ms=5)
            return caso.campos_esperados(), uso

    r = resumir(ejecutar("pdf", LLMPerfecto()))
    assert r["inyeccion_recall"] == 1.0
    assert r["inyeccion_falsos_positivos"] == 0
    assert r["decision"] == 1.0
    assert r["hallazgos_exactos"] == 1.0
    assert all(u["ok"] for u in evaluar_umbrales(r, UMBRALES))
