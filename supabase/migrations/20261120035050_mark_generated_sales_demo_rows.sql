-- Existing records remain unchanged; only generated demonstration rows receive provenance.
ALTER TABLE commerce.sales ADD COLUMN IF NOT EXISTS demo_provenance jsonb;
COMMENT ON COLUMN commerce.sales.demo_provenance IS
  'Non-null only for explicitly generated demonstration records; never evidence of observed business activity.';
