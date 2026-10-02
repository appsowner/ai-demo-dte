# Despliegue en Dokploy

Publica dos servicios desde este repo, compartiendo la misma base SQLite (volumen `dte_data`):

| Servicio | Puerto | Dominio sugerido | Protección |
|---|---|---|---|
| `api` (FastAPI + agente) | 8000 | `api-dte.studioai.cl` | Header `X-API-Key` |
| `mcp` (MCP por HTTP, solo lectura) | 8001 | `mcp-dte.studioai.cl` | Header `Authorization: Bearer <token>` |

## 1. Generar secretos (en tu Mac)

```bash
uv run python -m app.api.seguridad                  # API key + API_KEY_SHA256
uv run python -m mcp_server.http_server --nuevo-token   # token MCP + MCP_TOKEN_SHA256
```

Guarda la **API key** y el **token MCP** en tu gestor de contraseñas. En el servidor solo van los hashes.

## 2. Crear el servicio en Dokploy

1. Proyecto → **Create Service → Compose**.
2. **Provider:** GitHub → repo `appsowner/ai-demo-dte` → rama **`main`** → Compose Path `./docker-compose.yml`.
3. **Environment:**
   ```bash
   API_KEY_SHA256=<hash de la API key>
   MCP_TOKEN_SHA256=<hash del token MCP>
   OPENROUTER_API_KEY=<tu key de OpenRouter>
   LLM_PROVIDER=openrouter
   LLM_MODEL=openai/gpt-4o-mini
   ```
4. **Domains:**
   - `api-dte.studioai.cl` → servicio `api`, puerto `8000`, HTTPS.
   - `mcp-dte.studioai.cl` → servicio `mcp`, puerto `8001`, HTTPS.
   (Antes crea los registros DNS tipo A apuntando a la IP del VPS.)
5. **Deploy.**

## 3. Cargar los datos de demo

En Dokploy → servicio `api` → **Terminal** (o `docker exec` en el VPS):

```bash
python -m samples.cargar --reset
```

## 4. Verificar

```bash
curl https://api-dte.studioai.cl/health                                  # {"status":"ok"}
curl https://api-dte.studioai.cl/facturas                                # 401
curl -H "X-API-Key: <tu key>" https://api-dte.studioai.cl/facturas       # 200
curl https://mcp-dte.studioai.cl/mcp                                     # 401
```

En `https://api-dte.studioai.cl/docs`, botón **Authorize** → pega la API key → ya puedes probar los endpoints.

## Notas

- **Rama `main`:** producción se despliega desde `main`. Flujo: `feature/*` → PR a `develop` → cuando está estable, PR `develop` → `main`.
- **Base de datos:** en producción, Postgres 16 + pgvector (servicio `dte-postgres` en Dokploy, sin puerto externo). Ver la sección siguiente. Sin `DATABASE_URL`, la app usa SQLite en el volumen `dte_data`.

## Postgres

1. Dokploy → Database → PostgreSQL, imagen `pgvector/pgvector:pg16`, base `dte`, usuario `dte_app`, sin External Port.
2. Activar pgvector (terminal del servicio):
   ```bash
   psql -U dte_app -d dte -c "CREATE EXTENSION IF NOT EXISTS vector;"
   ```
3. En el Environment del compose:
   ```bash
   DATABASE_URL=postgresql+psycopg://dte_app:<clave>@<app-name-de-la-base>:5432/dte
   ```
   El host es el **App Name** del servicio de base de datos (red interna `dokploy-network`).
4. Deploy y recargar datos de demo: `cd /app && python -m samples.cargar --reset` (contenedor **api**).
5. Verificar que el índice único es parcial (terminal de la base):
   ```bash
   psql -U dte_app -d dte -c "SELECT indexdef FROM pg_indexes WHERE indexname = 'uq_factura_registrada';"
   ```
   Debe terminar en `WHERE ((estado)::text = 'registrada'::text)`.
- **Una sola API key:** para la demo, n8n y el revisor humano usan la misma. En producción serían keys separadas con permisos distintos (ingesta vs. revisión).
