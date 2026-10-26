-- Alltag: Rückgängig, Verleihen, Mindestbestand/Einkaufsliste, Favoriten.

-- event neu aufbauen (CHECK-Liste erweitern, Vorher-Ort für Rückgängig, undone-Markierung)
CREATE TABLE event_new (
    id                 INTEGER PRIMARY KEY,
    ts                 TEXT NOT NULL DEFAULT (datetime('now')),
    item_id            INTEGER REFERENCES item(id) ON DELETE SET NULL,
    item_name          TEXT NOT NULL DEFAULT '',
    container_id       INTEGER REFERENCES container(id) ON DELETE SET NULL,
    prev_container_id  INTEGER,                    -- Ort vor move (für Rückgängig)
    action             TEXT NOT NULL CHECK (action IN (
                           'add', 'take', 'put', 'move', 'edit', 'delete', 'import',
                           'lend', 'return', 'undo')),
    delta              INTEGER,
    note               TEXT NOT NULL DEFAULT '',
    undone             INTEGER NOT NULL DEFAULT 0
);
INSERT INTO event_new (id, ts, item_id, item_name, container_id, action, delta, note)
    SELECT id, ts, item_id, item_name, container_id, action, delta, note FROM event;
DROP TABLE event;
ALTER TABLE event_new RENAME TO event;
CREATE INDEX event_item ON event(item_id);

ALTER TABLE item ADD COLUMN lent_to TEXT;          -- verliehen an / in Benutzung bei
ALTER TABLE item ADD COLUMN lent_since TEXT;
ALTER TABLE item ADD COLUMN min_qty INTEGER;       -- Mindestbestand -> Einkaufsliste
ALTER TABLE item ADD COLUMN on_list INTEGER NOT NULL DEFAULT 0;  -- manuell auf Einkaufsliste
ALTER TABLE container ADD COLUMN favorite INTEGER NOT NULL DEFAULT 0;
