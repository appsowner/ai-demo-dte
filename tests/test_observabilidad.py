"""Tests de observabilidad. No usan LangSmith ni Langfuse: se prueba la lógica propia."""

import pytest

from app import observabilidad as obs
from app.extraction.schemas import UsoLLM

USO = UsoLLM(modelo="m", input_tokens=10, output_tokens=5, costo_usd=0.0001, latencia_ms=7)


class ClienteFalso:
    modelo = "openai/gpt-4o-mini"

    def __init__(self):
        self.textos = []

    def extraer(self, texto_documento):
        self.textos.append(texto_documento)
        return {"folio": 1}, USO


def test_por_defecto_no_se_traza(monkeypatch):
    monkeypatch.delenv("OBS_PROVIDER", raising=False)
    assert obs.proveedor() == "none"
    with obs.traza_factura({"origen": "test"}) as traza:
        assert traza.config == {}
        traza.resultado({"decision": "registrar"})  # no hace nada, no falla
    obs.flush()


def test_proveedor_desconocido(monkeypatch):
    monkeypatch.setenv("OBS_PROVIDER", "datadog")
    with pytest.raises(ValueError, match="OBS_PROVIDER"):
        obs.proveedor()


def test_el_archivo_original_nunca_se_envia():
    datos = {"contenido": b"%PDF-1.4 ...", "otro": 1}
    assert obs.enmascarar(datos, ocultar=False) == {"contenido": "<12 bytes>", "otro": 1}


def test_texto_del_documento_solo_se_oculta_si_se_pide():
    datos = {"extraccion": {"texto_documento": "RUT 76.900.010-0", "fuente": "pdf"}}
    visible = obs.enmascarar(datos, ocultar=False)
    oculto = obs.enmascarar(datos, ocultar=True)
    assert visible["extraccion"]["texto_documento"] == "RUT 76.900.010-0"
    assert oculto["extraccion"]["texto_documento"] == "<oculto: 16 caracteres>"
    assert oculto["extraccion"]["fuente"] == "pdf"


def test_enmascara_modelos_pydantic_y_listas():
    assert obs.enmascarar([USO], ocultar=True)[0]["input_tokens"] == 10


def test_ocultar_contenido_desde_entorno(monkeypatch):
    monkeypatch.setenv("OBS_OCULTAR_CONTENIDO", "true")
    assert obs.ocultar_contenido() is True
    monkeypatch.setenv("OBS_OCULTAR_CONTENIDO", "false")
    assert obs.ocultar_contenido() is False


def test_cliente_observado_delega_sin_proveedor(monkeypatch):
    monkeypatch.setenv("OBS_PROVIDER", "none")
    falso = ClienteFalso()
    cliente = obs.ClienteObservado(falso, "openrouter")
    assert cliente.modelo == "openai/gpt-4o-mini"
    assert cliente.extraer("texto") == ({"folio": 1}, USO)
    assert falso.textos == ["texto"]


def test_modelo_y_proveedor_para_costos():
    assert obs._modelo_y_proveedor("openai/gpt-4o-mini", "openrouter") == ("gpt-4o-mini", "openai")
    esperado = ("claude-haiku-4-5", "anthropic")
    assert obs._modelo_y_proveedor("claude-haiku-4-5", "anthropic") == esperado


def test_enmascarar_json_para_atributos_otel():
    texto = '{"contenido": "JVBERi0xLjQ=", "decision": "escalar"}'
    esperado = '{"contenido": "<oculto: 12 caracteres>", "decision": "escalar"}'
    assert obs.enmascarar_json(texto) == esperado
    assert obs.enmascarar_json("no es json") == "no es json"
    sin_cambios = '{"decision": "registrar"}'
    assert obs.enmascarar_json(sin_cambios) is sin_cambios


def test_metadata_segura_para_langfuse():
    meta = obs.metadata_segura({"origen": "api", "archivo": "x" * 300, "mal-clave": "a", "n": None})
    assert meta == {"origen": "api", "archivo": "x" * 200}
