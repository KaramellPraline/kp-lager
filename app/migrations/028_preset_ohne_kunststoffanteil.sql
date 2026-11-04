-- Kunststoff hat kein Anteilfeld mehr (= 100 - Zusatz)
UPDATE preset SET data = json_remove(data, '$.plastic_pct');
