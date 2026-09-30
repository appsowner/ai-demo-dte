# Ingesta con n8n

Flujo que recibe una factura (XML o PDF) desde un formulario web y la envía a la API del agente.

```
Formulario web ──► Filtrar XML/PDF ──► POST /facturas (X-API-Key) ──► decisión del agente
 (On form submission)   (Code)            (HTTP Request)                 registrar | escalar
```

- **Formulario:** campo `archivo` (tipo File, `.xml,.pdf`).
- **Filtrar XML/PDF:** deja pasar solo adjuntos `.xml`/`.pdf` y los expone como binario `archivo`. Es el mismo código que sirve para una entrada por correo (recorre todos los adjuntos del item).
- **HTTP Request:** `POST https://api-dte.studioai.cl/facturas`, multipart con el campo `archivo`, autenticado con Header Auth `X-API-Key`.

## Importar

1. n8n → **Import from File** → `ingesta-formulario.json`.
2. Crea la credencial **Header Auth**: Name `X-API-Key`, Value = tu API key (ver `docs/DEPLOY.md`). El JSON no trae la key, solo la referencia a la credencial.
3. Ajusta la URL del HTTP Request si tu API usa otro dominio.
4. **Publish** y abre la URL de producción del formulario.

## Probar

Facturas de prueba en `pruebas/` (datos ficticios, folios que no están en la carga inicial):

| Archivo | Resultado esperado |
|---|---|
| `f3001_valida_ferreteria.xml` | `registrar` |
| `f3002_iva_incorrecto.xml` | `escalar` (`IVA_INCORRECTO`) → queda en `GET /revisiones` |
| `f3003_valida_consultora.xml` | `registrar` |

Subir dos veces el mismo archivo → `escalar` por duplicado (regla anti-duplicados).

## Por qué formulario y no correo

Se probó el Email Trigger (IMAP) con Gmail: la credencial conectaba, pero el trigger no disparaba de forma confiable. Para la demo se eligió el formulario (cero dependencias externas). La alternativa robusta para correo es el nodo **Gmail Trigger** (API de Google con OAuth), pendiente como mejora.
