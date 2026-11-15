"""Anmeldung für den Betrieb als gehosteter Dienst (Modell: docs/SICHERHEIT.md).

* Benutzer (`app_user`): Passwort als scrypt-Hash mit Salt, Rolle `admin` | `nutzer`.
* Sitzungen (`session`): zufälliges Token im Cookie, in der Datenbank nur dessen SHA-256;
  gleitende Laufzeit (Einstellung `session_days`, Standard 30 Tage).
* Sperre: 5 Fehlversuche je Benutzer und Adresse (bzw. 20 je Adresse) → 10 Minuten gesperrt.
  Unbekannte Namen werden genauso behandelt wie falsche Passwörter (kein Benutzer-Aufzählen).
* Schreibschutz gegen fremde Seiten (CSRF): `Origin` muss zum eigenen Host passen
  (`same_origin`), dazu Cookie `SameSite=Lax`.
* Etikettenbilder für die D30-PC-Bridge: kurzlebige, signierte Links (`sign_label`).

Nur Standardbibliothek: hashlib.scrypt, secrets, hmac.
"""

import hashlib
import hmac
import re
import secrets
import sqlite3
import time
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from functools import cache
from pathlib import Path
from urllib.parse import urlsplit

from app import codes
from app.repo import LagerError, Row

COOKIE = "lager_session"
ROLES = {"admin": "Admin", "nutzer": "Nutzer"}
MAX_FAILS = 5  # je Benutzer und Adresse
MAX_FAILS_IP = 20  # je Adresse über alle Namen (gegen Durchprobieren vieler Namen)
LOCK_MINUTES = 10
MIN_PASSWORD = 8
NAME = re.compile(r"^[\w.@+-]{1,40}$")
_N, _R, _P = 2**14, 8, 1  # scrypt: ~16 MB, ~50 ms
REFRESH_SECONDS = 3600  # gleitende Laufzeit: höchstens stündlich in die Datenbank schreiben
LABEL_TOKEN_MINUTES = 15


# --- Passwörter ----------------------------------------------------------------------------


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    return f"scrypt${_N}${_R}${_P}${salt.hex()}${digest.hex()}"


def check_password(password: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt, digest = stored.split("$")
        if algo != "scrypt":
            return False
        calc = hashlib.scrypt(
            password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p),
            dklen=len(digest) // 2,
        )  # fmt: skip
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(calc.hex(), digest)


@cache
def _dummy_hash() -> str:
    """Für unbekannte Namen: gleich viel Rechenzeit wie bei einem echten Vergleich."""
    return hash_password(secrets.token_hex(16))


def check_new_password(password: str) -> None:
    if len(password) < MIN_PASSWORD:
        raise LagerError(f"Passwort zu kurz (mindestens {MIN_PASSWORD} Zeichen)")
    if len(password) > 200:
        raise LagerError("Passwort zu lang (höchstens 200 Zeichen)")


# --- Benutzer ------------------------------------------------------------------------------


def has_users(conn: sqlite3.Connection) -> bool:
    return conn.execute("SELECT 1 FROM app_user LIMIT 1").fetchone() is not None


def users(conn: sqlite3.Connection) -> list[Row]:
    return conn.execute(
        "SELECT id, name, role, created_at, last_login FROM app_user ORDER BY name"
    ).fetchall()


def get_user(conn: sqlite3.Connection, user_id: int) -> Row | None:
    row: Row | None = conn.execute(
        "SELECT id, name, role, created_at, last_login FROM app_user WHERE id = ?", (user_id,)
    ).fetchone()
    return row


def create_user(conn: sqlite3.Connection, name: str, password: str, role: str = "nutzer") -> int:
    name = name.strip()
    if not NAME.match(name):
        raise LagerError("Benutzername: 1–40 Zeichen, Buchstaben, Ziffern und . _ - @ +")
    if role not in ROLES:
        raise LagerError("Rolle: admin oder nutzer")
    check_new_password(password)
    if conn.execute("SELECT 1 FROM app_user WHERE name = ?", (name,)).fetchone():
        raise LagerError(f"Benutzer „{name}“ gibt es schon")
    with conn:
        cur = conn.execute(
            "INSERT INTO app_user (name, pw_hash, role) VALUES (?, ?, ?)",
            (name, hash_password(password), role),
        )
    return int(cur.lastrowid or 0)


