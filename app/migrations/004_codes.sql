-- Code-Schema PRÄFIX-NNN: Gegenstände bekommen eigene Codes (ART-0001), Druckstatus für Etiketten.
ALTER TABLE item ADD COLUMN code TEXT;
CREATE UNIQUE INDEX item_code ON item(code);
ALTER TABLE item ADD COLUMN label_printed INTEGER NOT NULL DEFAULT 0;
ALTER TABLE container ADD COLUMN label_printed INTEGER NOT NULL DEFAULT 0;
DELETE FROM meta WHERE key = 'next_label';  -- alter Zähler ohne Präfix
