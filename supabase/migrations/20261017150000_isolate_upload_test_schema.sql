-- Keep experimental Upload Test data outside the production public schema.
CREATE SCHEMA upload_test;

ALTER TABLE public.upload_test_runs SET SCHEMA upload_test;
ALTER TABLE public.upload_test_pages SET SCHEMA upload_test;
ALTER TABLE public.upload_test_parser_chunks SET SCHEMA upload_test;
ALTER TABLE public.upload_test_tables SET SCHEMA upload_test;
ALTER TABLE public.upload_test_records SET SCHEMA upload_test;
ALTER TABLE public.upload_test_token_chunks SET SCHEMA upload_test;

GRANT USAGE ON SCHEMA upload_test TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA upload_test TO service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA upload_test
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO service_role;
