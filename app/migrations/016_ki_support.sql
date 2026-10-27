-- KI-Support: Prüfstatus je Teil (Warteschlange) und Inhaltsetiketten für Bins/Fächer.
ALTER TABLE item ADD COLUMN ai_checked TEXT;  -- Zeitpunkt, an dem ein Mensch das Teil geprüft hat
CREATE TABLE content_queue (
    node_id   INTEGER PRIMARY KEY REFERENCES container(id) ON DELETE CASCADE,
    text      TEXT NOT NULL,
    added_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
