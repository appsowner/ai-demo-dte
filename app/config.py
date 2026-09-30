"""Parámetros de negocio compartidos por el pipeline, las validaciones y los datos de prueba."""

TASA_IVA = 19
"""Tasa de IVA en Chile, en porcentaje."""

UMBRAL_MONTO_ALTO = 5_000_000
"""Facturas con total igual o superior a este monto (CLP) siempre van a revisión humana."""

# --- Guardrails ------------------------------------------------------------------------------
MAX_CARACTERES_DOCUMENTO = 20_000
"""Texto máximo de un PDF que se envía al LLM. Una factura normal tiene ~1.000 caracteres."""

MAX_TOKENS_ENTRADA_POR_FACTURA = 6_000
"""Una factura normal usa ~900 tokens de entrada. Sobre este límite, se escala."""

MAX_COSTO_USD_POR_FACTURA = 0.005
"""Una factura normal cuesta ~USD 0,0002. Sobre este límite, se escala."""
