"""Clientes LLM para extraer datos de un PDF con structured outputs.

En ambos proveedores se usa tool calling con la herramienta forzada: el modelo está
obligado a responder llamando a `registrar_extraccion`, cuyo esquema es el JSON Schema
de FacturaExtraida. Así la respuesta siempre llega como JSON y luego Pydantic la valida.

Proveedor según la variable de entorno LLM_PROVIDER:
    openrouter (default) → OPENROUTER_API_KEY, modelo en LLM_MODEL
    anthropic            → ANTHROPIC_API_KEY, modelo en LLM_MODEL
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Protocol

import httpx

from app.extraction.schemas import ErrorExtraccion, FacturaExtraida, UsoLLM

VERSION_PROMPT = "extraccion_v1"
_PROMPT_PATH = Path(__file__).parent / "prompts" / f"{VERSION_PROMPT}.md"

NOMBRE_TOOL = "registrar_extraccion"
DESCRIPCION_TOOL = "Registra los campos extraídos del documento tributario."
MAX_TOKENS_RESPUESTA = 1024
TIMEOUT_S = 60

MODELO_DEFAULT = {
    "openrouter": "openai/gpt-4o-mini",
    "anthropic": "claude-haiku-4-5-20251001",
}

# Precios en USD por millón de tokens (input, output), solo para Anthropic directo.
# OpenRouter informa el costo real en cada respuesta. Verificar antes de reportar costos.
PRECIOS_USD_POR_MTOK: dict[str, tuple[float, float]] = {
    "claude-haiku-4-5-20251001": (1.00, 5.00),
}

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


def cargar_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def costo_usd(modelo: str, input_tokens: int, output_tokens: int) -> float:
    precio_in, precio_out = PRECIOS_USD_POR_MTOK.get(modelo, (0.0, 0.0))
    return round((input_tokens * precio_in + output_tokens * precio_out) / 1_000_000, 6)


def mensaje_usuario(texto_documento: str) -> str:
    return f"<documento>\n{texto_documento}\n</documento>"


def _schema() -> dict:
    return FacturaExtraida.model_json_schema()


class ClienteLLM(Protocol):
    """Lo que el servicio de extracción necesita de un LLM. Permite mockear en tests."""

    def extraer(self, texto_documento: str) -> tuple[dict, UsoLLM]: ...


class ClienteOpenRouter:
    """API compatible con OpenAI. Permite usar modelos de distintos proveedores."""

    def __init__(
        self,
        modelo: str | None = None,
        api_key: str | None = None,
        http: httpx.Client | None = None,
    ) -> None:
        self.modelo = modelo or os.getenv("LLM_MODEL") or MODELO_DEFAULT["openrouter"]
        key = api_key or os.getenv("OPENROUTER_API_KEY")
        if not key:
            raise ErrorExtraccion("Falta OPENROUTER_API_KEY en el entorno (.env)")
        self._http = http or httpx.Client(timeout=TIMEOUT_S)
        self._headers = {
            "Authorization": f"Bearer {key}",
            "X-Title": "ai-demo-dte",
        }
        self._system = cargar_prompt()

    def extraer(self, texto_documento: str) -> tuple[dict, UsoLLM]:
        payload = {
            "model": self.modelo,
            "max_tokens": MAX_TOKENS_RESPUESTA,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": self._system},
                {"role": "user", "content": mensaje_usuario(texto_documento)},
            ],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": NOMBRE_TOOL,
                        "description": DESCRIPCION_TOOL,
                        "parameters": _schema(),
                    },
                }
            ],
            "tool_choice": {"type": "function", "function": {"name": NOMBRE_TOOL}},
            "usage": {"include": True},  # OpenRouter devuelve el costo real
        }
        inicio = time.perf_counter()
        resp = self._http.post(OPENROUTER_URL, headers=self._headers, json=payload)
        latencia_ms = int((time.perf_counter() - inicio) * 1000)
        if resp.status_code != 200:
            raise ErrorExtraccion(f"OpenRouter respondió {resp.status_code}: {resp.text[:300]}")

        cuerpo = resp.json()
        datos: dict = {}
        try:
            llamadas = cuerpo["choices"][0]["message"].get("tool_calls") or []
            for llamada in llamadas:
                if llamada["function"]["name"] == NOMBRE_TOOL:
                    datos = json.loads(llamada["function"]["arguments"])
                    break
        except (KeyError, IndexError, json.JSONDecodeError) as e:
            raise ErrorExtraccion(f"Respuesta de OpenRouter inesperada: {e}") from e

        usage = cuerpo.get("usage") or {}
        uso = UsoLLM(
            modelo=cuerpo.get("model", self.modelo),
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
            costo_usd=float(usage.get("cost") or 0.0),
            latencia_ms=latencia_ms,
        )
        return datos, uso


class ClienteAnthropic:
    def __init__(self, modelo: str | None = None, api_key: str | None = None) -> None:
        import anthropic  # import tardío: los tests no necesitan el SDK

        self.modelo = modelo or os.getenv("LLM_MODEL") or MODELO_DEFAULT["anthropic"]
        self._client = anthropic.Anthropic(api_key=api_key or os.getenv("ANTHROPIC_API_KEY"))
        self._system = cargar_prompt()
        self._tool = {
            "name": NOMBRE_TOOL,
            "description": DESCRIPCION_TOOL,
            "input_schema": _schema(),
        }

    def extraer(self, texto_documento: str) -> tuple[dict, UsoLLM]:
        inicio = time.perf_counter()
        resp = self._client.messages.create(
            model=self.modelo,
            max_tokens=MAX_TOKENS_RESPUESTA,
            temperature=0,
            system=self._system,
            tools=[self._tool],
            tool_choice={"type": "tool", "name": NOMBRE_TOOL},
            messages=[{"role": "user", "content": mensaje_usuario(texto_documento)}],
        )
        latencia_ms = int((time.perf_counter() - inicio) * 1000)

        datos = next(
            (b.input for b in resp.content if b.type == "tool_use" and b.name == NOMBRE_TOOL),
            None,
        )
        uso = UsoLLM(
            modelo=self.modelo,
            input_tokens=resp.usage.input_tokens,
            output_tokens=resp.usage.output_tokens,
            costo_usd=costo_usd(self.modelo, resp.usage.input_tokens, resp.usage.output_tokens),
            latencia_ms=latencia_ms,
        )
        return (datos or {}), uso


def crear_cliente(proveedor: str | None = None) -> ClienteLLM:
    proveedor = (proveedor or os.getenv("LLM_PROVIDER") or "openrouter").lower()
    if proveedor == "openrouter":
        return ClienteOpenRouter()
    if proveedor == "anthropic":
        return ClienteAnthropic()
    raise ErrorExtraccion(f"LLM_PROVIDER desconocido: {proveedor}")
