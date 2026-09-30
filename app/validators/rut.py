"""Validación de RUT chileno (módulo 11)."""

from __future__ import annotations

import re

_PATRON = re.compile(r"^(\d{1,8})-?([\dkK])$")


def calcular_dv(numero: int) -> str:
    suma, factor = 0, 2
    for d in reversed(str(numero)):
        suma += int(d) * factor
        factor = 2 if factor == 7 else factor + 1
    resto = 11 - (suma % 11)
    return {11: "0", 10: "K"}.get(resto, str(resto))


def normalizar(rut: str) -> tuple[int, str] | None:
    """'76.900.043-7' → (76900043, '7'). None si el formato no es de RUT."""
    limpio = rut.strip().replace(".", "").replace(" ", "")
    m = _PATRON.match(limpio)
    if not m:
        return None
    return int(m.group(1)), m.group(2).upper()


def es_valido(rut: str) -> bool:
    partes = normalizar(rut)
    if partes is None:
        return False
    numero, dv = partes
    return numero > 0 and calcular_dv(numero) == dv
