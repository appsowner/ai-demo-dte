"""Autenticación de la API con API key (header X-API-Key).

En el entorno solo se guarda el hash SHA-256 de la key (API_KEY_SHA256), nunca la key.
Si la variable no está definida, la API queda abierta: es el modo de desarrollo local.
En producción siempre debe estar definida.

Generar una key y su hash:
    uv run python -m app.api.seguridad
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from typing import Annotated

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

ENV_VAR = "API_KEY_SHA256"

_api_key_header = APIKeyHeader(
    name="X-API-Key",
    auto_error=False,
    description="API key de la aplicación. En desarrollo local no se exige.",
)


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def verificar_api_key(
    key: Annotated[str | None, Security(_api_key_header)] = None,
) -> None:
    esperado = os.getenv(ENV_VAR, "")
    if not esperado:
        return  # modo desarrollo: sin API key configurada
    if not key or not hmac.compare_digest(hash_key(key), esperado):
        raise HTTPException(
            status_code=401,
            detail="API key inválida o ausente (header X-API-Key)",
            headers={"WWW-Authenticate": "ApiKey"},
        )


def main() -> None:
    key = secrets.token_urlsafe(32)
    print(f"API key (dásela a n8n / al revisor, no se guarda):  {key}")
    print(f"{ENV_VAR} (ponlo en el entorno del servidor):     {hash_key(key)}")


if __name__ == "__main__":
    main()
