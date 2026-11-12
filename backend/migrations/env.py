"""How Alembic connects to the database. It runs for every Alembic command.

Normally we reuse the app's engine, so migrations always touch the same database as the
app. A caller can pass its own connection instead (the tests do, to migrate a separate
database file) through `config.attributes["connection"]`.
"""

from alembic import context
from sqlalchemy.engine import Connection

import app.models  # noqa: F401  (importing registers every table on Base.metadata)
from app.database import Base, engine


def run_migrations(connection: Connection) -> None:
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


given_connection = context.config.attributes.get("connection")
if given_connection is not None:
    run_migrations(given_connection)
else:
    with engine.connect() as connection:
        run_migrations(connection)
