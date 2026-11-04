-- Pflichtfelder (kommagetrennte Feld-Schlüssel) und gemerkte Standardwerte (JSON) je Typ
ALTER TABLE type_setting ADD COLUMN required TEXT NOT NULL DEFAULT '';
ALTER TABLE type_setting ADD COLUMN defaults TEXT NOT NULL DEFAULT '';
