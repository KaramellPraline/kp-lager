-- Speicherstruktur: ein Baum aus Behältern (Raum › Regal › Ebene › Box › Fach), Items liegen in genau einem Behälter.

CREATE TABLE container (
    id          INTEGER PRIMARY KEY,
    code        TEXT UNIQUE,                 -- QR-Code-ID, nur bei etikettierten Behältern
    parent_id   INTEGER REFERENCES container(id) ON DELETE RESTRICT,
    kind        TEXT NOT NULL CHECK (kind IN (
                    'raum', 'regal', 'ebene', 'stapel', 'eurobox', 'kiste',
                    'sortierkasten', 'fach', 'sonstiges')),
    name        TEXT NOT NULL,
    position    TEXT,                        -- Platz im Elternbehälter, z. B. 'B3' oder 'Ebene 2'
    grid        TEXT,                        -- 'SpaltenxZeilen' bei Sortierkästen, erzeugt Fächer
    notes       TEXT NOT NULL DEFAULT '',
    photo       TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (parent_id, position)
);
CREATE INDEX container_parent ON container(parent_id);

CREATE TABLE item (
    id            INTEGER PRIMARY KEY,
    container_id  INTEGER NOT NULL REFERENCES container(id) ON DELETE RESTRICT,
    name          TEXT NOT NULL,
    qty           INTEGER CHECK (qty IS NULL OR qty >= 0),  -- NULL = ungezählt
    qty_hint      TEXT NOT NULL DEFAULT '',                 -- 'ca. 20', 'viele'
    unit          TEXT NOT NULL DEFAULT '',
    tags          TEXT NOT NULL DEFAULT '',
    notes         TEXT NOT NULL DEFAULT '',
    photo         TEXT,
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX item_container ON item(container_id);

-- Protokoll: bleibt erhalten, auch wenn Item/Behälter gelöscht werden.
CREATE TABLE event (
    id            INTEGER PRIMARY KEY,
    ts            TEXT NOT NULL DEFAULT (datetime('now')),
    item_id       INTEGER REFERENCES item(id) ON DELETE SET NULL,
    item_name     TEXT NOT NULL DEFAULT '',
    container_id  INTEGER REFERENCES container(id) ON DELETE SET NULL,
    action        TEXT NOT NULL CHECK (action IN ('add', 'take', 'put', 'move', 'edit', 'delete', 'import')),
    delta         INTEGER,
    note          TEXT NOT NULL DEFAULT ''
);
CREATE INDEX event_item ON event(item_id);
