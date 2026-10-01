"""Observabilidad: trazas del agente en LangSmith o Langfuse.

Se elige con variables de entorno (por defecto no se traza nada):

    OBS_PROVIDER=none | langsmith | langfuse
    OBS_OCULTAR_CONTENIDO=true    # no envía el texto de la factura al proveedor

LangSmith:  LANGSMITH_API_KEY, LANGSMITH_PROJECT (default "ai-demo-dte")
Langfuse:   LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_BASE_URL,
            LANGFUSE_TRACING_ENVIRONMENT (development / production)

Qué se registra por cada factura (una traza = una factura procesada):
  procesar-factura (agent)       input: archivo y tamaño · output: decisión, motivo, hallazgos
  └── ejecutar-grafo             (en LangSmith el grafo es la raíz)
      ├── extraer
      │   └── extraer-datos-factura   (solo PDF, generation) modelo, tokens, costo, prompt
      ├── seguridad → validar → decidir → registrar | escalar

Privacidad: el archivo original (bytes) nunca se envía; se reemplaza por su tamaño.
Con OBS_OCULTAR_CONTENIDO=true tampoco se envía el texto del documento. Los campos
extraídos (RUT, montos) sí se envían: son lo que se necesita para depurar.

Los SDK se importan solo si se activan: sin OBS_PROVIDER no se usan.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from pydantic import BaseModel

from app.extraction.schemas import UsoLLM

PROVEEDORES = ("none", "langsmith", "langfuse")

# Nombres estáticos, verbo primero y sin el modelo (buenas prácticas de Langfuse):
# permiten filtrar y comparar aunque cambie el modelo.
NOMBRE_TRAZA = "procesar-factura"
NOMBRE_LLM = "extraer-datos-factura"
NOMBRE_GRAFO = "ejecutar-grafo"  # en Langfuse, el grafo cuelga de la raíz con otro nombre
TAGS = ["ai-demo-dte"]
PROYECTO_DEFAULT = "ai-demo-dte"
MAX_METADATA = 200  # Langfuse: valores de metadata ≤ 200 caracteres

# "contenido" es el archivo original: nunca se envía. "texto_documento"/"documento" es el
# texto del PDF: se envía salvo que OBS_OCULTAR_CONTENIDO=true.
CLAVE_ARCHIVO = "contenido"
CLAVES_TEXTO = {"texto_documento", "documento"}


# --- Configuración ---------------------------------------------------------------------------


def proveedor() -> str:
    p = (os.getenv("OBS_PROVIDER") or "none").strip().lower()
    if p not in PROVEEDORES:
        raise ValueError(f"OBS_PROVIDER desconocido: {p!r} (opciones: {', '.join(PROVEEDORES)})")
    return p


def ocultar_contenido() -> bool:
    valor = os.getenv("OBS_OCULTAR_CONTENIDO", "false").strip().lower()
    return valor in {"1", "true", "si", "sí", "yes"}


# --- Enmascarado -----------------------------------------------------------------------------


def _resumen(valor: Any) -> str:
    if isinstance(valor, (bytes, bytearray)):
        return f"<{len(valor)} bytes>"
    if isinstance(valor, str):
        return f"<oculto: {len(valor)} caracteres>"
    return "<oculto>"


def enmascarar(data: Any, ocultar: bool | None = None) -> Any:
    """Prepara datos para enviarlos al proveedor de trazas sin exponer el documento."""
    if ocultar is None:
        ocultar = ocultar_contenido()
    if isinstance(data, (bytes, bytearray)):
        return _resumen(data)
    if isinstance(data, BaseModel):
        data = data.model_dump(mode="json")
    if isinstance(data, dict):
        salida = {}
        for clave, valor in data.items():
            if clave == CLAVE_ARCHIVO and valor is not None:
                salida[clave] = _resumen(valor)
            elif ocultar and clave in CLAVES_TEXTO and isinstance(valor, str):
                salida[clave] = _resumen(valor)
            else:
                salida[clave] = enmascarar(valor, ocultar)
        return salida
    if isinstance(data, (list, tuple)):
        return [enmascarar(v, ocultar) for v in data]
    return data


def enmascarar_json(texto: str) -> str:
    """Versión para atributos OpenTelemetry, donde input/output viajan como JSON en texto."""
    try:
        data = json.loads(texto)
    except (ValueError, TypeError):
        return texto
    enmascarado = enmascarar(data)
    return texto if enmascarado == data else json.dumps(enmascarado, ensure_ascii=False)


def _mascara_otel(*, params: Any) -> Any:
    """Enmascarado en la etapa de exportación (Langfuse v4): cubre también los spans que
    crea el CallbackHandler de LangChain, no solo los que crea este módulo."""
    from langfuse.types import MaskOtelSpansResult, OtelSpanPatch

    parches = {}
    for identificador, span in params.spans.items():
        cambios = {}
        for clave, valor in dict(span.attributes or {}).items():
            if isinstance(valor, str) and clave.endswith((".input", ".output")):
                nuevo = enmascarar_json(valor)
                if nuevo != valor:
                    cambios[clave] = nuevo
        if cambios:
            parches[identificador] = OtelSpanPatch(set_attributes=cambios)
    return MaskOtelSpansResult(span_patches=parches) if parches else None


def _mascara_legacy(*, data: Any = None, **_: Any) -> Any:
    return enmascarar(data)


def metadata_segura(metadata: dict | None) -> dict[str, str]:
    """Langfuse exige metadata dict[str, str], claves alfanuméricas y valores ≤ 200 chars."""
    return {
        str(k): str(v)[:MAX_METADATA]
        for k, v in (metadata or {}).items()
        if v is not None and str(k).isalnum()
    }


# --- Clientes (se crean una sola vez y solo si se usan) --------------------------------------


@lru_cache
def _langfuse():
    from langfuse import Langfuse

    try:
        return Langfuse(mask_otel_spans=_mascara_otel)
    except TypeError:  # SDK sin enmascarado en exportación: usar el mask clásico
        return Langfuse(mask=_mascara_legacy)


@lru_cache
def _langsmith():
    from langsmith import Client

    return Client(hide_inputs=enmascarar, hide_outputs=enmascarar)


def _proyecto_langsmith() -> str:
    return os.getenv("LANGSMITH_PROJECT") or PROYECTO_DEFAULT


def flush() -> None:
    """Envía las trazas pendientes. Llamar al final de scripts cortos (evals, carga)."""
    p = proveedor()
    if p == "langfuse":
        _langfuse().flush()
    elif p == "langsmith":
        cliente = _langsmith()
        if hasattr(cliente, "flush"):
            cliente.flush()


# --- Traza de una factura --------------------------------------------------------------------


@dataclass
class Traza:
    """Lo que necesita quien procesa una factura: la config para el grafo y dónde anotar."""

    config: dict = field(default_factory=dict)
    _al_terminar: Callable[[Any], None] | None = None

    def resultado(self, datos: Any) -> None:
        if self._al_terminar:
            self._al_terminar(enmascarar(datos))


@contextmanager
def traza_factura(
    metadata: dict | None = None, entrada: dict | None = None
) -> Iterator[Traza]:
    """Abre la traza de una factura. Uso:

    with traza_factura({"origen": "api"}, entrada={"archivo": "f.xml", "bytes": 1200}) as t:
        final = grafo.invoke(estado, config=t.config)
        t.resultado({"decision": final["decision"]})
    """
    p = proveedor()
    if p == "none":
        yield Traza()
        return

    meta = metadata_segura(metadata)
    tags = TAGS + ([f"origen:{meta['origen']}"] if "origen" in meta else [])
    config: dict = {"run_name": NOMBRE_TRAZA, "tags": tags, "metadata": meta}

    if p == "langsmith":
        import langsmith as ls
        from langchain_core.tracers import LangChainTracer

        cliente, proyecto = _langsmith(), _proyecto_langsmith()
        config["callbacks"] = [LangChainTracer(client=cliente, project_name=proyecto)]
        # tracing_context habilita también los @traceable anidados (la llamada al LLM).
        with ls.tracing_context(enabled=True, client=cliente, project_name=proyecto):
            yield Traza(config)
        return

    # Langfuse v4: observación raíz de tipo "agent" (una corrida del agente = una traza).
    # propagate_attributes pasa nombre, tags y metadata a todas las observaciones hijas,
    # incluidas las del grafo (CallbackHandler) y la generación del LLM.
    from langfuse import propagate_attributes
    from langfuse.langchain import CallbackHandler

    lf = _langfuse()
    with lf.start_as_current_observation(
        as_type="agent", name=NOMBRE_TRAZA, input=enmascarar(entrada or {})
    ) as raiz:
        with propagate_attributes(trace_name=NOMBRE_TRAZA, tags=tags, metadata=meta):
            # Si el grafo se llamara igual que la raíz, la traza mostraría dos
            # "procesar-factura" anidados.
            config["run_name"] = NOMBRE_GRAFO
            config["callbacks"] = [CallbackHandler()]
            yield Traza(config, lambda datos: raiz.update(output=datos))


# --- Llamada al LLM --------------------------------------------------------------------------


def _modelo_y_proveedor(modelo: str, proveedor_llm: str) -> tuple[str, str]:
    """"openai/gpt-4o-mini" → ("gpt-4o-mini", "openai"): así lo espera LangSmith para costos."""
    if "/" in modelo:
        prov, nombre = modelo.split("/", 1)
        return nombre, prov
    return modelo, proveedor_llm


def trazar_llm(
    texto: str, modelo: str, proveedor_llm: str, llamar: Callable[[], tuple[dict, UsoLLM]]
) -> tuple[dict, UsoLLM]:
    """Ejecuta la llamada al LLM registrándola como 'generation' con tokens y costo."""
    p = proveedor()
    if p == "none":
        return llamar()

    from app.extraction.llm import VERSION_PROMPT  # import tardío: evita ciclo

    entrada = {"documento": texto if not ocultar_contenido() else _resumen(texto)}

    if p == "langsmith":
        from langsmith import traceable

        nombre, prov = _modelo_y_proveedor(modelo, proveedor_llm)
        resultado: dict = {}

        def _llm(documento: str) -> dict:
            datos, uso = llamar()
            resultado["datos"], resultado["uso"] = datos, uso
            return {
                "output": datos,
                "usage_metadata": {
                    "input_tokens": uso.input_tokens,
                    "output_tokens": uso.output_tokens,
                    "total_tokens": uso.input_tokens + uso.output_tokens,
                    "total_cost": uso.costo_usd,
                },
            }

        traceable(
            run_type="llm",
            name=NOMBRE_LLM,
            metadata={"ls_provider": prov, "ls_model_name": nombre, "prompt": VERSION_PROMPT},
        )(_llm)(entrada["documento"])
        return resultado["datos"], resultado["uso"]

    lf = _langfuse()
    with lf.start_as_current_observation(
        as_type="generation",
        name=NOMBRE_LLM,
        model=modelo,
        input=entrada,
        metadata={"prompt": VERSION_PROMPT, "proveedorllm": proveedor_llm},
    ) as gen:
        datos, uso = llamar()
        gen.update(
            output=datos,
            # Costo real informado por OpenRouter: no depende de la tabla de precios.
            usage_details={"input": uso.input_tokens, "output": uso.output_tokens},
            cost_details={"total": uso.costo_usd},
            metadata={"latenciams": str(uso.latencia_ms)},
        )
    return datos, uso


class ClienteObservado:
    """Envuelve un cliente LLM para que cada llamada quede en la traza."""

    def __init__(self, cliente: Any, proveedor_llm: str) -> None:
        self._cliente = cliente
        self._proveedor_llm = proveedor_llm
        self.modelo = getattr(cliente, "modelo", "desconocido")

    def extraer(self, texto_documento: str) -> tuple[dict, UsoLLM]:
        return trazar_llm(
            texto_documento,
            self.modelo,
            self._proveedor_llm,
            lambda: self._cliente.extraer(texto_documento),
        )
