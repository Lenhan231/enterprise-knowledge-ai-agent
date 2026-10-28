-- CSV is accepted by the upload API as text/csv; allow it in the private source bucket.
UPDATE storage.buckets
SET allowed_mime_types = array_append(
    COALESCE(allowed_mime_types, ARRAY[]::text[]),
    'text/csv'
)
WHERE id = 'enterprise-documents'
  AND NOT ('text/csv' = ANY(COALESCE(allowed_mime_types, ARRAY[]::text[])));
