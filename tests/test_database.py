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


def test_additive_fix_cl_migration_preserves_legacy_data_and_is_idempotent(tmp_path):
    from sqlalchemy import text
    from app.models import Finding, Event
    from app.migrations import initialize_database
    engine, sessions = database(f'sqlite:///{tmp_path}/legacy.db')
    Base.metadata.create_all(engine)
    with sessions() as session:
        run = Run(execution_id='legacy', release='SVR26B', branch='INTEG', part='VP', cl='123',
                  status='completed', uploader='Tester', metadata_json='{}', fingerprint='hash')
        session.add(run); session.flush()
        finding = Finding(run_id=run.id, filename='a.md', title='Original', markdown='# Original\r\n',
                          sha256='hash', judgment='confirmed', progress='fixed', revision=3)
        session.add(finding); session.flush()
        session.add(Event(finding_id=finding.id, actor='Tester', kind='comment', detail='{"text":"preserve"}'))
        session.commit()
    # Match the previous schema, which had no fix_cl column.
    with engine.begin() as connection:
        connection.execute(text('ALTER TABLE findings DROP COLUMN fix_cl'))
    initialize_database(engine); initialize_database(engine)
    with sessions() as session:
        finding = session.scalar(select(Finding))
        assert finding.fix_cl == '' and finding.markdown == '# Original\r\n'
        assert finding.progress == 'fixed' and finding.revision == 3
        assert session.scalar(select(Event)).detail == '{"text":"preserve"}'
        assert session.scalar(select(Run)).execution_id == 'legacy'
    engine.dispose()
