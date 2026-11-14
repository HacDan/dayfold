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
        assert s["values"]["device"]["screensaver_cover"] is False  # sleep screen is opt-in
        assert c.put("/api/settings/device", json={"screensaver_cover": True}).json()["screensaver_cover"] is True


def test_provider_with_several_sections(data_dir):
    from dayfold.app import app

    with TestClient(app) as c:
        p = c.get("/api/providers").json()[0]
        body = {k: p[k] for k in ("name", "base_url", "language", "usage_mode", "license_name",
                                  "license_url", "license_note", "enabled", "max_items")}
        r = c.put(f"/api/providers/{p['id']}", json={**body, "categories": ["ciencia", "saude", "ciencia"]})
        assert r.status_code == 200, r.text
        assert r.json()["categories"] == ["ciencia", "saude"] and r.json()["category"] == "ciencia"
        assert c.put(f"/api/providers/{p['id']}", json={**body, "categories": []}).status_code == 422
        legacy = c.put(f"/api/providers/{p['id']}", json={**body, "category": "mundo"}).json()
        assert legacy["categories"] == ["mundo"]


def test_kindle_settings_hide_the_app_password(data_dir):
    from dayfold.app import app

    with TestClient(app) as c:
        k = c.get("/api/settings").json()["values"]["kindle"]
        assert k["mode"] == "koreader" and k["native_games"] is False and k["gmail_app_password_set"] is False
        r = c.put("/api/settings/kindle", json={"mode": "native", "kindle_email": "eu_123@kindle.com",
                                                "gmail_address": "eu@gmail.com",
                                                "gmail_app_password": "abcd efgh ijkl mnop"})
        assert r.status_code == 200 and r.json()["gmail_app_password"] == "" and r.json()["gmail_app_password_set"]
        # saving the form again with the password blank keeps it
        c.put("/api/settings/kindle", json={"auto_send": True, "gmail_app_password": ""})
        k = c.get("/api/settings").json()["values"]["kindle"]
        assert k["gmail_app_password"] == "" and k["gmail_app_password_set"] and k["auto_send"]
        assert c.put("/api/settings/kindle", json={"kindle_email": "x"}).status_code == 422
        assert c.post("/api/kindle/send", json={}).status_code == 404  # no edition yet


def test_send_to_kindle_mail(monkeypatch, tmp_path):
    from dayfold.delivery import kindle_mail
    from dayfold.settings import KindleSettings

    sent = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            sent["server"] = (host, port)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def starttls(self, context):
            sent["tls"] = True

        def login(self, user, password):
            sent["login"] = (user, password)

        def send_message(self, msg):
            sent["msg"] = msg

    monkeypatch.setattr(kindle_mail.smtplib, "SMTP", FakeSMTP)
    epub = tmp_path / "dayfold.kindle.epub"
    epub.write_bytes(b"PK fake")
    cfg = KindleSettings(kindle_email="eu_1@kindle.com", gmail_address="eu@gmail.com",
                         gmail_app_password="abcd efgh ijkl mnop")
    kindle_mail.send_epub(cfg, epub, "Dayfold · 14 nov. 2026")
    assert sent["server"] == ("smtp.gmail.com", 587) and sent["tls"]
    assert sent["login"] == ("eu@gmail.com", "abcdefghijklmnop")
    msg = sent["msg"]
    assert msg["To"] == "eu_1@kindle.com"
    att = next(msg.iter_attachments())
    assert att.get_filename() == "dayfold.kindle.epub" and att.get_content_type() == "application/epub+zip"
    import pytest

    with pytest.raises(kindle_mail.KindleMailError):
        kindle_mail.send_epub(KindleSettings(), epub, "x")
