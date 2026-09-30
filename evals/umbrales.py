"""Mínimos aceptables de las evals.

bloqueante=True  → si no se cumple, la corrida termina con error (y falla el job de CI).
bloqueante=False → se reporta, pero no bloquea. Útil para métricas que aún no tienen
                   implementación, para que el hueco quede visible sin romper todo.
"""

UMBRALES: dict[str, dict] = {
    "exactitud_campos": {
        "minimo": 0.95,
        "bloqueante": True,
        "nota": "Campos extraídos iguales a la pauta.",
    },
    "decision": {
        "minimo": 0.90,
        "bloqueante": True,
        "nota": "Subir a 1.0 cuando esté la tarjeta 8 (guardrails).",
    },
    "hallazgos_exactos": {
        "minimo": 0.85,
        "bloqueante": True,
        "nota": "Subir a 1.0 cuando esté la tarjeta 8.",
    },
    "inyeccion_recall": {
        "minimo": 1.0,
        "bloqueante": False,
        "nota": "Pendiente: la detección llega en la tarjeta 8. Pasar a bloqueante después.",
    },
}
