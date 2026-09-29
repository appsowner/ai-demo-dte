import os

# Base de datos en memoria para tests; se define antes de importar la app.
os.environ.setdefault("DATABASE_URL", "sqlite://")
