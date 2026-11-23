-- App-level role grants. Keep this in a non-exposed schema; the FastAPI backend
-- connects directly to Postgres and performs authorization before serving routes.
CREATE SCHEMA IF NOT EXISTS private;
REVOKE ALL ON SCHEMA private FROM PUBLIC, anon, authenticated;

CREATE TABLE private.role_permission_grants (
    role text NOT NULL CHECK (role IN (
        'employee', 'finance_analyst', 'sustainability_analyst', 'procurement',
        'operations', 'legal_compliance', 'executive', 'admin',
        'document_uploader', 'document_processing_owner'
    )),
    permission text NOT NULL CHECK (permission IN (
        'view_corpus', 'ask_documents', 'view_analytics', 'upload_documents',
        'classify_documents', 'manage_access', 'manage_knowledge',
        'view_agent_monitoring', 'list_processing_documents', 'process_documents',
        'run_upload_tests', 'review_upload_tests'
    )),
    PRIMARY KEY (role, permission)
);

ALTER TABLE private.role_permission_grants ENABLE ROW LEVEL SECURITY;
ALTER TABLE private.role_permission_grants FORCE ROW LEVEL SECURITY;
REVOKE ALL ON private.role_permission_grants FROM PUBLIC, anon, authenticated, service_role;

INSERT INTO private.role_permission_grants (role, permission) VALUES
    ('employee', 'view_corpus'), ('employee', 'ask_documents'),
    ('finance_analyst', 'view_corpus'), ('finance_analyst', 'ask_documents'),
    ('finance_analyst', 'view_analytics'),
    ('sustainability_analyst', 'view_corpus'), ('sustainability_analyst', 'ask_documents'),
    ('sustainability_analyst', 'view_analytics'),
    ('procurement', 'view_corpus'), ('procurement', 'ask_documents'),
    ('operations', 'view_corpus'), ('operations', 'ask_documents'),
    ('operations', 'view_analytics'),
    ('legal_compliance', 'view_corpus'), ('legal_compliance', 'ask_documents'),
    ('executive', 'view_corpus'), ('executive', 'ask_documents'),
    ('executive', 'view_analytics'),
    ('admin', 'view_corpus'), ('admin', 'ask_documents'), ('admin', 'view_analytics'),
    ('admin', 'upload_documents'), ('admin', 'classify_documents'), ('admin', 'manage_access'),
    ('admin', 'manage_knowledge'), ('admin', 'view_agent_monitoring'),
    ('admin', 'list_processing_documents'),
    ('document_uploader', 'view_corpus'), ('document_uploader', 'upload_documents'),
    ('document_uploader', 'classify_documents'),
    ('document_processing_owner', 'view_corpus'), ('document_processing_owner', 'upload_documents'),
    ('document_processing_owner', 'classify_documents'), ('document_processing_owner', 'process_documents'),
    ('document_processing_owner', 'list_processing_documents'),
    ('document_processing_owner', 'run_upload_tests'), ('document_processing_owner', 'review_upload_tests');
