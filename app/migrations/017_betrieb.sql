-- Betrieb & Material: Haltbarkeit/Bestellung je Teil, Maße je Behälter, Trockner, Slicer-Aufträge.
ALTER TABLE item ADD COLUMN opened TEXT;       -- geöffnet am (Harz, Kleber), ISO-Datum
ALTER TABLE item ADD COLUMN expires TEXT;      -- haltbar bis, ISO-Datum
ALTER TABLE item ADD COLUMN ordered_at TEXT;   -- bestellt am (Einkaufsliste)
ALTER TABLE item ADD COLUMN order_qty INTEGER; -- Wunschmenge beim Nachkaufen
ALTER TABLE container ADD COLUMN dims TEXT NOT NULL DEFAULT '';  -- Maße, z. B. '400x300x170'

CREATE TABLE dryer_program (
    id        INTEGER PRIMARY KEY,
    name      TEXT NOT NULL UNIQUE,
    material  TEXT NOT NULL DEFAULT '',
    temp_c    REAL NOT NULL,
    hours     REAL NOT NULL,
    note      TEXT NOT NULL DEFAULT ''
);
INSERT INTO dryer_program (name, material, temp_c, hours) VALUES
    ('PLA', 'PLA', 45, 6), ('PETG', 'PETG', 65, 6), ('ABS / ASA', 'ABS', 80, 4),
    ('TPU', 'TPU', 55, 6), ('PA / Nylon', 'PA', 80, 12), ('PC', 'PC', 80, 8),
    ('PVA', 'PVA', 45, 8), ('CF / GF Verbund', 'PA-CF', 80, 12);

CREATE TABLE dry_log (
    id          INTEGER PRIMARY KEY,
    item_id     INTEGER NOT NULL REFERENCES item(id) ON DELETE CASCADE,
    program     TEXT NOT NULL,
    temp_c      REAL NOT NULL,
    hours       REAL NOT NULL,
    started_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    done_at     TEXT,
    note        TEXT NOT NULL DEFAULT ''
);
CREATE INDEX dry_log_item ON dry_log(item_id);

CREATE TABLE print_job (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    source      TEXT NOT NULL DEFAULT '',   -- Dateiname
    grams       TEXT NOT NULL DEFAULT '[]', -- JSON: [{"g": 12.3, "type": "PLA", "color": "#fff", "item_id": 5}]
    seconds     INTEGER,
    created_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    booked_at   TEXT
);
