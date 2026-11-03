-- Projekt-Reservierung (Menge je Stücklistenzeile) und Artikelnummer bei Einkäufen (Wiedererkennung beim Import).
ALTER TABLE project_item ADD COLUMN reserved INTEGER NOT NULL DEFAULT 0;
ALTER TABLE purchase ADD COLUMN sku TEXT NOT NULL DEFAULT '';
CREATE INDEX purchase_sku ON purchase(sku);
