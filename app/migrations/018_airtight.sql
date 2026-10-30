-- Behälter: luftdicht (Airtight) ja/nein.
ALTER TABLE container ADD COLUMN airtight INTEGER NOT NULL DEFAULT 0;
