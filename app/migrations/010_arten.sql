-- foreign_keys: off
-- Eigene Behälter-Arten mit eigenem Code-Präfix (z. B. Schublade → SCH-001).
-- container neu aufbauen: CHECK auf feste Arten entfällt, gültige Arten prüft app/kinds.py.

CREATE TABLE container_kind (
    kind        TEXT PRIMARY KEY,
    label       TEXT NOT NULL,
    prefix      TEXT NOT NULL UNIQUE,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE container_new (
    id             INTEGER PRIMARY KEY,
    code           TEXT UNIQUE,
    parent_id      INTEGER REFERENCES container(id) ON DELETE RESTRICT,
    kind           TEXT NOT NULL,
    name           TEXT NOT NULL,
    position       TEXT,
    grid           TEXT,
    notes          TEXT NOT NULL DEFAULT '',
    photo          TEXT,
    created_at     TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at     TEXT NOT NULL DEFAULT (datetime('now')),
    label_printed  INTEGER NOT NULL DEFAULT 0,
    favorite       INTEGER NOT NULL DEFAULT 0,
    size           TEXT,
    model          TEXT,
    review         INTEGER NOT NULL DEFAULT 0,
    UNIQUE (parent_id, position)
);
INSERT INTO container_new (id, code, parent_id, kind, name, position, grid, notes, photo,
                           created_at, updated_at, label_printed, favorite, size, model, review)
    SELECT id, code, parent_id, kind, name, position, grid, notes, photo,
           created_at, updated_at, label_printed, favorite, size, model, review FROM container;
DROP TABLE container;
ALTER TABLE container_new RENAME TO container;
CREATE INDEX container_parent ON container(parent_id);
