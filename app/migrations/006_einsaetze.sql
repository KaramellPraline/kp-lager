-- foreign_keys: off
-- Sortierkasten-Modelle (NORB16) mit Einsätzen (Bins) und Etiketten-Warteschlange.
-- container neu aufbauen: Art 'einsatz' in der CHECK-Liste, size (Bin-Größe BxT), model (Kastenmodell).

CREATE TABLE container_new (
    id             INTEGER PRIMARY KEY,
    code           TEXT UNIQUE,
    parent_id      INTEGER REFERENCES container(id) ON DELETE RESTRICT,
    kind           TEXT NOT NULL CHECK (kind IN (
                       'raum', 'regal', 'ebene', 'stapel', 'eurobox', 'kiste',
                       'sortierkasten', 'einsatz', 'fach', 'sonstiges')),
    name           TEXT NOT NULL,
    position       TEXT,
    grid           TEXT,
    notes          TEXT NOT NULL DEFAULT '',
    photo          TEXT,
    created_at     TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at     TEXT NOT NULL DEFAULT (datetime('now')),
    label_printed  INTEGER NOT NULL DEFAULT 0,
    favorite       INTEGER NOT NULL DEFAULT 0,
    size           TEXT,     -- Einsatz: Breite x Tiefe in Rasterzellen, z. B. '2x1'
    model          TEXT,     -- Sortierkasten-Modell, z. B. 'norb16' (Raster aus app/kasten.py)
    UNIQUE (parent_id, position)
);
INSERT INTO container_new (id, code, parent_id, kind, name, position, grid, notes, photo,
                           created_at, updated_at, label_printed, favorite)
    SELECT id, code, parent_id, kind, name, position, grid, notes, photo,
           created_at, updated_at, label_printed, favorite FROM container;
DROP TABLE container;
ALTER TABLE container_new RENAME TO container;
CREATE INDEX container_parent ON container(parent_id);

CREATE TABLE label_queue (
    code      TEXT PRIMARY KEY,
    text      TEXT NOT NULL DEFAULT '',
    extra     TEXT NOT NULL DEFAULT '',
    added_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
