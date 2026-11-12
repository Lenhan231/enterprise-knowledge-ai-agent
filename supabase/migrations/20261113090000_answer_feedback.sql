-- Written only when a user rates an answer (thumbs up/down). Unlike agent_run_events, the rated
-- question and answer are kept, because reviewing a disliked answer is the point of the feedback.
CREATE TABLE public.answer_feedback (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    actor_role text NOT NULL,
    agent_name text NOT NULL,
    rating text NOT NULL CHECK (rating IN ('up', 'down')),
    question text NOT NULL CHECK (char_length(question) BETWEEN 1 AND 2000),
    answer text NOT NULL CHECK (char_length(answer) BETWEEN 1 AND 20000),
    comment text CHECK (char_length(comment) <= 1000),
    claim_status text CHECK (char_length(claim_status) <= 40),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX answer_feedback_created_at_idx ON public.answer_feedback (created_at DESC);

ALTER TABLE public.answer_feedback ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.answer_feedback FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT ON public.answer_feedback TO service_role;
GRANT USAGE, SELECT ON SEQUENCE public.answer_feedback_id_seq TO service_role;
