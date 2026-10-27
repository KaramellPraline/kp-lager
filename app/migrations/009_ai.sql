-- KI-Vorschläge an bestehenden Teilen: alter Stand als JSON, damit „Ablehnen“ ihn wiederherstellt.
ALTER TABLE item ADD COLUMN ai_backup TEXT;
