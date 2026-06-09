from app.main import _safe_static_path


def _setup(tmp_path):
    (tmp_path / "index.html").write_text('<div id="root"></div>')
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "app.js").write_text("console.log(1)")
    return tmp_path.resolve()


def test_serves_existing_file(tmp_path):
    root = _setup(tmp_path)
    assert _safe_static_path("assets/app.js", root) == root / "assets" / "app.js"


def test_unknown_path_falls_back_to_index(tmp_path):
    root = _setup(tmp_path)
    assert _safe_static_path("settings", root) == root / "index.html"


def test_empty_path_returns_index(tmp_path):
    root = _setup(tmp_path)
    assert _safe_static_path("", root) == root / "index.html"


def test_path_traversal_is_blocked(tmp_path):
    root = _setup(tmp_path)
    # Attempting to escape the static root must fall back to index.html,
    # never resolve to a file outside the served directory.
    result = _safe_static_path("../../../../etc/passwd", root)
    assert result == root / "index.html"


def test_mount_spa_serves_index_and_blocks_unknown_api(tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.main import mount_spa

    (tmp_path / "index.html").write_text('<div id="root"></div>')

    app = FastAPI()

    @app.get("/api/ping")
    def ping():
        return {"ok": True}

    mount_spa(app, tmp_path)
    client = TestClient(app)

    # A real API route still wins over the SPA catch-all.
    assert client.get("/api/ping").json() == {"ok": True}
    # An unknown API path returns 404 instead of falling through to the SPA index.
    assert client.get("/api/does-not-exist").status_code == 404
    # A SPA deep link falls back to index.html.
    spa_resp = client.get("/settings")
    assert spa_resp.status_code == 200
    assert "root" in spa_resp.text
