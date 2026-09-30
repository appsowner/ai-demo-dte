"""Detector de prompt injection en el texto de los documentos.

Busca frases típicas de un ataque: órdenes de ignorar reglas, de aprobar, de saltarse la
revisión o mensajes dirigidos "al sistema". Es determinístico (expresiones regulares), así
que es barato, rápido, explicable y testeable.

No es infalible: un atacante puede redactar la orden de otra forma. Por eso es una capa más,
no la única defensa. Las otras son: el prompt trata el documento como dato, el LLM no tiene
permiso para aprobar y las reglas tributarias se revisan en código.

Importante: el mensaje del hallazgo NO incluye el texto del atacante. Ese mensaje se guarda,
se muestra al revisor y el MCP se lo entrega a Claude; copiar la frase maliciosa ahí sería
volver a inyectarla en otro LLM (inyección de segundo orden).
"""

from __future__ import annotations

import re
import unicodedata

from app.validators.reglas import Codigo, Hallazgo, Severidad

# (patrón, descripción segura para mostrar). Los patrones se aplican sobre texto normalizado:
# minúsculas, sin tildes y con los espacios colapsados.
PATRONES: list[tuple[str, str]] = [
    (r"\bignora\w*\s+(?:todas?\s+)?(?:las\s+|los\s+|tus\s+)?(?:reglas|instrucciones|indicaciones)",
     "orden de ignorar las reglas"),
    (r"\bignore\s+(?:all\s+|any\s+)?(?:the\s+)?(?:previous\s+|prior\s+|above\s+)?"
     r"(?:rules|instructions)",
     "orden de ignorar las reglas (en inglés)"),
    (r"\bmarca\w*\s+(?:esta\s+factura\s+|este\s+documento\s+)?como\s+aprobad",
     "orden de aprobar el documento"),
    (r"\baprueba\w*\s+(?:esta|este)\s+(?:factura|documento)",
     "orden de aprobar el documento"),
    (r"\bno\s+requiere\s+(?:ninguna\s+)?revision",
     "pide saltarse la revisión"),
    (r"\b(?:ya\s+fue|fue|esta)\s+(?:validad|aprobad|revisad)[ao]\s+por\b",
     "afirma estar prevalidado"),
    (r"\bnota\s+para\s+el\s+(?:sistema|asistente|modelo|agente|ia)\b",
     "mensaje dirigido al sistema"),
    (r"(?:^|\s)(?:asistente|assistant|system|sistema)\s*:",
     "mensaje dirigido al sistema"),
    (r"\breporta\w*\s+(?:cero|0|ningun\w*|sin)\s+hallazgo",
     "pide ocultar hallazgos"),
    (r"\b(?:you\s+are\s+now|ahora\s+eres|actua\s+como|act\s+as)\b",
     "intenta cambiar el rol del sistema"),
]

_COMPILADOS = [(re.compile(p), desc) for p, desc in PATRONES]


def normalizar(texto: str) -> str:
    """Minúsculas, sin tildes y con los espacios colapsados, para que 'Revisión' == 'revision'."""
    sin_tildes = "".join(
        c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c)
    )
    return re.sub(r"\s+", " ", sin_tildes.lower()).strip()


def senales(texto: str) -> list[str]:
    """Descripciones (seguras) de los patrones sospechosos encontrados, sin repetir."""
    normal = normalizar(texto)
    encontradas: list[str] = []
    for patron, descripcion in _COMPILADOS:
        if patron.search(normal) and descripcion not in encontradas:
            encontradas.append(descripcion)
    return encontradas


def detectar_inyeccion(texto: str) -> list[Hallazgo]:
    encontradas = senales(texto)
    if not encontradas:
        return []
    return [
        Hallazgo(
            codigo=Codigo.POSIBLE_INYECCION,
            severidad=Severidad.ALTA,
            mensaje=(
                "El documento contiene texto que intenta dar instrucciones al sistema ("
                + "; ".join(encontradas)
                + "). Revisar el documento original antes de aprobar."
            ),
        )
    ]
