from app.db import make_engine


def test_sqlite_url_gets_check_same_thread():
    engine = make_engine("sqlite:///test_tmp.db")
    assert engine.dialect.name == "sqlite"
    assert engine.url.database == "test_tmp.db"


def test_postgres_url_has_no_sqlite_connect_args():
    # Should construct without raising; psycopg driver resolved lazily at connect time.
    engine = make_engine("postgresql+psycopg://u:p@localhost:5432/sprout")
    assert engine.dialect.name == "postgresql"


def test_default_falls_back_to_sqlite_db_path(monkeypatch):
    monkeypatch.delenv("SPROUT_DATABASE_URL", raising=False)
    monkeypatch.setenv("SPROUT_DB_PATH", "fallback.db")
    engine = make_engine()
    assert engine.dialect.name == "sqlite"
    assert engine.url.database == "fallback.db"


def test_database_url_env_wins(monkeypatch):
    monkeypatch.setenv("SPROUT_DATABASE_URL", "postgresql+psycopg://u:p@localhost/sprout")
    engine = make_engine()
    assert engine.dialect.name == "postgresql"
