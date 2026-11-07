"""How Alembic connects to the database. It runs for every Alembic command.

We reuse the app's engine, so migrations always touch the same database as the app.
"""

from alembic import context

import app.models  # noqa: F401  (importing registers every table on Base.metadata)
from app.database import Base, engine

with engine.connect() as connection:
    context.configure(
        connection=connection,
        # Lets `alembic revision --autogenerate` compare the models with the real database.
        target_metadata=Base.metadata,
        # SQLite can't change or drop most columns in place. In "batch" mode Alembic instead
        # builds a new table, copies the rows across, and swaps the two.
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()
