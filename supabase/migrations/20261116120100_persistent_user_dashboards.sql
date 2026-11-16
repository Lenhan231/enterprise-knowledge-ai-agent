CREATE SCHEMA IF NOT EXISTS dashboard_private;
REVOKE ALL ON SCHEMA dashboard_private FROM PUBLIC, anon, authenticated;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dashboard_store') THEN
        CREATE ROLE dashboard_store NOLOGIN NOBYPASSRLS;
    END IF;
END
$$;

GRANT dashboard_store TO postgres;
GRANT USAGE ON SCHEMA dashboard_private TO dashboard_store;

CREATE TABLE dashboard_private.dashboards (
    id text PRIMARY KEY CHECK (id ~ '^[a-f0-9]{32}$'),
    owner text NOT NULL CHECK (owner ~ '^[a-f0-9]{64}$'),
    revision integer NOT NULL CHECK (revision >= 1),
    title text NOT NULL CHECK (char_length(title) BETWEEN 1 AND 120),
    updated timestamptz NOT NULL,
    document text NOT NULL,
    html text NOT NULL,
    CHECK (octet_length(document) + octet_length(html) <= 2000000),
    CHECK (jsonb_typeof(document::jsonb) = 'object'),
    CHECK ((document::jsonb ->> 'id') = id),
    CHECK ((document::jsonb ->> 'revision')::integer = revision)
);

CREATE INDEX dashboards_owner_updated_idx ON dashboard_private.dashboards(owner, updated DESC, id);
ALTER TABLE dashboard_private.dashboards ENABLE ROW LEVEL SECURITY;
ALTER TABLE dashboard_private.dashboards FORCE ROW LEVEL SECURITY;
REVOKE ALL ON dashboard_private.dashboards FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON dashboard_private.dashboards TO dashboard_store;

-- The backend verifies its own session; its subjects are not Supabase Auth UUIDs.
CREATE POLICY dashboard_owner ON dashboard_private.dashboards
    FOR ALL TO dashboard_store
    USING (owner = (SELECT current_setting('app.dashboard_owner', true)))
    WITH CHECK (owner = (SELECT current_setting('app.dashboard_owner', true)));
