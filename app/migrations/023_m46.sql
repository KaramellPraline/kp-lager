-- M46: Teile ohne eigenes Etikett (nur Tag/Fachinhalt), Leergewicht für Behälter
ALTER TABLE item ADD COLUMN standalone INTEGER NOT NULL DEFAULT 1;
ALTER TABLE container ADD COLUMN tare REAL;
