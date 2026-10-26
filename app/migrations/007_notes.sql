-- Längere Sprachaufnahmen (Diktate) -> Transkript -> fertiger Haiku-Prompt zum Kopieren/Herunterladen.
CREATE TABLE voice_note (
    id          INTEGER PRIMARY KEY,
    created_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    duration    INTEGER NOT NULL DEFAULT 0,          -- Sekunden
    audio       TEXT,                                -- Dateiname in data/notes/
    transcript  TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'neu' CHECK (status IN ('neu', 'fertig', 'fehler')),
    error       TEXT NOT NULL DEFAULT ''
);
