import os

# Base de datos en memoria para tests; se define antes de importar la app.
os.environ.setdefault("DATABASE_URL", "sqlite://")

# Los tests nunca envían trazas, aunque el .env tenga OBS_PROVIDER configurado.
os.environ["OBS_PROVIDER"] = "none"
