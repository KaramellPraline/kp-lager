-- Etiketten-Layout je Typ (JSON: QR-Position, Zeilen mit Vorlage, Höhenanteil, Ausrichtung).
ALTER TABLE type_setting ADD COLUMN label_layout TEXT NOT NULL DEFAULT '';
