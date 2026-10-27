-- Präfix TYP heißt jetzt TAG (Tags ordnen Teile ein, filterbar in der Suche).
UPDATE item_type SET code = 'TAG' || substr(code, 4) WHERE code LIKE 'TYP-%';
UPDATE label_queue SET code = 'TAG' || substr(code, 4) WHERE code LIKE 'TYP-%';
UPDATE meta SET key = 'next:TAG' WHERE key = 'next:TYP';