def _admins(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT COUNT(*) FROM app_user WHERE role = 'admin'").fetchone()[0])


def _need_user(conn: sqlite3.Connection, user_id: int) -> Row:
    user = get_user(conn, user_id)
    if user is None:
        raise LagerError("Benutzer nicht gefunden")
    return user


def set_password(
    conn: sqlite3.Connection, user_id: int, password: str, keep_token: str = ""
) -> None:
    """Neues Passwort; alle anderen Sitzungen dieses Benutzers enden."""
    _need_user(conn, user_id)
    check_new_password(password)
    with conn:
        conn.execute(
            "UPDATE app_user SET pw_hash = ? WHERE id = ?", (hash_password(password), user_id)
        )
        conn.execute(
            "DELETE FROM session WHERE user_id = ? AND token_hash != ?",
            (user_id, _token_hash(keep_token) if keep_token else ""),
        )


def change_own_password(
    conn: sqlite3.Connection, user_id: int, old: str, new: str, keep_token: str
) -> None:
    row = conn.execute("SELECT pw_hash FROM app_user WHERE id = ?", (user_id,)).fetchone()
    if row is None or not check_password(old, row["pw_hash"]):
        raise LagerError("Bisheriges Passwort stimmt nicht")
    set_password(conn, user_id, new, keep_token)


def set_role(conn: sqlite3.Connection, user_id: int, role: str) -> None:
    user = _need_user(conn, user_id)
    if role not in ROLES:
        raise LagerError("Rolle: admin oder nutzer")
    if user["role"] == "admin" and role != "admin" and _admins(conn) <= 1:
        raise LagerError("Der letzte Admin bleibt Admin")
    with conn:
        conn.execute("UPDATE app_user SET role = ? WHERE id = ?", (role, user_id))


def delete_user(conn: sqlite3.Connection, user_id: int) -> str:
    user = _need_user(conn, user_id)
    if user["role"] == "admin" and _admins(conn) <= 1:
        raise LagerError("Der letzte Admin kann nicht gelöscht werden")
    with conn:
        conn.execute("DELETE FROM session WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM app_user WHERE id = ?", (user_id,))
    return str(user["name"])


def bootstrap(conn: sqlite3.Connection, name: str, password_file: str) -> str:
    """Erster Admin aus der Umgebung (LAGER_ADMIN_USER + Passwortdatei), nur ohne Benutzer.

    Gibt eine Meldung fürs Log zurück (ohne Passwort)."""
    if not name or has_users(conn):
        return ""
    if not password_file:
        return "LAGER_ADMIN_USER ohne LAGER_ADMIN_PASSWORD_FILE – Einrichtung über /einrichten"
    try:
        password = Path(password_file).read_text(encoding="utf-8-sig").strip()
        create_user(conn, name, password, "admin")
    except (OSError, LagerError) as exc:
        return f"Admin aus der Umgebung nicht angelegt: {exc}"
    return f"Admin „{name}“ aus der Umgebung angelegt"


# --- Fehlversuche und Sperre ---------------------------------------------------------------


def _since(minutes: int) -> str:
    return (datetime.now(UTC) - timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M:%S")


def _keys(name: str, ip: str) -> tuple[str, str]:
    return f"p:{name.strip().casefold()}|{ip}", f"ip:{ip}"


def locked(conn: sqlite3.Connection, name: str, ip: str) -> bool:
    pair, addr = _keys(name, ip)
    since = _since(LOCK_MINUTES)

    def fails(key: str) -> int:
        return int(
            conn.execute(
                "SELECT COUNT(*) FROM login_fail WHERE key = ? AND at > ?", (key, since)
            ).fetchone()[0]
        )

    return fails(pair) >= MAX_FAILS or fails(addr) >= MAX_FAILS_IP


def _record_fail(conn: sqlite3.Connection, name: str, ip: str) -> None:
    with conn:
        conn.executemany("INSERT INTO login_fail (key) VALUES (?)", [(k,) for k in _keys(name, ip)])
        conn.execute("DELETE FROM login_fail WHERE at < ?", (_since(24 * 60),))


def authenticate(conn: sqlite3.Connection, name: str, password: str, ip: str) -> Row:
    """Benutzer bei richtigem Passwort; sonst LagerError mit immer gleicher Meldung."""
    if locked(conn, name, ip):
        _dummy_check(password)
        raise LagerError(f"Zu viele Fehlversuche – bitte {LOCK_MINUTES} Minuten warten")
    row = conn.execute(
        "SELECT id, name, role, pw_hash FROM app_user WHERE name = ?", (name.strip(),)
    ).fetchone()
    ok = check_password(password, row["pw_hash"] if row else _dummy_hash())
    if not (row and ok):
        _record_fail(conn, name, ip)
        raise LagerError("Benutzername oder Passwort falsch")
    pair, _ = _keys(name, ip)
    with conn:
        conn.execute("DELETE FROM login_fail WHERE key = ?", (pair,))
        conn.execute("UPDATE app_user SET last_login = datetime('now') WHERE id = ?", (row["id"],))
    user: Row = row
    return user


def _dummy_check(password: str) -> None:
    check_password(password, _dummy_hash())


# --- Sitzungen -----------------------------------------------------------------------------


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _expiry(days: int) -> str:
    return (datetime.now(UTC) + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")


def new_session(
    conn: sqlite3.Connection, user_id: int, days: int, ip: str = "", agent: str = ""
) -> str:
    token = secrets.token_urlsafe(32)
    with conn:
        conn.execute(
            "INSERT INTO session (token_hash, user_id, expires_at, ip, agent)"
            " VALUES (?, ?, ?, ?, ?)",
            (_token_hash(token), user_id, _expiry(days), ip[:64], agent[:200]),
        )
        conn.execute("DELETE FROM session WHERE expires_at < datetime('now')")
    return token


def session_user(conn: sqlite3.Connection, token: str, days: int) -> tuple[Row | None, bool]:
    """(Benutzer, Cookie erneuern?) zu einem Sitzungs-Token; abgelaufen/unbekannt -> None."""
    if not token or len(token) > 100:
        return None, False
    th = _token_hash(token)
    row = conn.execute(
        "SELECT u.id, u.name, u.role, s.seen_at FROM session s JOIN app_user u ON u.id = s.user_id"
        " WHERE s.token_hash = ? AND s.expires_at > datetime('now')",
        (th,),
    ).fetchone()
    if row is None:
        return None, False
    seen = datetime.strptime(row["seen_at"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
    refresh = (datetime.now(UTC) - seen).total_seconds() > REFRESH_SECONDS
    if refresh:  # gleitend: jede Nutzung verlängert (höchstens stündlich geschrieben)
        with conn:
            conn.execute(
                "UPDATE session SET seen_at = datetime('now'), expires_at = ? WHERE token_hash = ?",
                (_expiry(days), th),
            )
    user: Row = row
    return user, refresh


def end_session(conn: sqlite3.Connection, token: str) -> None:
    if token:
        with conn:
            conn.execute("DELETE FROM session WHERE token_hash = ?", (_token_hash(token),))


def sessions_of(conn: sqlite3.Connection, user_id: int) -> int:
    return int(
        conn.execute(
            "SELECT COUNT(*) FROM session WHERE user_id = ? AND expires_at > datetime('now')",
            (user_id,),
        ).fetchone()[0]
    )


# --- Signierte Kurzlinks (Etikettenbild für die D30-PC-Bridge) -----------------------------


def _secret(conn: sqlite3.Connection) -> bytes:
    """Serverschlüssel für Signaturen; liegt in `meta` (nicht im Export, kein `setting:`)."""
    value = codes.get_secret(conn, "sign")
    if not value:
        with conn:
            conn.execute(
                "INSERT OR IGNORE INTO meta (key, value) VALUES ('secret:sign', ?)",
                (secrets.token_hex(32),),
            )
        value = codes.get_secret(conn, "sign")
    return bytes.fromhex(value)


def sign_label(conn: sqlite3.Connection, code: str, now: float | None = None) -> str:
    exp = int((now or time.time()) + LABEL_TOKEN_MINUTES * 60)
    mac = hmac.new(_secret(conn), f"labelimg|{code.upper()}|{exp}".encode(), "sha256")
    return f"{exp}.{mac.hexdigest()[:32]}"


def check_label(conn: sqlite3.Connection, code: str, token: str) -> bool:
    exp, _, sig = token.partition(".")
    if not exp.isdigit() or int(exp) < time.time() or len(sig) != 32:
        return False
    mac = hmac.new(_secret(conn), f"labelimg|{code.upper()}|{exp}".encode(), "sha256")
    return hmac.compare_digest(mac.hexdigest()[:32], sig)


# --- Herkunft von Anfragen und Rücksprung ----------------------------------------------------


def _netloc(value: str) -> str:
    loc = value.strip().lower()
    for port in (":80", ":443"):
        loc = loc.removesuffix(port)
    return loc


def same_origin(headers: Mapping[str, str]) -> bool:
    """Schreibende Anfrage von der eigenen Seite? (Schutz gegen CSRF)

    Aktuelle Browser schicken bei jedem POST/fetch/HTMX-Aufruf die Kopfzeile `Origin`; passt ihr
    Host nicht zum eigenen (`Host` bzw. `X-Forwarded-Host` hinter Caddy), kam die Anfrage von einer
    fremden Seite. Ohne `Origin` (Werkzeuge, Tests, sehr alte Browser) wird zugelassen – dort
    schützt das Sitzungs-Cookie mit `SameSite=Lax`, das bei fremden POSTs nicht mitgeschickt wird.
    """
    get = headers.get
    source = get("origin")
    if source is None:
        return True
    if source == "null":  # Sandbox-iframe, data:-URL, Weiterleitung über fremde Seite
        return False
    loc = urlsplit(source).netloc
    hosts = {_netloc(h) for h in (get("host") or "", get("x-forwarded-host") or "") if h}
    return bool(loc) and _netloc(loc) in hosts


def safe_next(url: str, default: str = "/") -> str:
    """Nur relative Pfade der eigenen Seite (kein //host, kein Schema, kein Backslash)."""
    url = (url or "").strip()
    if not url.startswith("/") or url.startswith("//") or "\\" in url or "\n" in url:
        return default
    if urlsplit(url).netloc or url.startswith(("/login", "/einrichten", "/logout")):
        return default
    return url
