"""Genera un PDF simple de un caso, sin dependencias externas.

Escribe PDF 1.4 a mano (una página, fuente Helvetica). Suficiente para que la
extracción con LLM tenga un documento realista que leer.

Si el caso trae `inyeccion_pdf`, ese texto se escribe en letra diminuta y casi
blanca al pie de la página: un humano no lo ve, pero un extractor de texto sí.
Así se simula un ataque de prompt injection escondido en un documento.
"""

from __future__ import annotations

from app.config import TASA_IVA
from samples.cases import AVISO_PRUEBA, RECEPTOR, Caso

NOMBRE_TIPO = {33: "FACTURA ELECTRONICA", 34: "FACTURA NO AFECTA O EXENTA ELECTRONICA",
               61: "NOTA DE CREDITO ELECTRONICA"}


def _clp(monto: int) -> str:
    return "$" + f"{monto:,}".replace(",", ".")


def _escape(texto: str) -> bytes:
    raw = texto.encode("cp1252", errors="replace")
    return raw.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


class _Pagina:
    def __init__(self) -> None:
        self.ops: list[bytes] = []

    def texto(self, x: float, y: float, s: str, size: int = 10, bold: bool = False,
              gris: float = 0.0) -> None:
        fuente = b"/F2" if bold else b"/F1"
        color = f"{gris:.2f} {gris:.2f} {gris:.2f} rg".encode()
        self.ops.append(
            b"BT " + color + b" " + fuente + f" {size} Tf {x:.1f} {y:.1f} Td (".encode()
            + _escape(s) + b") Tj ET"
        )

    def linea(self, x1: float, y1: float, x2: float, y2: float) -> None:
        self.ops.append(f"0 0 0 RG 0.5 w {x1} {y1} m {x2} {y2} l S".encode())

    def rect(self, x: float, y: float, w: float, h: float) -> None:
        self.ops.append(f"0 0 0 RG 1 w {x} {y} {w} {h} re S".encode())

    def contenido(self) -> bytes:
        return b"\n".join(self.ops)


def _armar_pdf(contenido: bytes) -> bytes:
    objetos = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R /F2 5 0 R >> >> /Contents 6 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>",
        b"<< /Length " + str(len(contenido)).encode() + b" >>\nstream\n" + contenido + b"\nendstream",
    ]
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for n, obj in enumerate(objetos, start=1):
        offsets.append(len(out))
        out += f"{n} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objetos) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += (f"trailer\n<< /Size {len(objetos) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n").encode()
    return bytes(out)


def render_pdf(caso: Caso) -> bytes:
    p = _Pagina()
    emi = caso.emisor

    # Aviso de prueba
    p.texto(40, 760, AVISO_PRUEBA, size=11, bold=True, gris=0.45)

    # Emisor
    p.texto(40, 725, emi.razon_social, size=13, bold=True)
    p.texto(40, 709, f"Giro: {emi.giro}", size=9)
    p.texto(40, 696, f"{emi.direccion}, {emi.comuna}", size=9)

    # Recuadro tipo DTE (como en los PDF reales del SII)
    p.rect(390, 668, 182, 72)
    p.texto(402, 722, f"R.U.T.: {caso.rut_emisor_efectivo}", size=10, bold=True)
    p.texto(402, 704, NOMBRE_TIPO[caso.tipo_dte][:28], size=9, bold=True)
    if len(NOMBRE_TIPO[caso.tipo_dte]) > 28:
        p.texto(402, 692, NOMBRE_TIPO[caso.tipo_dte][28:].strip(), size=9, bold=True)
    p.texto(402, 676, f"N° {caso.folio}", size=11, bold=True)

    # Receptor
    y = 640
    p.texto(40, y, f"Fecha emisión: {caso.fecha.strftime('%d-%m-%Y')}", size=10)
    p.texto(40, y - 16, f"Señor(es): {RECEPTOR.razon_social}", size=10)
    p.texto(40, y - 30, f"R.U.T.: {caso.rut_receptor_efectivo}", size=10)
    p.texto(40, y - 44, f"Giro: {RECEPTOR.giro}", size=10)
    p.texto(40, y - 58, f"Dirección: {RECEPTOR.direccion}, {RECEPTOR.comuna}", size=10)

    # Detalle
    y = 550
    p.linea(40, y + 14, 572, y + 14)
    for x, h in ((40, "Descripción"), (330, "Cant."), (400, "Precio"), (490, "Monto")):
        p.texto(x, y, h, size=9, bold=True)
    p.linea(40, y - 6, 572, y - 6)
    y -= 22
    for item in caso.items:
        nombre = item.nombre + (" (EX)" if item.exento else "")
        p.texto(40, y, nombre, size=9)
        p.texto(330, y, str(item.cantidad), size=9)
        p.texto(400, y, _clp(item.precio), size=9)
        p.texto(490, y, _clp(item.monto), size=9)
        y -= 16
    p.linea(40, y + 4, 572, y + 4)

    # Referencia
    if caso.referencia:
        r = caso.referencia
        y -= 14
        p.texto(40, y, f"Referencia: Factura N° {r.folio} del {r.fecha.strftime('%d-%m-%Y')} - {r.razon}",
                size=9)
        y -= 10

    # Totales
    y -= 24
    filas = []
    if caso.tipo_dte != 34:
        filas.append(("Monto neto", caso.neto))
    if caso.exento:
        filas.append(("Monto exento", caso.exento))
    if caso.tipo_dte != 34:
        filas.append((f"IVA {TASA_IVA}%", caso.iva))
    filas.append(("TOTAL", caso.total))
    for etiqueta, monto in filas:
        bold = etiqueta == "TOTAL"
        p.texto(400, y, etiqueta, size=10, bold=bold)
        p.texto(490, y, _clp(monto), size=10, bold=bold)
        y -= 16

    # Pie
    p.texto(40, 80, "Documento generado para pruebas de software. Empresas y RUTs ficticios.",
            size=8, gris=0.45)

    # Texto oculto (prompt injection)
    if caso.inyeccion_pdf:
        p.texto(40, 30, caso.inyeccion_pdf, size=3, gris=0.97)

    return _armar_pdf(p.contenido())
