from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.db.models import EstadoFactura, Factura, Revision


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _factura(**kw) -> Factura:
    base = dict(
        rut_emisor="76123456-0",
        razon_social_emisor="Proveedora Ficticia SpA",
        rut_receptor="77000000-0",
        tipo_dte=33,
        folio=1,
        fecha=date(2026, 9, 1),
        neto=100_000,
        iva=19_000,
        total=119_000,
    )
    base.update(kw)
    return Factura(**base)


def test_crea_factura_y_revision(session: Session) -> None:
    f = _factura()
    session.add(f)
    session.commit()
    session.refresh(f)
    assert f.id is not None
    assert f.estado == EstadoFactura.EN_REVISION

    r = Revision(factura_id=f.id, hallazgos=[{"codigo": "IVA", "severidad": "alta"}])
    session.add(r)
    session.commit()
    session.refresh(r)
    assert r.hallazgos[0]["codigo"] == "IVA"


def test_duplicado_rechazado(session: Session) -> None:
    session.add(_factura())
    session.commit()
    session.add(_factura())
    with pytest.raises(IntegrityError):
        session.commit()
