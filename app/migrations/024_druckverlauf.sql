-- M46: Druckverlauf (Wiederholung, auch als Batch)
CREATE TABLE label_job (
    id     INTEGER PRIMARY KEY,
    ts     TEXT NOT NULL DEFAULT (datetime('now')),
    codes  TEXT NOT NULL,            -- Codes, durch Leerzeichen getrennt
    n      INTEGER NOT NULL,
    ok     INTEGER NOT NULL DEFAULT 1,
    error  TEXT NOT NULL DEFAULT ''
);
