# Corpus de normativa

Documentos que el agente de normativa (fase 2) puede citar.

## Criterios

- **Solo fuentes oficiales:** SII (preguntas frecuentes, guías, normativa) y textos legales.
  Nada de blogs, software contable ni estudios jurídicos: pueden estar desactualizados,
  contradecirse o tener derechos de autor.
- **Alcance acotado:** IVA y documentos tributarios electrónicos (factura, notas de crédito
  y débito, acuse de recibo, Registro de Compras y Ventas).
- **Fuera de alcance a propósito:** renta, remuneraciones y otros impuestos. Sirven para
  probar que el agente responde "no tengo esa información" en vez de inventar.

## Uso

```bash
uv run python -m normativa.descargar        # descarga o actualiza normativa/docs/
```

Cada documento queda en `docs/<id>.md` con su URL, fecha de descarga y hash del contenido.

> Demo de portafolio: corpus acotado. No es asesoría tributaria. Las respuestas del agente
> siempre citan su fuente para que se puedan verificar.
