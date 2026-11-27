import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
_tmp = tempfile.mkdtemp(prefix="lantern_test_")
os.environ["APP_DB"] = str(Path(_tmp) / "import.db")
os.environ["UPLOAD_DIR"] = str(Path(_tmp) / "uploads")
os.environ["ANALYZE_URL"] = ""
os.environ["TRUSTED_HOSTS"] = "127.0.0.1,::1,testclient"
# login and the private bot are switched on per test (the real .env may set them)
os.environ["LANTERN_PASSWORD"] = ""
os.environ["BOT_PASSWORD"] = ""
os.environ["TELEGRAM_ALLOWED_USERS"] = ""

MOCK = ROOT / "mock"


@pytest.fixture
def mock_dir():
    if not (MOCK / "signals.json").is_file():
        pytest.skip("mock/ not present (unzip lantern_mock.zip into the repo root)")
    return MOCK


@pytest.fixture
def make_client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from app import analyze as analyze_mod
    from app import main
    from app.timeutil import clock

    verdicts = {}

    def fake_analyze(url, timeout, photo, filename, content_type, comment):
        rel = verdicts.get(filename, "accept")
        if isinstance(rel, dict):  # a full answer, e.g. {"note": "webcam screenshot"}
            return {"relevant": "accept", "score": 0.9, "hint": "snow", "note": "", **rel}
        return {"relevant": rel, "score": 0.9, "hint": "snow", "note": f"test verdict {rel}"}

    monkeypatch.setattr(analyze_mod, "analyze", fake_analyze)

    def factory():
        app = main.build_app(db_path=tmp_path / "lantern.db", start_ticker=False)
        return TestClient(app), app.state.engine, clock, verdicts

    yield factory
    clock.reset()
