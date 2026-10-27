-- CNS, RAW, CBL, CMP, PPE sind ab jetzt Teile-Kategorien (wie ART/FIL/RES), keine Behälter-Arten.
UPDATE container SET kind = 'box'
    WHERE kind IN ('consumables', 'raw', 'cables', 'components', 'ppe');
