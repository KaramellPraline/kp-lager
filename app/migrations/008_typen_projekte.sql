-- Typen (TYP-001 …), Anzeige-/Vollname, Modellnummer + Datenblatt, KI-Prüf-Flag, Archiv,
-- Entnahmen (7-Tage-Bestätigung), Projekte (Sammellisten), API-Schlüssel.

CREATE TABLE item_type (
    id          INTEGER PRIMARY KEY,
    code        TEXT UNIQUE,
    name        TEXT NOT NULL UNIQUE COLLATE NOCASE,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
INSERT INTO item_type (code, name) VALUES
    ('TYP-001', 'mechanical'), ('TYP-002', 'electronic'), ('TYP-003', 'smart-home'), ('TYP-004', 'TBD');

ALTER TABLE item ADD COLUMN full_name TEXT NOT NULL DEFAULT '';      -- vollständiger Name; name = Anzeigename
ALTER TABLE item ADD COLUMN type_id INTEGER REFERENCES item_type(id) ON DELETE SET NULL;
ALTER TABLE item ADD COLUMN model TEXT NOT NULL DEFAULT '';          -- Modell-/Teilenummer
ALTER TABLE item ADD COLUMN datasheet_url TEXT NOT NULL DEFAULT '';
ALTER TABLE item ADD COLUMN datasheet TEXT;                          -- lokale PDF in data/datasheets/
ALTER TABLE item ADD COLUMN review INTEGER NOT NULL DEFAULT 0;       -- 1 = von KI angelegt, zu prüfen
ALTER TABLE item ADD COLUMN archived INTEGER NOT NULL DEFAULT 0;     -- verbraucht/entnommen, ausgeblendet
ALTER TABLE container ADD COLUMN review INTEGER NOT NULL DEFAULT 0;

-- Volltextindex um Vollname und Modell erweitern
DROP TRIGGER item_fts_ai;
DROP TRIGGER item_fts_ad;
DROP TRIGGER item_fts_au;
DROP TABLE item_fts;
CREATE VIRTUAL TABLE item_fts USING fts5(
    name, full_name, model, tags, notes, content='item', content_rowid='id', tokenize='trigram'
);
INSERT INTO item_fts(item_fts) VALUES ('rebuild');
CREATE TRIGGER item_fts_ai AFTER INSERT ON item BEGIN
    INSERT INTO item_fts(rowid, name, full_name, model, tags, notes)
    VALUES (new.id, new.name, new.full_name, new.model, new.tags, new.notes);
END;
CREATE TRIGGER item_fts_ad AFTER DELETE ON item BEGIN
    INSERT INTO item_fts(item_fts, rowid, name, full_name, model, tags, notes)
    VALUES ('delete', old.id, old.name, old.full_name, old.model, old.tags, old.notes);
END;
CREATE TRIGGER item_fts_au AFTER UPDATE OF name, full_name, model, tags, notes ON item BEGIN
    INSERT INTO item_fts(item_fts, rowid, name, full_name, model, tags, notes)
    VALUES ('delete', old.id, old.name, old.full_name, old.model, old.tags, old.notes);
    INSERT INTO item_fts(rowid, name, full_name, model, tags, notes)
    VALUES (new.id, new.name, new.full_name, new.model, new.tags, new.notes);
END;

CREATE TABLE withdrawal (
    id            INTEGER PRIMARY KEY,
    item_id       INTEGER REFERENCES item(id) ON DELETE SET NULL,
    item_name     TEXT NOT NULL DEFAULT '',
    container_id  INTEGER REFERENCES container(id) ON DELETE SET NULL,
    qty           INTEGER,                                   -- NULL = ungezähltes Teil komplett
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    confirm_at    TEXT NOT NULL DEFAULT (datetime('now', '+7 days')),
    state         TEXT NOT NULL DEFAULT 'offen' CHECK (state IN ('offen', 'bestaetigt', 'storniert'))
);
CREATE INDEX withdrawal_item ON withdrawal(item_id);

CREATE TABLE project (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    notes       TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    done        INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE project_item (
    id           INTEGER PRIMARY KEY,
    project_id   INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
    item_id      INTEGER REFERENCES item(id) ON DELETE SET NULL,
    name         TEXT NOT NULL,                              -- auch für Teile, die nicht im Lager sind
    qty          INTEGER,
    gathered     INTEGER NOT NULL DEFAULT 0,
    gathered_at  TEXT
);
CREATE INDEX project_item_project ON project_item(project_id);

CREATE TABLE api_key (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    key_hash    TEXT NOT NULL UNIQUE,                        -- sha256, Schlüssel selbst wird nie gespeichert
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    last_used   TEXT
);
