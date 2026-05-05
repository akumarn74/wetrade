from contextlib import contextmanager

from sqlalchemy import text
from sqlmodel import Session, SQLModel, create_engine

from app.config import settings

engine = create_engine(settings.database_url, echo=False)


def init_db() -> None:
    SQLModel.metadata.create_all(engine)
    _ensure_additive_columns()


def _ensure_additive_columns() -> None:
    # Lightweight additive migration support for local SQLite during MVP iteration.
    if not settings.database_url.startswith('sqlite'):
        return
    with engine.begin() as conn:
        pos_cols = {row[1] for row in conn.execute(text("PRAGMA table_info('position')")).fetchall()}
        if 'underlying' not in pos_cols:
            conn.execute(text("ALTER TABLE position ADD COLUMN underlying TEXT DEFAULT 'SPY'"))
        if 'expiry' not in pos_cols:
            conn.execute(text("ALTER TABLE position ADD COLUMN expiry TEXT DEFAULT ''"))
        if 'strike' not in pos_cols:
            conn.execute(text("ALTER TABLE position ADD COLUMN strike FLOAT DEFAULT 0"))
        if 'option_type' not in pos_cols:
            conn.execute(text("ALTER TABLE position ADD COLUMN option_type TEXT DEFAULT 'CALL'"))
        if 'last_mark_price' not in pos_cols:
            conn.execute(text("ALTER TABLE position ADD COLUMN last_mark_price FLOAT"))

        order_cols = {row[1] for row in conn.execute(text("PRAGMA table_info('order')")).fetchall()}
        if 'underlying' not in order_cols:
            conn.execute(text("ALTER TABLE 'order' ADD COLUMN underlying TEXT DEFAULT 'SPY'"))
        if 'expiry' not in order_cols:
            conn.execute(text("ALTER TABLE 'order' ADD COLUMN expiry TEXT DEFAULT ''"))
        if 'strike' not in order_cols:
            conn.execute(text("ALTER TABLE 'order' ADD COLUMN strike FLOAT DEFAULT 0"))
        if 'option_type' not in order_cols:
            conn.execute(text("ALTER TABLE 'order' ADD COLUMN option_type TEXT DEFAULT 'CALL'"))


@contextmanager
def get_session():
    with Session(engine) as session:
        yield session
