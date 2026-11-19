-- Extend the private document bucket's existing MIME allowlist.
UPDATE storage.buckets
SET allowed_mime_types = ARRAY(
    SELECT DISTINCT mime_type
    FROM unnest(allowed_mime_types || ARRAY[
        'application/msword',
        'application/vnd.ms-excel',
        'application/vnd.ms-powerpoint',
        'image/bmp',
        'image/gif',
        'image/webp',
        'image/svg+xml',
        'image/heic',
        'image/heif',
        'image/avif'
    ]) AS types(mime_type)
    ORDER BY mime_type
)
WHERE id = 'enterprise-documents'
  AND allowed_mime_types IS NOT NULL;
