-- The application accesses these tables through its trusted server connection.
-- Revoke the default Supabase API grants so RBAC remains behind the app API.
REVOKE ALL PRIVILEGES ON TABLE
    public.documents,
    public.document_chunks,
    public.extracted_tables,
    public.extracted_records
FROM anon, authenticated;

-- Legacy scratch table: no application code or tests use it.
ALTER TABLE public.test_chunks ENABLE ROW LEVEL SECURITY;
REVOKE ALL PRIVILEGES ON TABLE public.test_chunks
FROM anon, authenticated, service_role;
