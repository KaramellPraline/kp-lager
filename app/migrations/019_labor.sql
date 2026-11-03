-- Homelab-Ausbau: API-Rechte, Inventur, Lieferanten/Einkäufe, Notiz- und Pinout-Karten.
ALTER TABLE api_key ADD COLUMN scope TEXT NOT NULL DEFAULT 'write';  -- read | write
ALTER TABLE item ADD COLUMN checked_at TEXT;       -- zuletzt per Inventur bestätigt
ALTER TABLE container ADD COLUMN checked_at TEXT;  -- Inventur dieses Behälters abgeschlossen

CREATE TABLE supplier (
    id    INTEGER PRIMARY KEY,
    name  TEXT NOT NULL UNIQUE COLLATE NOCASE,
    url   TEXT NOT NULL DEFAULT '',
    note  TEXT NOT NULL DEFAULT ''
);

CREATE TABLE purchase (
    id          INTEGER PRIMARY KEY,
    item_id     INTEGER NOT NULL REFERENCES item(id) ON DELETE CASCADE,
    supplier_id INTEGER REFERENCES supplier(id) ON DELETE SET NULL,
    qty         INTEGER,
    price       REAL,                 -- Stückpreis in Euro
    bought_at   TEXT NOT NULL DEFAULT (date('now', 'localtime')),
    url         TEXT NOT NULL DEFAULT '',
    note        TEXT NOT NULL DEFAULT ''
);
CREATE INDEX purchase_item ON purchase(item_id);
CREATE INDEX purchase_supplier ON purchase(supplier_id);

CREATE TABLE card (
    id           INTEGER PRIMARY KEY,
    item_id      INTEGER REFERENCES item(id) ON DELETE CASCADE,
    container_id INTEGER REFERENCES container(id) ON DELETE CASCADE,
    kind         TEXT NOT NULL DEFAULT 'note' CHECK (kind IN ('note', 'pinout')),
    title        TEXT NOT NULL,
    body         TEXT NOT NULL DEFAULT '',
    created_at   TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    CHECK ((item_id IS NULL) <> (container_id IS NULL))
);
CREATE INDEX card_item ON card(item_id);
CREATE INDEX card_container ON card(container_id);
