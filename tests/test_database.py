from sqlalchemy import select
from sqlalchemy.engine import make_url
from app.models import Base, Run, database


def test_database_url_object_and_postgres_driver():
    engine, sessions = database(make_url('sqlite://'))
    Base.metadata.create_all(engine)
    with sessions() as session:
        assert session.scalar(select(1)) == 1
    engine.dispose()
    # Verifies production driver import and schema compilation without network/DB access.
    postgres, _ = database('postgresql+psycopg://test:test@localhost/test')
    assert postgres.dialect.name == 'postgresql'
    assert 'runs' in str(select(Run).compile(postgres))
    postgres.dispose()
