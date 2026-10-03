"""One conservative transaction protocol for PostgreSQL and the local SQLite fallback.

PostgreSQL locks the workspace row before stable-order root locks. This intentionally
serializes writes at lab scale. Long model/validation/network work happens outside it.
"""
from contextlib import contextmanager
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event, select, text

from .schema import workspace


def migrate(url):
    import os
    previous = os.environ.get("WITHAQ_DATABASE_URL")
    os.environ["WITHAQ_DATABASE_URL"] = url
    try:
        root = Path(__file__).resolve().parents[2]
        config = Config(str(root / "alembic.ini"))
        config.set_main_option("script_location", str(root / "migrations"))
        command.upgrade(config, "head")
    finally:
        if previous is None:
            os.environ.pop("WITHAQ_DATABASE_URL", None)
        else:
            os.environ["WITHAQ_DATABASE_URL"] = previous


class Database:
    def __init__(self, url):
        self.engine = create_engine(url, pool_pre_ping=True, hide_parameters=True,
                                    **({"connect_args": {"timeout": 15}} if url.startswith("sqlite") else {}))
        if self.engine.dialect.name == "sqlite":
            @event.listens_for(self.engine, "connect")
            def configure(connection, _):
                connection.execute("PRAGMA foreign_keys=ON")

    @contextmanager
    def transaction(self):
        with self.engine.connect() as db:
            if self.engine.dialect.name == "sqlite":
                db.exec_driver_sql("BEGIN IMMEDIATE")
            else:
                db.begin()
                db.execute(text("SET LOCAL lock_timeout = '5s'"))
                db.execute(select(workspace).where(workspace.c.id == 1).with_for_update()).one()
            try:
                yield db
                db.commit()
            except Exception:
                db.rollback()
                raise

    def ready(self):
        with self.engine.connect() as db:
            return db.execute(text("SELECT version_num FROM alembic_version")).scalar() == "0003"
