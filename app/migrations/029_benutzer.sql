-- Anmeldung (Betrieb als gehosteter Dienst): Benutzer, Sitzungen, Fehlversuche.
-- Passwörter nur als scrypt-Hash mit Salt, Sitzungs-Token nur als SHA-256.
CREATE TABLE app_user (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE COLLATE NOCASE,
    pw_hash     TEXT NOT NULL,
    role        TEXT NOT NULL DEFAULT 'nutzer' CHECK (role IN ('admin', 'nutzer')),
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    last_login  TEXT
);

CREATE TABLE session (
    token_hash  TEXT PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    seen_at     TEXT NOT NULL DEFAULT (datetime('now')),
    expires_at  TEXT NOT NULL,
    ip          TEXT NOT NULL DEFAULT '',
    agent       TEXT NOT NULL DEFAULT ''
);
CREATE INDEX session_user ON session(user_id);

-- Fehlversuche: Schlüssel 'p:<name>|<ip>' (Benutzer an dieser Adresse) und 'ip:<ip>'
CREATE TABLE login_fail (
    key  TEXT NOT NULL,
    at   TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX login_fail_key ON login_fail(key, at);
