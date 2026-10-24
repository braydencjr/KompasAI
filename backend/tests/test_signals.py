from fastapi.testclient import TestClient

from app.main import app


def test_signal_engine_is_served_under_api_signals(tmp_path, monkeypatch):
    monkeypatch.setenv("KOMPAS_DB", str(tmp_path / "kompas.db"))
    monkeypatch.setenv("KOMPAS_RADAR", "0")   # no GitHub Trending scrape from a test
    with TestClient(app) as client:          # runs the lifespan, as the real server does
        health = client.get("/api/signals/health").json()
        assert health["ok"] is True and health["latest_snapshot"] is None
        assert {s["stream"] for s in health["ingestion"]["streams"]} >= {"monthly", "groups", "editions"}
        # no snapshot built yet: the API says so instead of returning empty data
        assert client.get("/api/signals/concepts").status_code == 503
        assert client.get("/api/health").json()["status"] == "ok"
