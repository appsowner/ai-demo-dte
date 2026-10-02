from app.db.session import normalizar_url


def test_normaliza_urls_de_postgres_al_driver_psycopg():
    esperado = "postgresql+psycopg://u:c@host:5432/dte"
    assert normalizar_url("postgresql://u:c@host:5432/dte") == esperado
    assert normalizar_url("postgres://u:c@host:5432/dte") == esperado
    assert normalizar_url(esperado) == esperado


def test_no_toca_sqlite():
    assert normalizar_url("sqlite:///./facturas.db") == "sqlite:///./facturas.db"
