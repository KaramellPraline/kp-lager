-- Beschreibung je eigener Art (nur auf der Codes-Seite sichtbar, nicht in Auswahllisten).
ALTER TABLE container_kind ADD COLUMN description TEXT NOT NULL DEFAULT '';
