-- Neues Code-Schema (englische Schlüssel, Namen DE/EN): STA -> TBX, EIN -> BIN, sonstiges -> box.
-- Typnamen immer klein. Unbenutzte eigene Arten entfallen (durch feste Arten ersetzt).

UPDATE container SET kind = CASE kind
    WHEN 'raum' THEN 'room' WHEN 'regal' THEN 'shelf' WHEN 'ebene' THEN 'level'
    WHEN 'stapel' THEN 'toolbox' WHEN 'kiste' THEN 'crate' WHEN 'sortierkasten' THEN 'sortingbox'
    WHEN 'einsatz' THEN 'bin' WHEN 'fach' THEN 'compartment' WHEN 'sonstiges' THEN 'box'
    ELSE kind END;

UPDATE container SET code = 'BIN' || substr(code, 4) WHERE code LIKE 'EIN-%';
UPDATE container SET code = 'TBX' || substr(code, 4) WHERE code LIKE 'STA-%';
UPDATE label_queue SET code = 'BIN' || substr(code, 4) WHERE code LIKE 'EIN-%';
UPDATE label_queue SET code = 'TBX' || substr(code, 4) WHERE code LIKE 'STA-%';
UPDATE meta SET key = 'next:BIN' WHERE key = 'next:EIN';
UPDATE meta SET key = 'next:TBX' WHERE key = 'next:STA';

DELETE FROM container_kind WHERE kind NOT IN (SELECT kind FROM container);
DELETE FROM container_kind WHERE prefix IN ('WBA', 'WAL', 'DRW', 'TBX', 'MCF', 'MOD', 'BOX',
    'BIN', 'CNS', 'RAW', 'CBL', 'CMP', 'PPE');

UPDATE item_type SET name = lower(name);
