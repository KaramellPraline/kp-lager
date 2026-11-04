-- A4-Etiketten-Warteschlange, Presets (Klassen) je Typ, Etikett-/CAD-Daten an Behältern
CREATE TABLE a4_job (
    id         INTEGER PRIMARY KEY,
    kind       TEXT NOT NULL,
    title      TEXT NOT NULL DEFAULT '',
    payload    TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE preset (
    id   INTEGER PRIMARY KEY,
    kind TEXT NOT NULL,                  -- Typ-Schlüssel, z. B. filament, harz
    name TEXT NOT NULL,
    data TEXT NOT NULL DEFAULT '{}',     -- JSON: Feld-Schlüssel -> Wert
    UNIQUE (kind, name)
);

ALTER TABLE container ADD COLUMN label_text TEXT;  -- Etikettentext des Fachs/Einsatzes (Tags)
ALTER TABLE container ADD COLUMN cad TEXT;         -- JSON: Parameter-Überschreibungen für den Bin-Generator

INSERT INTO preset (kind, name, data) VALUES
 ('filament', 'PLA',      '{"plastic":"PLA","diameter":"1.75","weight":"1","spool_type":"Pappe","spool_weight":"250"}'),
 ('filament', 'PLA+',     '{"plastic":"PLA+","diameter":"1.75","weight":"1","spool_type":"Plastik","spool_weight":"220"}'),
 ('filament', 'PETG',     '{"plastic":"PETG","diameter":"1.75","weight":"1","spool_type":"Plastik","spool_weight":"220"}'),
 ('filament', 'ABS',      '{"plastic":"ABS","diameter":"1.75","weight":"1","spool_type":"Plastik","spool_weight":"220"}'),
 ('filament', 'ASA',      '{"plastic":"ASA","diameter":"1.75","weight":"1","spool_type":"Plastik","spool_weight":"220"}'),
 ('filament', 'TPU',      '{"plastic":"TPU","diameter":"1.75","weight":"0.5","spool_type":"Plastik","spool_weight":"150"}'),
 ('filament', 'PA12-CF',  '{"plastic":"PA12","plastic_pct":"80","additive":"Carbonfaser","additive_pct":"20","diameter":"1.75","weight":"0.5","spool_type":"Plastik","spool_weight":"150"}'),
 ('filament', 'PETG-CF',  '{"plastic":"PETG","plastic_pct":"85","additive":"Carbonfaser","additive_pct":"15","diameter":"1.75","weight":"0.5","spool_type":"Plastik","spool_weight":"150"}'),
 ('filament', 'PLA-CF',   '{"plastic":"PLA","plastic_pct":"85","additive":"Carbonfaser","additive_pct":"15","diameter":"1.75","weight":"0.5","spool_type":"Plastik","spool_weight":"150"}'),
 ('filament', 'PA6-GF',   '{"plastic":"PA6","plastic_pct":"70","additive":"Glasfaser","additive_pct":"30","diameter":"1.75","weight":"0.5","spool_type":"Plastik","spool_weight":"150"}'),
 ('harz', 'Standard',       '{"material":"Standard","volume":"1000"}'),
 ('harz', 'ABS-like',       '{"material":"ABS-like","volume":"1000"}'),
 ('harz', 'Tough',          '{"material":"Tough","volume":"500"}'),
 ('harz', 'Flexibel',       '{"material":"Flexibel","volume":"500"}'),
 ('harz', 'Wasserwaschbar', '{"material":"Wasserwaschbar","volume":"1000"}');
