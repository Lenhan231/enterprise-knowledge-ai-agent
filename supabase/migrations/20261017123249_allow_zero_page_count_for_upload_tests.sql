-- Non-PDF Upload Test inputs (Office, CSV, text, and images) may not have
-- rendered page previews. A count of zero means no page previews were saved.
ALTER TABLE public.upload_test_runs
    DROP CONSTRAINT ocr_test_runs_page_count_check,
    ADD CONSTRAINT upload_test_runs_page_count_check CHECK (page_count >= 0);
