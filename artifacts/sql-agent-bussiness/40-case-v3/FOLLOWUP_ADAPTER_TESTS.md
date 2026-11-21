# Follow-up adapter and tests

Adapter: followup_adapter.py, version context-conditioned-sql.v1.

The SQL Agent's native _sql_context decoder supports typed inventory follow-up state and rejects non-inventory follow-up memory. Four v3 cases use sales, orders, or returns context. Rather than claiming that the application has general conversational memory, v3 uses context-conditioned SQL: it sends the frozen prior user question, a bounded allowlisted JSON semantic state, and the current user follow-up in a normal SQL-mode request.

The adapter:

- validates the context hash and adapter version;
- allows only metric, formula, source, date/snapshot scope, population, grouping, and ranking context;
- rejects SQL, parameters, results, rows, assistant answers, and unknown fields;
- emits ChatRequest(agent_mode="sql", metadata={});
- records hashes of the prior question and structured context.

test_followup_adapter.py checks all five cases, request construction, the SQLAnalyticsAgent._query_text path, and inclusion of the context in the SQL-generation prompt builder. It does not call an LLM, execute SQL, or run the SQL Agent benchmark. Actual model use of inherited context remains an execution-time measurement; no held-out question was executed during preparation.

Run:

    PYTHONPATH=src uv run python -m unittest discover \
      -s artifacts/sql-agent-bussiness/40-case-v3 -p 'test_followup_adapter.py' -v
