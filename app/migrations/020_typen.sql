-- Typen: Katalog-Typ und strukturierte Felder je Teil, eigene Typen, Einstellungen je Typ,
-- Stückgewicht/Tara zum Zählen per Waage.
ALTER TABLE item ADD COLUMN ctype TEXT;                          -- Typ-Schlüssel (Katalog oder eigener Typ)
ALTER TABLE item ADD COLUMN cfields TEXT NOT NULL DEFAULT '{}';  -- JSON: Feld -> Wert
ALTER TABLE item ADD COLUMN unit_weight REAL;                    -- Gramm je Stück
ALTER TABLE item ADD COLUMN tare REAL;                           -- Gramm Leergewicht (Tüte, Dose)
CREATE INDEX item_ctype ON item(ctype);

CREATE TABLE custom_type (
    key       TEXT PRIMARY KEY,
    label     TEXT NOT NULL,
    grp       TEXT NOT NULL DEFAULT 'Eigene Typen',
    cat       TEXT NOT NULL DEFAULT 'ART',
    fields    TEXT NOT NULL DEFAULT '[]',   -- JSON: [{"key","label","options":[],"unit"}]
    name_tpl  TEXT NOT NULL DEFAULT ''      -- z. B. "{kind} {size}mm"; leer = Felder der Reihe nach
);

CREATE TABLE type_setting (
    key          TEXT PRIMARY KEY,            -- Typ-Schlüssel (auch mat:fil usw.)
    min_qty      INTEGER,                     -- Standard-Mindestbestand je Teil dieses Typs
    shelf_months INTEGER,                     -- haltbar nach dem Öffnen (Monate)
    label_main   TEXT NOT NULL DEFAULT '',    -- Etikett: große Zeile, z. B. "{thread}x{length}"
    label_extra  TEXT NOT NULL DEFAULT ''     -- Etikett: kleine Zeile, z. B. "{head}"
);
