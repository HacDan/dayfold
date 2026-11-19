from datetime import date

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
        assert k["mode"] == "koreader" and k["native_games"] is True and k["gmail_app_password_set"] is False
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


def test_schedule_days_are_saved_sorted_and_validated(data_dir):
    from dayfold.app import app

    with TestClient(app) as c:
        r = c.put("/api/settings/schedule", json={"days": [4, 0, 0]})
        assert r.status_code == 200, r.text
        assert r.json()["days"] == [0, 4]
        assert c.put("/api/settings/schedule", json={"days": []}).status_code == 422
        assert c.put("/api/settings/schedule", json={"days": [7]}).status_code == 422


def test_send_a_chosen_edition_to_the_kindle(data_dir, monkeypatch):
    """An archived edition can go to the Kindle, not only the latest one."""
    from dayfold.api import kindle as api
    from dayfold.app import app
    from dayfold.db import session_scope
    from dayfold.models import Edition, EditionStatus
    from dayfold.settings import set_section

    sent: list[str] = []
    monkeypatch.setattr(api, "send_and_record", lambda s, path, subject: sent.append(path.name) or "ok")

    ids: dict[int, int] = {}
    with session_scope() as s:
        set_section(s, "kindle", {"kindle_email": "eu_1@kindle.com", "gmail_address": "eu@gmail.com",
                                  "gmail_app_password": "abcd efgh ijkl mnop"})
    for number, day in ((1, "2026-11-16"), (2, "2026-11-17")):
        folder = data_dir / "editions" / f"{day}-000{number}"
        folder.mkdir(parents=True)
        reader = folder / f"paper-{number}.epub"
        reader.write_bytes(b"PK")
        (folder / f"paper-{number}.kindle-games.epub").write_bytes(b"PK native")
        with session_scope() as s:
            e = Edition(number=number, edition_date=date.fromisoformat(day), title="Dayfold",
                        status=EditionStatus.READY, epub_path=str(reader))
            s.add(e)
            s.flush()
            ids[number] = e.id

    with TestClient(app) as c:
        r = c.post("/api/kindle/send", json={"edition_id": ids[1]})
    assert r.status_code == 200, r.text
    assert sent == ["paper-1.kindle-games.epub"]  # the chosen edition, not the latest


def test_send_refuses_an_edition_that_predates_the_kindle_version(data_dir, monkeypatch):
    """Sending must not recompose an archived paper behind the user's back: it asks for Recompor."""
    from dayfold.api import kindle as api
    from dayfold.app import app
    from dayfold.db import session_scope
    from dayfold.models import Edition, EditionStatus
    from dayfold.settings import set_section

    folder = data_dir / "editions" / "2026-11-16-0001"
    folder.mkdir(parents=True)
    reader = folder / "paper.epub"
    reader.write_bytes(b"PK")
    rebuilt: list[int] = []
    sent: list[str] = []
    monkeypatch.setattr(api, "retypeset", rebuilt.append)
    monkeypatch.setattr(api, "send_and_record", lambda s, path, subject: sent.append(path.name) or "ok")

    with session_scope() as s:
        set_section(s, "kindle", {"kindle_email": "eu_1@kindle.com", "gmail_address": "eu@gmail.com",
                                  "gmail_app_password": "abcd efgh ijkl mnop"})
        e = Edition(number=1, edition_date=date(2026, 11, 16), title="Dayfold",
                    status=EditionStatus.READY, epub_path=str(reader))
        s.add(e)
        s.flush()
        eid = e.id

    with TestClient(app) as c:
        r = c.post("/api/kindle/send", json={"edition_id": eid})
    assert r.status_code == 400, r.text
    assert "Recompor" in r.json()["detail"]
    assert rebuilt == [] and sent == []


def test_an_unconfigured_mailer_does_not_retypeset_the_edition(data_dir, monkeypatch):
    """Sending an edition from before the Kindle variant existed must fail before rebuilding it."""
    from dayfold.api import kindle as api
    from dayfold.app import app
    from dayfold.db import session_scope
    from dayfold.models import Edition, EditionStatus

    folder = data_dir / "editions" / "2026-11-16-0001"
    folder.mkdir(parents=True)
    reader = folder / "paper.epub"
    reader.write_bytes(b"PK")
    rebuilt: list[int] = []
    monkeypatch.setattr(api, "retypeset", rebuilt.append)

    with session_scope() as s:
        e = Edition(number=1, edition_date=date(2026, 11, 16), title="Dayfold",
                    status=EditionStatus.READY, epub_path=str(reader))
        s.add(e)
        s.flush()
        eid = e.id

    with TestClient(app) as c:
        r = c.post("/api/kindle/send", json={"edition_id": eid})
    assert r.status_code == 400, r.text
    assert "configure" in r.json()["detail"]
    assert rebuilt == []


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


def test_overview_knows_when_the_latest_edition_is_not_todays(data_dir):
    from datetime import timedelta

    from dayfold import clock
    from dayfold.app import app
    from dayfold.db import session_scope
    from dayfold.models import Edition, EditionStatus

    today = clock.now().date()
    with TestClient(app) as c:
        assert c.get("/api/overview").json()["edition_is_today"] is False
        with session_scope() as s:
            s.add(Edition(number=1, edition_date=today - timedelta(days=1), title="Dayfold",
                          status=EditionStatus.READY))
        assert c.get("/api/overview").json()["edition_is_today"] is False
        with session_scope() as s:
            s.add(Edition(number=2, edition_date=today, title="Dayfold", status=EditionStatus.READY))
        body = c.get("/api/overview").json()
        assert body["edition_is_today"] is True
        assert body["latest_edition"]["date"] == today.isoformat()
