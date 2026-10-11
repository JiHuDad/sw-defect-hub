"""Small, additive startup migrations; never replace existing scan data."""
from sqlalchemy import inspect, text
from .models import Base


def initialize_database(engine):
    with engine.begin() as connection:
        if connection.dialect.name == 'postgresql':
            # Serialize schema setup across application workers.
            connection.execute(text('SELECT pg_advisory_xact_lock(73644201)'))
        Base.metadata.create_all(connection)
        columns = {column['name'] for column in inspect(connection).get_columns('findings')}
        if 'fix_cl' not in columns:
            connection.execute(text("ALTER TABLE findings ADD COLUMN fix_cl VARCHAR(30) NOT NULL DEFAULT ''"))
