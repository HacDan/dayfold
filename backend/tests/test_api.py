from fastapi.testclient import TestClient


def test_settings_and_feed_auth(data_dir):
    from dayfold.app import app

    with TestClient(app) as c:
        s = c.get("/api/settings").json()
        assert s["values"]["newspaper"]["title"] == "Dayfold"
        assert len(c.get("/api/providers").json()) >= 10
        r = c.put("/api/settings/newspaper", json={"include_charge": True})
        assert r.status_code == 400  # charge requires AI
        assert c.get("/feed/latest.json").status_code == 401
        token = s["values"]["distribution"]["feed_token"]
        assert c.get(f"/feed/latest.json?token={token}").status_code == 404  # no edition yet
