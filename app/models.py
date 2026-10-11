import os
from datetime import datetime, timezone

from sqlalchemy import create_engine, String, Text, Integer, ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy.engine import make_url


def now():
    return datetime.now(timezone.utc).isoformat()


class Base(DeclarativeBase):
    pass


class Run(Base):
    __tablename__ = 'runs'
    id: Mapped[int] = mapped_column(primary_key=True)
    execution_id: Mapped[str] = mapped_column(String(120), unique=True)
    release: Mapped[str] = mapped_column(String(80))
    branch: Mapped[str] = mapped_column(String(80))
    part: Mapped[str] = mapped_column(String(30))
    cl: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(20))
    uploader: Mapped[str] = mapped_column(String(80))
    started_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    finished_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[str] = mapped_column(String(40), default=now)
    metadata_json: Mapped[str] = mapped_column(Text)
    fingerprint: Mapped[str] = mapped_column(String(64))
    __table_args__ = (Index('ix_runs_scope', 'release', 'branch', 'part', 'cl', 'id'),)


class Finding(Base):
    __tablename__ = 'findings'
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey('runs.id'), index=True)
    filename: Mapped[str] = mapped_column(String(240))
    title: Mapped[str] = mapped_column(String(300))
    markdown: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String(64))
    judgment: Mapped[str] = mapped_column(String(30), default='unreviewed')
    progress: Mapped[str] = mapped_column(String(30), default='open')
    fix_cl: Mapped[str] = mapped_column(String(30), default='', server_default='')
    assignee: Mapped[str] = mapped_column(String(80), default='')
    revision: Mapped[int] = mapped_column(Integer, default=1)
    __table_args__ = (UniqueConstraint('run_id', 'filename'),)


class Event(Base):
    __tablename__ = 'events'
    id: Mapped[int] = mapped_column(primary_key=True)
    finding_id: Mapped[int] = mapped_column(ForeignKey('findings.id'), index=True)
    actor: Mapped[str] = mapped_column(String(80))
    kind: Mapped[str] = mapped_column(String(20))
    detail: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(40), default=now)


def database(url=None):
    url = url or os.getenv('DATABASE_URL', 'sqlite:///./defects.db')
    engine = create_engine(url, pool_pre_ping=True,
                           connect_args={'check_same_thread': False, 'timeout': 30} if make_url(url).get_backend_name() == 'sqlite' else {})
    return engine, sessionmaker(engine, expire_on_commit=False)
