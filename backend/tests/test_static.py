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
