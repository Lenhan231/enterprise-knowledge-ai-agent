-- Reports and dashboards have separate libraries, sharing only the existing owner-scoped backend role.
CREATE TABLE dashboard_private.reports (
    id text PRIMARY KEY CHECK (id ~ '^[a-f0-9-]{36}$'),
    owner text NOT NULL CHECK (owner ~ '^[a-f0-9]{64}$'),
    revision integer NOT NULL CHECK (revision >= 1),
    title text NOT NULL CHECK (char_length(title) BETWEEN 1 AND 160),
    updated timestamptz NOT NULL,
    document text NOT NULL,
    html text NOT NULL,
    CHECK (octet_length(document) + octet_length(html) <= 2000000),
    CHECK (jsonb_typeof(document::jsonb) = 'object'),
    CHECK ((document::jsonb ->> 'id') = id),
    CHECK ((document::jsonb ->> 'revision')::integer = revision)
);
CREATE INDEX reports_owner_updated_idx ON dashboard_private.reports(owner, updated DESC, id);
ALTER TABLE dashboard_private.reports ENABLE ROW LEVEL SECURITY;
ALTER TABLE dashboard_private.reports FORCE ROW LEVEL SECURITY;
REVOKE ALL ON dashboard_private.reports FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON dashboard_private.reports TO dashboard_store;
CREATE POLICY report_owner ON dashboard_private.reports
    FOR ALL TO dashboard_store
    USING (owner = (SELECT current_setting('app.dashboard_owner', true)))
    WITH CHECK (owner = (SELECT current_setting('app.dashboard_owner', true)));
