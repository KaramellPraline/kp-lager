"""Anmeldung (Arbeitspaket 3): Einrichten, Login, Sperre, Abmelden, Rollen, Herkunftsprüfung,
freie Pfade, Rücksprung nach dem Login, API unberührt, Kurzlinks für die D30-Bridge."""

import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import auth
from app.config import Settings, load_settings
from app.db import connect
from app.web import create_app

PW = "geheim-123"


def make(tmp_path: Path, **kw: object) -> TestClient:
    settings = Settings(data_dir=tmp_path, base_url="https://lager.test", auth=True, **kw)  # type: ignore[arg-type]
    return TestClient(create_app(settings), follow_redirects=True)


@pytest.fixture
def anon(tmp_path: Path) -> Iterator[TestClient]:
    with make(tmp_path) as c:
        yield c


@pytest.fixture
def admin(tmp_path: Path) -> Iterator[TestClient]:
    """Eingerichtet, als Admin „chef“ angemeldet."""
    with make(tmp_path) as c:
        c.post("/einrichten", data={"name": "chef", "password": PW, "password2": PW})
        yield c


def login(c: TestClient, name: str, pw: str, next_: str = "/") -> str:
    return c.post("/login", data={"name": name, "password": pw, "next": next_}).text


def test_settings_defaults(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    assert Settings(data_dir=tmp_path, base_url="x").auth is False  # Tests/Bibliothek: aus
    monkeypatch.delenv("LAGER_AUTH", raising=False)
    assert load_settings().auth is True  # Betrieb: Standard an
    monkeypatch.setenv("LAGER_AUTH", "0")
    assert load_settings().auth is False


def test_password_hash_roundtrip() -> None:
    h = auth.hash_password("abc12345")
    assert h.startswith("scrypt$") and "abc12345" not in h
    assert auth.check_password("abc12345", h) and not auth.check_password("abc12346", h)
    assert h != auth.hash_password("abc12345")  # eigenes Salt
    assert not auth.check_password("x", "kaputt")


def test_first_start_redirects_to_setup(anon: TestClient) -> None:
    for path in ("/", "/n/1", "/settings", "/login"):
        r = anon.get(path)
        assert r.url.path == "/einrichten", path
    assert "Admin anlegen" in anon.get("/einrichten").text
    r = anon.post("/einrichten", data={"name": "chef", "password": "kurz", "password2": "kurz"})
    assert "zu kurz" in r.text
    r = anon.post("/einrichten", data={"name": "chef", "password": PW, "password2": PW + "x"})
    assert "verschieden" in r.text
    r = anon.post("/einrichten", data={"name": "chef", "password": PW, "password2": PW})
    assert r.url.path == "/" and "chef" in r.text  # gleich angemeldet
    cookie = r.history[0].headers["set-cookie"]
    assert auth.COOKIE in cookie and "HttpOnly" in cookie and "samesite=lax" in cookie.lower()
    assert "Secure" not in cookie  # http
    # Einrichten geht nur einmal
    r = anon.post("/einrichten", data={"name": "boss", "password": PW, "password2": PW})
    assert r.url.path != "/einrichten"
    conn = connect(anon.app.state.settings.db_path)  # type: ignore[attr-defined]
    assert [u["name"] for u in auth.users(conn)] == ["chef"]


def test_login_wrong_and_right(admin: TestClient) -> None:
    admin.post("/logout")
    r = admin.get("/")
    assert r.url.path == "/login"
    wrong = login(admin, "chef", "falsch-falsch")
    unknown = login(admin, "niemand", "falsch-falsch")
    assert "Benutzername oder Passwort falsch" in wrong
    assert "Benutzername oder Passwort falsch" in unknown  # keine Auskunft über Namen
    page = login(admin, "chef", PW)
    assert "Anmelden" not in page.split("<main>")[1][:200]
    assert admin.get("/settings").url.path == "/settings"


def test_session_stored_hashed_and_cookie_secure_behind_proxy(admin: TestClient) -> None:
    token = admin.cookies.get(auth.COOKIE)
    assert token
    conn = connect(admin.app.state.settings.db_path)  # type: ignore[attr-defined]
    stored = [r["token_hash"] for r in conn.execute("SELECT token_hash FROM session")]
    assert token not in stored and len(stored) == 1
    admin.post("/logout")
    r = admin.post(
        "/login", data={"name": "chef", "password": PW},
        headers={"x-forwarded-proto": "https"}, follow_redirects=False,
    )  # fmt: skip
    assert "Secure" in r.headers["set-cookie"]


def test_lockout_after_five_failures(admin: TestClient) -> None:
    admin.post("/logout")
    for _ in range(5):
        assert "falsch" in login(admin, "chef", "nein-nein-nein")
    page = login(admin, "chef", PW)  # auch das richtige Passwort hilft jetzt nicht
    assert "Zu viele Fehlversuche" in page
    assert admin.get("/").url.path == "/login"
    # andere Namen von derselben Adresse: eigene Zählung (bis 20 je Adresse)
    assert "falsch" in login(admin, "jemand", "nein-nein-nein")
    conn = connect(admin.app.state.settings.db_path)  # type: ignore[attr-defined]
    with conn:
        conn.execute("UPDATE login_fail SET at = datetime('now', '-11 minutes')")
    assert "Abmelden" in login(admin, "chef", PW)  # nach 10 Minuten wieder frei


def test_logout_ends_session(admin: TestClient) -> None:
    token = admin.cookies.get(auth.COOKIE)
    r = admin.post("/logout")
    assert r.url.path == "/login"
    admin.cookies.set(auth.COOKIE, token or "")  # altes Cookie nützt nichts mehr
    assert admin.get("/").url.path == "/login"


def test_next_redirect_only_relative(admin: TestClient) -> None:
    box = admin.post("/containers", data={"name": "Box", "kind": "eurobox", "code": "EUR-001"})
    admin.post("/logout")
    r = admin.get("/c/EUR-001")
    assert r.url.path == "/login" and "next=/c/EUR-001" in str(r.url)
    assert 'name="next" value="/c/EUR-001"' in r.text
    r = admin.post("/login", data={"name": "chef", "password": PW, "next": "/c/EUR-001"})
    assert r.url.path == box.url.path  # Scan-Ziel nach dem Login
    for evil in ("https://evil.example/", "//evil.example/x", "/\\evil.example", "javascript:x"):
        admin.post("/logout")
        r = admin.post("/login", data={"name": "chef", "password": PW, "next": evil})
        assert r.url.host == "testserver" and r.url.path == "/", evil
    assert auth.safe_next("/n/1?x=2") == "/n/1?x=2" and auth.safe_next("/login") == "/"


def test_open_paths_without_login(anon: TestClient) -> None:
    anon.post("/einrichten", data={"name": "chef", "password": PW, "password2": PW})
    anon.post("/logout")
    assert anon.get("/health").json()["status"] == "ok"
    for path in ("/sw.js", "/manifest.webmanifest", "/offline", "/static/style.css", "/login"):
        r = anon.get(path, follow_redirects=False)
        assert r.status_code == 200, path
    assert anon.get("/ca.crt", follow_redirects=False).status_code == 404  # frei, nur keine Datei
    for path in ("/", "/photos/x.jpg", "/export.json", "/labels/img/ART-0001.png", "/scan"):
        r = anon.get(path, follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"].startswith("/login"), path


def test_htmx_and_fetch_get_401(admin: TestClient) -> None:
    admin.post("/logout")
    r = admin.post("/api/take", headers={"hx-request": "true", "hx-current-url": "http://testserver/n/3"},
                   follow_redirects=False)  # fmt: skip
    assert r.status_code == 401 and r.headers["hx-redirect"] == "/login?next=/n/3"
    r = admin.post("/items/1/take", data={"qty": "1"}, headers={"sec-fetch-mode": "cors"},
                   follow_redirects=False)  # fmt: skip
    assert r.status_code == 401 and r.json()["login"].startswith("/login")  # Service Worker behält


def test_api_unaffected(admin: TestClient) -> None:
    admin.post("/logout")
    assert admin.get("/api/v1/overview").status_code == 200  # Lesen ohne Schlüssel (Einstellung)
    r = admin.post("/api/v1/items", json={"text": "x"}, follow_redirects=False)
    assert r.status_code == 401 and "login" not in r.text.lower()  # Schlüssel-Logik der API


def test_roles_user_cannot_reach_admin_areas(admin: TestClient) -> None:
    r = admin.post("/settings/benutzer", data={"name": "lea", "password": PW, "role": "nutzer"})
    assert "Benutzer „lea“ angelegt" in r.text
    admin.post("/logout")
    login(admin, "lea", PW)
    assert admin.get("/").status_code == 200
    box = admin.post("/containers", data={"name": "Kiste", "kind": "kiste"})
    assert box.status_code == 200 and "/n/" in box.url.path  # Bestand: erlaubt
    for path in (
        "/settings",
        "/settings/system",
        "/settings/anbindungen",
        "/import",
        "/export.zip",
    ):
        assert admin.get(path, follow_redirects=False).status_code == 403, path
    assert admin.post("/settings", data={"app_name": "X"}).status_code == 403
    assert admin.post("/settings/benutzer", data={"name": "x", "password": PW}).status_code == 403
    page = admin.get("/settings/benutzer").text  # eigenes Konto: erlaubt
    assert "Mein Konto" in page and "Neuer Benutzer" not in page
    assert 'href="/settings/system"' not in page
    r = admin.post(
        "/settings/konto/passwort", data={"old": PW, "new": "neues-pw-1", "new2": "neues-pw-1"}
    )
    assert "Passwort geändert" in r.text
    admin.post("/logout")
    assert "falsch" in login(admin, "lea", PW)
    assert "Abmelden" in login(admin, "lea", "neues-pw-1")


def test_user_management_and_last_admin(admin: TestClient) -> None:
    admin.post("/settings/benutzer", data={"name": "lea", "password": PW, "role": "nutzer"})
    conn = connect(admin.app.state.settings.db_path)  # type: ignore[attr-defined]
    ids = {u["name"]: u["id"] for u in auth.users(conn)}
    assert "gibt es schon" in admin.post(
        "/settings/benutzer", data={"name": "LEA", "password": PW}, headers={"referer": "/settings/benutzer"}
    ).text  # fmt: skip
    r = admin.post(
        f"/settings/benutzer/{ids['chef']}/loeschen", headers={"referer": "/settings/benutzer"}
    )
    assert "letzte Admin" in r.text
    r = admin.post(f"/settings/benutzer/{ids['chef']}/rolle", data={"role": "nutzer"},
                   headers={"referer": "/settings/benutzer"})  # fmt: skip
    assert "letzte Admin" in r.text
    admin.post(f"/settings/benutzer/{ids['lea']}/rolle", data={"role": "admin"})
    assert auth.get_user(conn, ids["lea"])["role"] == "admin"  # type: ignore[index]
    r = admin.post(f"/settings/benutzer/{ids['lea']}/passwort", data={"password": "anderes-pw"})
    assert "Passwort gesetzt" in r.text
    r = admin.post(f"/settings/benutzer/{ids['lea']}/loeschen")
    assert "gelöscht" in r.text and "lea" not in [u["name"] for u in auth.users(conn)]


def test_csrf_origin_check(admin: TestClient) -> None:
    r = admin.post("/containers", data={"name": "Fremd", "kind": "kiste"},
                   headers={"origin": "https://evil.example"}, follow_redirects=False)  # fmt: skip
    assert r.status_code == 403
    r = admin.post("/containers", data={"name": "Fremd", "kind": "kiste"},
                   headers={"origin": "http://testserver.evil.example"}, follow_redirects=False)  # fmt: skip
    assert r.status_code == 403
    assert (
        admin.post("/logout", headers={"origin": "null"}, follow_redirects=False).status_code == 403
    )
    r = admin.post("/containers", data={"name": "Eigen", "kind": "kiste"},
                   headers={"origin": "http://testserver"})  # fmt: skip
    assert r.status_code == 200 and "/n/" in r.url.path
    r = admin.post("/containers", data={"name": "Proxy", "kind": "kiste"},
                   headers={"origin": "https://lager.home.lan", "host": "lager.home.lan"})  # fmt: skip
    assert r.status_code == 200
    # API hat eigene Schlüssel und ist von der Herkunftsprüfung ausgenommen
    assert (
        admin.post("/api/v1/items", json={}, headers={"origin": "https://evil.example"}).status_code
        == 401
    )


def test_csrf_also_without_auth(client: TestClient) -> None:
    r = client.post("/containers", data={"name": "X", "kind": "kiste"},
                    headers={"origin": "https://evil.example"}, follow_redirects=False)  # fmt: skip
    assert r.status_code == 403
    assert client.get("/login", follow_redirects=False).headers["location"] == "/"  # ohne Login


def test_sliding_session_and_lifetime(admin: TestClient) -> None:
    conn = connect(admin.app.state.settings.db_path)  # type: ignore[attr-defined]
    with conn:
        conn.execute("UPDATE session SET seen_at = datetime('now', '-2 hours'),"
                     " expires_at = datetime('now', '+1 day')")  # fmt: skip
    r = admin.get("/", follow_redirects=False)
    assert r.status_code == 200 and "Max-Age=2592000" in r.headers["set-cookie"]  # 30 Tage
    left = conn.execute("SELECT julianday(expires_at) - julianday('now') FROM session").fetchone()[
        0
    ]
    assert 29.9 < left <= 30
    with conn:
        conn.execute("UPDATE session SET expires_at = datetime('now', '-1 minute')")
    assert admin.get("/").url.path == "/login"


def test_admin_from_environment(tmp_path: Path) -> None:
    secret = tmp_path / "pw.txt"
    secret.write_text(PW + "\n")
    with make(tmp_path / "d", admin_user="root", admin_password_file=str(secret)) as c:
        assert c.get("/").url.path == "/login"  # kein /einrichten mehr nötig
        assert "Abmelden" in login(c, "root", PW)


def test_label_image_for_bridge(admin: TestClient) -> None:
    box = admin.post("/containers", data={"name": "Box", "kind": "kiste", "code": "KIS-001"})
    assert box.status_code == 200
    conn = connect(admin.app.state.settings.db_path)  # type: ignore[attr-defined]
    token = auth.sign_label(conn, "KIS-001")
    admin.post("/logout")
    assert admin.get("/labels/img/KIS-001.png", follow_redirects=False).status_code == 303
    r = admin.get(f"/labels/img/KIS-001.png?t={token}", follow_redirects=False)
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert (
        admin.get(f"/labels/img/KIS-002.png?t={token}", follow_redirects=False).status_code == 303
    )
    old = auth.sign_label(conn, "KIS-001", now=1_000_000)
    assert admin.get(f"/labels/img/KIS-001.png?t={old}", follow_redirects=False).status_code == 303
    from app import apikeys

    key = apikeys.create(conn, "Drucker", "read")
    r = admin.get("/labels/img/KIS-001.png", headers={"X-API-Key": key}, follow_redirects=False)
    assert r.status_code == 200


def test_bridge_tokens_in_toast(tmp_path: Path) -> None:
    s = Settings(data_dir=tmp_path, base_url="https://lager.test", d30_bridge=True, auth=True)
    with TestClient(create_app(s), follow_redirects=True) as c:
        c.post("/einrichten", data={"name": "chef", "password": PW, "password2": PW})
        c.post("/containers", data={"name": "Box", "kind": "kiste", "code": "KIS-001"})
        page = c.post("/d30/print", data={"code": "KIS-001", "back": "/labels"}).text
        m = re.search(r'data-d30-tokens="([^"]+)"', page)
        assert m and "KIS-001" in m.group(1)
        token = re.search(r"KIS-001&#34;: &#34;([0-9a-f.]+)", m.group(1))
        assert token
        c.post("/logout")
        r = c.get(f"/labels/img/KIS-001.png?t={token.group(1)}", follow_redirects=False)
        assert r.status_code == 200


def test_service_worker_keeps_rejected_bookings(client: TestClient) -> None:
    js = client.get("/sw.js").text
    assert "needsLogin(resp)) return false" in js  # 401/403/Login: behalten, nicht verwerfen
    assert "isLoginPage(resp)" in js and "/einrichten" in js  # Login-Seite nie cachen


def test_login_page_not_cacheable(anon: TestClient) -> None:
    r = anon.get("/einrichten")
    assert r.headers["cache-control"] == "no-store" and r.headers["x-lager-login"] == "1"
