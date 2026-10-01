# Observabilidad: LangSmith vs Langfuse Cloud

El mismo agente se conecta a uno u otro con una variable de entorno (`app/observabilidad.py`):

```bash
OBS_PROVIDER=none        # default: no se traza nada
OBS_PROVIDER=langsmith   # LANGSMITH_API_KEY, LANGSMITH_PROJECT
OBS_PROVIDER=langfuse    # LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_BASE_URL
OBS_OCULTAR_CONTENIDO=true   # opcional: no envía el texto de la factura
```

## Qué queda registrado

Por cada factura, una traza `procesar-factura`:

```
procesar-factura (agent)        input: archivo y tamaño
│                               output: decisión, motivo, hallazgos, folio, RUT emisor
│                               tags: ai-demo-dte, origen:api | origen:evals
│                               metadata: origen, archivo o caso de eval
└── ejecutar-grafo              (grafo LangGraph; en LangSmith es la raíz)
    ├── extraer
    │   └── extraer-datos-factura (generation, solo PDF)
    │                           modelo, tokens, costo USD real (OpenRouter), versión del prompt
    ├── seguridad
    ├── validar
    ├── decidir
    │   └── elegir_camino       (arista condicional: registrar o escalar)
    └── registrar | escalar
```

Criterios (buenas prácticas de Langfuse): nombres estáticos y con verbo, sin el nombre del
modelo; una traza por unidad de trabajo (una factura); input/output de la raíz con lo que un
revisor necesita ver, no el estado completo; `generation` para la llamada al LLM; `agent` para
la corrida del agente; entorno separado con `LANGFUSE_TRACING_ENVIRONMENT`.

Verificado en Langfuse con `c17_inyeccion_directa`: la generación queda anidada dentro de
`extraer`, el costo (USD 0,000181) y los tokens (994) suben hasta la traza, y el `motivo` del
escalamiento no copia el texto del atacante.

## Privacidad

- El archivo original (bytes del XML/PDF) **nunca** se envía: se reemplaza por su tamaño.
- Langfuse: enmascarado en la etapa de exportación (`mask_otel_spans`), que cubre también los spans del CallbackHandler. LangSmith: `Client(hide_inputs=..., hide_outputs=...)`.
- Con `OBS_OCULTAR_CONTENIDO=true` tampoco se envía el texto del documento.
- Los campos extraídos (RUT, montos, decisión) sí se envían: son lo que se necesita para depurar.
- En este repo todas las facturas son sintéticas. Con datos reales, ocultar el contenido o autoalojar el proveedor de trazas.

## Cómo probar

```bash
# LangSmith
OBS_PROVIDER=langsmith uv run --env-file .env python -m evals.run --casos c01,c10,c17

# Langfuse
OBS_PROVIDER=langfuse uv run --env-file .env python -m evals.run --casos c01,c10,c17
```

- `c01`: factura válida → registrar.
- `c10`: IVA incorrecto → escalar.
- `c17`: prompt injection → escalar por guardrail.

## Comparación

Probado con el mismo caso (`c17_inyeccion_directa`, PDF con prompt injection) en ambos.

| Criterio | LangSmith | Langfuse Cloud |
|---|---|---|
| Quién lo hace | LangChain (mismo equipo que LangGraph) | Langfuse (open source, MIT) |
| Autoalojable | Solo plan Enterprise | Sí (Docker; v3+ necesita varios servicios) |
| Integración con LangGraph | Nativa: `LangChainTracer`, casi sin código | `CallbackHandler` + observación raíz propia |
| Raíz de la traza | El grafo (`procesar-factura`) | Observación `agent` propia (`procesar-factura`) con el grafo dentro |
| Input/output de la raíz | El estado completo del grafo (más detalle, más datos expuestos) | Curado: archivo/tamaño → decisión, motivo, hallazgos |
| Llamada al LLM | Anidada en `extraer`, modelo y 994 tokens | Anidada en `extraer`, costo real USD 0,000181 y 994 tokens |
| Enmascarado | `Client(hide_inputs/hide_outputs)`: el PDF aparece como `<2948 bytes>` | `mask_otel_spans` en la exportación: ídem |
| Filtrar trazas | Metadata (`caso`, `origen`) y tags | Tags (`origen:evals`), metadata y entorno |
| Código propio necesario | Menos (~20 líneas) | Más (~40 líneas: raíz, atributos, generación) |
| Encontrar una factura escalada | Filtro por metadata `caso` | Búsqueda por input (`c17`) o tag |

## Conclusión

- **Para depurar durante el desarrollo, LangSmith**: se integra con LangGraph sin esfuerzo y
  muestra el estado completo de cada nodo.
- **Para producción con datos tributarios, Langfuse**: es open source y se puede autoalojar
  (los datos no salen de la infraestructura propia), el enmascarado se aplica en un solo punto
  (exportación) y la traza muestra un input/output curado, pensado para quien revisa.
- El agente no depende de ninguno: se cambia con `OBS_PROVIDER` y, por defecto, no traza nada.
