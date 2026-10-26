-- Volltextsuche über Items. trigram findet Teilwörter (deutsche Komposita: "schraub" in "Holzschrauben").

CREATE VIRTUAL TABLE item_fts USING fts5(
    name, tags, notes, content='item', content_rowid='id', tokenize='trigram'
);
INSERT INTO item_fts(item_fts) VALUES ('rebuild');

CREATE TRIGGER item_fts_ai AFTER INSERT ON item BEGIN
    INSERT INTO item_fts(rowid, name, tags, notes) VALUES (new.id, new.name, new.tags, new.notes);
END;
CREATE TRIGGER item_fts_ad AFTER DELETE ON item BEGIN
    INSERT INTO item_fts(item_fts, rowid, name, tags, notes)
    VALUES ('delete', old.id, old.name, old.tags, old.notes);
END;
CREATE TRIGGER item_fts_au AFTER UPDATE OF name, tags, notes ON item BEGIN
    INSERT INTO item_fts(item_fts, rowid, name, tags, notes)
    VALUES ('delete', old.id, old.name, old.tags, old.notes);
    INSERT INTO item_fts(rowid, name, tags, notes) VALUES (new.id, new.name, new.tags, new.notes);
END;
