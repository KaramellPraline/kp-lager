-- Mehr Kartenarten (Eigenschaften, Checkliste, Links): CHECK-Bedingung der Tabelle erweitern.
CREATE TABLE card_new (
    id           INTEGER PRIMARY KEY,
    item_id      INTEGER REFERENCES item(id) ON DELETE CASCADE,
    container_id INTEGER REFERENCES container(id) ON DELETE CASCADE,
    kind         TEXT NOT NULL DEFAULT 'note'
                 CHECK (kind IN ('note', 'pinout', 'spec', 'checklist', 'link')),
    title        TEXT NOT NULL,
    body         TEXT NOT NULL DEFAULT '',
    created_at   TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    CHECK ((item_id IS NULL) <> (container_id IS NULL))
);
INSERT INTO card_new (id, item_id, container_id, kind, title, body, created_at)
    SELECT id, item_id, container_id, kind, title, body, created_at FROM card;
DROP TABLE card;
ALTER TABLE card_new RENAME TO card;
CREATE INDEX card_item ON card(item_id);
CREATE INDEX card_container ON card(container_id);
