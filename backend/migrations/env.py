"""Explicit database URL prevents accidentally migrating the legacy database."""
import os
from alembic import context
from sqlalchemy import create_engine, pool

url = os.environ.get("DATABASE_URL")
if not url:
    raise RuntimeError("Set DATABASE_URL explicitly before running migrations")
if url.startswith("postgresql://"):
    url = url.replace("postgresql://", "postgresql+psycopg://", 1)

if context.is_offline_mode():
    context.configure(url=url, literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = create_engine(url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection)
        with context.begin_transaction():
            context.run_migrations()
