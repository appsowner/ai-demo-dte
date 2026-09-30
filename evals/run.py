"""Corre las evals: las 20 facturas de prueba por el agente completo, contra la pauta.

Uso:
    uv run --env-file .env python -m evals.run                 # PDF con LLM real (~USD 0,004)
    uv run --env-file .env python -m evals.run --casos c10,c17 # solo algunos casos
    uv run python -m evals.run --fuente xml                    # XML, sin LLM, gratis

Cada corrida usa una base de datos en memoria (limpia) y una fecha fija, para que el
resultado sea reproducible. Escribe un reporte en evals/reports/ (markdown + JSON).
Termina con código 1 si alguna métrica bloqueante no alcanza su mínimo.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, date, datetime
from pathlib import Path

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.agent.procesar import procesar_documento
from app.extraction.llm import VERSION_PROMPT, ClienteLLM
from app.extraction.schemas import ErrorExtraccion
from evals.metricas import ResultadoCaso, comparar_campos, evaluar_umbrales, resumir
from evals.umbrales import UMBRALES
from samples.cases import CASOS
from samples.render_pdf import render_pdf
from samples.render_xml import render_xml

HOY = date(2026, 9, 30)  # fecha fija: la pauta asume este "hoy"
SALIDA_DEFAULT = Path(__file__).parent / "reports"


def ejecutar(
    fuente: str = "pdf",
    cliente_llm: ClienteLLM | None = None,
    casos_ids: list[str] | None = None,
    hoy: date = HOY,
) -> list[ResultadoCaso]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    render = render_pdf if fuente == "pdf" else render_xml

    resultados: list[ResultadoCaso] = []
    with Session(engine) as session:
        # Se procesan TODOS en orden (el duplicado depende de uno anterior), pero solo se
        # reportan los pedidos con --casos.
        for caso in CASOS:
            esperado = caso.esperado()
            try:
                r = procesar_documento(
                    render(caso), session=session, cliente_llm=cliente_llm, hoy=hoy
                )
            except ErrorExtraccion as e:
                session.rollback()
                res = ResultadoCaso(
                    id=caso.id,
                    decision_esperada=esperado["decision"],
                    decision_obtenida=None,
                    hallazgos_esperados=esperado["hallazgos"],
                    hallazgos_obtenidos=[],
                    campos=comparar_campos(esperado["campos"], None),
                    error=str(e),
                )
            else:
                uso = r.uso_llm
                res = ResultadoCaso(
                    id=caso.id,
                    decision_esperada=esperado["decision"],
                    decision_obtenida=r.decision,
                    hallazgos_esperados=esperado["hallazgos"],
                    hallazgos_obtenidos=sorted(h.codigo.value for h in r.hallazgos),
                    campos=comparar_campos(esperado["campos"], r.factura.model_dump(mode="json")),
                    costo_usd=uso.costo_usd if uso else 0.0,
                    input_tokens=uso.input_tokens if uso else 0,
                    output_tokens=uso.output_tokens if uso else 0,
                    latencia_ms=uso.latencia_ms if uso else 0,
                )
            if casos_ids is None or caso.id in casos_ids:
                resultados.append(res)
    return resultados


def _pct(valor: float) -> str:
    return f"{valor * 100:.1f}%"


def reporte_markdown(meta: dict, resumen: dict, umbrales: list[dict],
                     casos: list[ResultadoCaso]) -> str:
    lineas = [
        "# Reporte de evals — Asistente de Facturas DTE",
        "",
        f"- Fecha: {meta['fecha']}",
        f"- Fuente: {meta['fuente']} · Modelo: {meta['modelo']} · Prompt: {meta['prompt']}",
        f"- Casos: {resumen['casos']} · Errores: {resumen['errores']}",
        "",
        "## Métricas",
        "",
        "| Métrica | Valor | Mínimo | Estado |",
        "|---|---|---|---|",
    ]
    for u in umbrales:
        if u["ok"]:
            estado = "✅"
        else:
            estado = "❌ bloquea" if u["bloqueante"] else "⚠️ no bloqueante"
        lineas.append(f"| {u['metrica']} | {_pct(u['valor'])} | {_pct(u['minimo'])} | {estado} |")
    lineas += [
        "",
        f"Falsos positivos de inyección: {resumen['inyeccion_falsos_positivos']}",
        "",
        "## Costo y latencia",
        "",
        f"- Costo total: USD {resumen['costo_total_usd']:.5f} "
        f"(promedio USD {resumen['costo_promedio_usd']:.6f} por factura)",
        f"- Tokens: {resumen['tokens_entrada']} entrada + {resumen['tokens_salida']} salida",
        f"- Latencia: promedio {resumen['latencia_promedio_ms']} ms · "
        f"p95 {resumen['latencia_p95_ms']} ms",
        "",
        "## Exactitud por campo",
        "",
        "| Campo | Exactitud |",
        "|---|---|",
    ]
    lineas += [f"| {c} | {_pct(v)} |" for c, v in resumen["exactitud_por_campo"].items()]
    lineas += [
        "",
        "## Detalle por caso",
        "",
        "| Caso | Decisión (esperada → obtenida) | Hallazgos esperados | Hallazgos obtenidos "
        "| Campos con error |",
        "|---|---|---|---|---|",
    ]
    for c in casos:
        marca = "✅" if c.decision_ok and c.hallazgos_ok and not c.campos_fallidos else "❌"
        decision = f"{c.decision_esperada} → {c.decision_obtenida or 'ERROR'}"
        fallidos = f"ERROR: {c.error[:120]}" if c.error else (", ".join(c.campos_fallidos) or "—")
        lineas.append(
            f"| {marca} {c.id} | {decision} | {', '.join(c.hallazgos_esperados) or '—'} "
            f"| {', '.join(c.hallazgos_obtenidos) or '—'} | {fallidos} |"
        )
    return "\n".join(lineas) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Corre las evals contra la pauta.")
    parser.add_argument("--fuente", choices=["pdf", "xml"], default="pdf")
    parser.add_argument("--casos", help="Lista de ids separados por coma (ej: c10,c17)")
    parser.add_argument("--salida", type=Path, default=SALIDA_DEFAULT)
    args = parser.parse_args()

    cliente = None
    if args.fuente == "pdf":
        from app.extraction.llm import crear_cliente

        try:
            cliente = crear_cliente()
        except ErrorExtraccion as e:
            raise SystemExit(f"ERROR: {e}") from e

    ids = [x.strip() for x in args.casos.split(",")] if args.casos else None
    casos = ejecutar(args.fuente, cliente, ids)
    errores = {c.error for c in casos if c.error}
    if casos and len(errores) == 1 and all(c.error for c in casos):
        # Un mismo error en todos los casos es de configuración (key, crédito, red), no de
        # calidad del modelo: no se reportan puntajes que no significan nada.
        raise SystemExit(f"Todas las facturas fallaron con el mismo error:\n  {errores.pop()}")
    resumen = resumir(casos)
    umbrales = evaluar_umbrales(resumen, UMBRALES)

    ahora = datetime.now(UTC)
    meta = {
        "fecha": ahora.isoformat(timespec="seconds"),
        "fuente": args.fuente,
        "modelo": getattr(cliente, "modelo", "sin LLM (XML)"),
        "prompt": VERSION_PROMPT if args.fuente == "pdf" else "—",
    }

    args.salida.mkdir(parents=True, exist_ok=True)
    nombre = f"{ahora:%Y%m%d-%H%M%S}-{args.fuente}"
    md = reporte_markdown(meta, resumen, umbrales, casos)
    (args.salida / f"{nombre}.md").write_text(md, encoding="utf-8")
    (args.salida / f"{nombre}.json").write_text(
        json.dumps({"meta": meta, "resumen": resumen, "umbrales": umbrales,
                    "casos": [c.__dict__ for c in casos]}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(md)
    print(f"Reporte: {args.salida / (nombre + '.md')}")

    fallan = [u["metrica"] for u in umbrales if u["bloqueante"] and not u["ok"]]
    if fallan:
        raise SystemExit(f"Métricas bajo el mínimo: {', '.join(fallan)}")


if __name__ == "__main__":
    main()
