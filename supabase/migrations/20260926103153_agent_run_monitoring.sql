-- Operational trace metadata only; never store the user question, prompt, or answer.
CREATE TABLE public.agent_run_events (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    actor_role text NOT NULL,
    agent_name text NOT NULL DEFAULT 'unrouted',
    retrieval_method text NOT NULL
        CHECK (retrieval_method IN ('dense', 'bm25', 'hybrid', 'parent')),
    status text NOT NULL
        CHECK (status IN ('completed', 'failed', 'rate_limited')),
    elapsed_ms integer NOT NULL CHECK (elapsed_ms >= 0),
    citation_count integer NOT NULL DEFAULT 0 CHECK (citation_count >= 0),
    error_type text,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK ((status = 'completed' AND error_type IS NULL)
        OR (status <> 'completed' AND error_type IS NOT NULL))
);

CREATE INDEX agent_run_events_created_at_idx
    ON public.agent_run_events (created_at DESC);
CREATE INDEX agent_run_events_agent_created_at_idx
    ON public.agent_run_events (agent_name, created_at DESC);

ALTER TABLE public.agent_run_events ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.agent_run_events FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.agent_run_events TO service_role;
GRANT USAGE, SELECT ON SEQUENCE public.agent_run_events_id_seq TO service_role;
