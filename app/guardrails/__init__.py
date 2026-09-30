"""Guardrails: controles de seguridad que corren antes de las reglas tributarias.

- inyeccion: detecta texto en el documento que intenta dar órdenes al sistema.
- costo: escala la factura si su extracción consumió más de lo razonable.

Ambos devuelven hallazgos del mismo tipo que las reglas, así el agente los trata igual:
cualquier hallazgo manda la factura a revisión humana.
"""
