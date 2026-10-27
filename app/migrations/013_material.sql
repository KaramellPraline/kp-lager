-- 3D-Druck-Material (Filament FIL-, UV-Harz RES-Codes) und Einkaufsdaten für alle Teile.
ALTER TABLE item ADD COLUMN material TEXT;          -- 'fil' | 'res' | NULL
ALTER TABLE item ADD COLUMN specs TEXT NOT NULL DEFAULT '{}';  -- Eigenschaften (app/materials.py)
ALTER TABLE item ADD COLUMN order_url TEXT NOT NULL DEFAULT '';
ALTER TABLE item ADD COLUMN price REAL;             -- Euro je Stück/Spule/Flasche
