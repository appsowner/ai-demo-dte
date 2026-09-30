"""Servidor MCP por HTTP, protegido con token Bearer.

Mismo patrón que AgrOwner MCP: en el entorno solo se guarda el hash SHA-256 del token,
nunca el token en texto plano. La comparación es de tiempo constante.

Generar un token y su hash:
    uv run python -m mcp_server.http_server --nuevo-token

Levantar el servidor:
    MCP_TOKEN_SHA256=<hash> uv run python -m mcp_server.http_server   # http://127.0.0.1:8001/mcp
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import os
import secrets

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class TokenBearer:
    """Middleware ASGI: rechaza con 401 toda petición HTTP sin el token correcto."""

    def __init__(self, app: ASGIApp, token_sha256: str) -> None:
        if not token_sha256:
            raise ValueError("Falta MCP_TOKEN_SHA256: el servidor HTTP no arranca sin token")
        self.app = app
        self.token_sha256 = token_sha256

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            headers = dict(scope.get("headers") or [])
            auth = headers.get(b"authorization", b"").decode()
            token = auth[7:] if auth.lower().startswith("bearer ") else ""
            if not token or not hmac.compare_digest(hash_token(token), self.token_sha256):
                resp = JSONResponse({"error": "token inválido o ausente"}, status_code=401)
                await resp(scope, receive, send)
                return
        await self.app(scope, receive, send)


def crear_app():
    from app.db.session import create_db
    from mcp_server.server import mcp

    create_db()
    return TokenBearer(mcp.http_app(), os.getenv("MCP_TOKEN_SHA256", ""))


def main() -> None:
    parser = argparse.ArgumentParser(description="Servidor MCP HTTP con token.")
    parser.add_argument("--nuevo-token", action="store_true", help="Genera un token y su hash")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()

    if args.nuevo_token:
        token = secrets.token_urlsafe(32)
        print(f"Token (dáselo al cliente, no se guarda):  {token}")
        print(f"MCP_TOKEN_SHA256 (ponlo en .env):        {hash_token(token)}")
        return

    import uvicorn

    uvicorn.run(crear_app(), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
