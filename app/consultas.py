"""Consultas de solo lectura sobre las facturas. Las usa el servidor MCP (tarjeta 6).

Funciones normales que reciben una sesión: se testean sin MCP y sin LLM.
Todas devuelven dicts serializables a JSON (fechas en ISO, montos en pesos enteros).
"""

from __future__ import annotations

from datetime import date

from sqlmodel import Session, select

from app.db.models import DecisionRevision, EstadoFactura, Factura, Revision
from app.validators import rut as rut_mod

TIPO_NOTA_CREDITO = 61
LIMITE_MAXIMO = 100


class ErrorConsulta(ValueError):
    """Parámetros inválidos. El mensaje se muestra tal cual al asistente."""


def normalizar_rut(valor: str) -> str:
    """'76.900.010-0' → '76900010-0'. Acepta el formato con o sin puntos."""
    partes = rut_mod.normalizar(valor)
    if partes is None:
        raise ErrorConsulta(f"'{valor}' no tiene formato de RUT (ej: 76900010-0)")
    numero, dv = partes
    return f"{numero}-{dv}"


def _factura_dict(f: Factura) -> dict:
    return {
        "id": f.id,
        "tipo_dte": f.tipo_dte,
        "folio": f.folio,
        "fecha": f.fecha.isoformat(),
        "rut_emisor": f.rut_emisor,
        "razon_social_emisor": f.razon_social_emisor,
        "neto": f.neto,
        "iva": f.iva,
        "exento": f.exento,
        "total": f.total,
        "estado": f.estado,
    }


def _signo(f: Factura) -> int:
    """Las notas de crédito restan."""
    return -1 if f.tipo_dte == TIPO_NOTA_CREDITO else 1


def buscar_facturas(
    session: Session,
    rut_emisor: str | None = None,
    desde: date | None = None,
    hasta: date | None = None,
    estado: str | None = None,
    limite: int = 50,
) -> dict:
    if estado is not None and estado not in {e.value for e in EstadoFactura}:
        raise ErrorConsulta(f"estado debe ser uno de: {', '.join(e.value for e in EstadoFactura)}")
    if desde and hasta and desde > hasta:
        raise ErrorConsulta("'desde' no puede ser posterior a 'hasta'")
    limite = max(1, min(limite, LIMITE_MAXIMO))

    stmt = select(Factura)
    if rut_emisor:
        stmt = stmt.where(Factura.rut_emisor == normalizar_rut(rut_emisor))
    if desde:
        stmt = stmt.where(Factura.fecha >= desde)
    if hasta:
        stmt = stmt.where(Factura.fecha <= hasta)
    if estado:
        stmt = stmt.where(Factura.estado == estado)

    todas = list(session.exec(stmt.order_by(Factura.fecha, Factura.id)).all())
    return {
        "cantidad": len(todas),
        "mostradas": min(len(todas), limite),
        "facturas": [_factura_dict(f) for f in todas[:limite]],
    }


def resumen_proveedor(session: Session, rut_emisor: str) -> dict:
    rut = normalizar_rut(rut_emisor)
    facturas = list(
        session.exec(select(Factura).where(Factura.rut_emisor == rut).order_by(Factura.fecha)).all()
    )
    if not facturas:
        return {"rut_emisor": rut, "encontrado": False, "mensaje": "No hay facturas de ese RUT."}

    registradas = [f for f in facturas if f.estado == EstadoFactura.REGISTRADA]
    por_estado = {e.value: sum(1 for f in facturas if f.estado == e.value) for e in EstadoFactura}
    return {
        "rut_emisor": rut,
        "encontrado": True,
        "razon_social": facturas[-1].razon_social_emisor,
        "documentos_por_estado": por_estado,
        "total_comprado_registrado": sum(_signo(f) * f.total for f in registradas),
        "iva_credito_registrado": sum(_signo(f) * f.iva for f in registradas),
        "primera_fecha": facturas[0].fecha.isoformat(),
        "ultima_fecha": facturas[-1].fecha.isoformat(),
        "nota": "Totales solo de documentos registrados; las notas de crédito restan.",
    }


def iva_credito_mes(session: Session, anio: int, mes: int) -> dict:
    if not 1 <= mes <= 12:
        raise ErrorConsulta("mes debe estar entre 1 y 12")
    if not 2000 <= anio <= 2100:
        raise ErrorConsulta("anio fuera de rango")

    inicio = date(anio, mes, 1)
    fin = date(anio + 1, 1, 1) if mes == 12 else date(anio, mes + 1, 1)
    del_mes = list(
        session.exec(select(Factura).where(Factura.fecha >= inicio, Factura.fecha < fin)).all()
    )
    registradas = [f for f in del_mes if f.estado == EstadoFactura.REGISTRADA]

    iva_facturas = sum(f.iva for f in registradas if f.tipo_dte != TIPO_NOTA_CREDITO)
    iva_nc = sum(f.iva for f in registradas if f.tipo_dte == TIPO_NOTA_CREDITO)

    por_proveedor: dict[str, dict] = {}
    for f in registradas:
        p = por_proveedor.setdefault(
            f.rut_emisor, {"rut_emisor": f.rut_emisor, "razon_social": f.razon_social_emisor,
                           "iva": 0, "documentos": 0}
        )
        p["iva"] += _signo(f) * f.iva
        p["documentos"] += 1

    return {
        "periodo": f"{anio}-{mes:02d}",
        "iva_credito": iva_facturas - iva_nc,
        "iva_facturas": iva_facturas,
        "iva_notas_credito": iva_nc,
        "documentos_registrados": len(registradas),
        "documentos_excluidos": {
            "en_revision": sum(1 for f in del_mes if f.estado == EstadoFactura.EN_REVISION),
            "rechazada": sum(1 for f in del_mes if f.estado == EstadoFactura.RECHAZADA),
        },
        "por_proveedor": sorted(por_proveedor.values(), key=lambda p: -p["iva"]),
        "nota": "Solo cuentan documentos registrados. Las facturas en revisión no suman "
                "hasta que una persona las apruebe.",
    }


def revisiones_pendientes(session: Session) -> dict:
    pendientes = list(
        session.exec(
            select(Revision)
            .where(Revision.decision == DecisionRevision.PENDIENTE.value)
            .order_by(Revision.id)
        ).all()
    )
    items = []
    for r in pendientes:
        f = session.get(Factura, r.factura_id)
        items.append({
            "revision_id": r.id,
            "motivo": r.motivo,
            "hallazgos": [h.get("codigo") for h in r.hallazgos],
            "factura": _factura_dict(f),
        })
    return {"cantidad": len(items), "pendientes": items}
