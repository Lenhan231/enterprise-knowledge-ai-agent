# Dashboard field reconciliation and tile deletion

Dashboard planning remains model-driven, but field binding and rendering status now follow observed SQL outputs. A missing temporal alias such as `date` binds to `month` only when SQL grouping and actual returned dates identify one unambiguous date dimension. Unrelated metrics and ambiguous dimensions are never guessed. Numeric grouping columns such as `year` are excluded from inferred measures.

For dashboards with charts, summary tiles must reuse a chart dataset. An independent summary query or a KPI attached to a chart dataset triggers one bounded plan repair before SQL execution. Descriptive summaries are calculated from the returned observations in code; canonical metric validation and SQL permissions are unchanged. A total KPI still needs its own aggregate query. Invalid tile shapes produce explicit unavailable states rather than invented totals.

Each dashboard includes `tile_status`. Complete data with an invalid chart no longer produces a complete dashboard. Opening old saved documents reconciles fields and status against their existing data; refresh preserves their definition. **Rebuild from description** is needed once for older plans with independent, unsupported statistics queries. HTML open/download uses the reconciled presentation as well.

**Delete tile** removes a tile from the editor draft; **Save edits** persists the deletion and updates the preview. At least one tile must remain; the existing Delete action removes the entire dashboard. Shared datasets are retained while another tile uses them, and unused datasets are removed so future refreshes do not rerun abandoned questions. Existing ownership, revision conflicts and sandboxing still apply.

The Cloudflare GPT-OSS models now use low reasoning effort and a bounded 2,048-token default allowance. Other model defaults and explicit budgets are preserved. A live 20B check had exhausted the old 1,000-token allowance in reasoning with no final JSON; the adjusted check completed successfully. The provider does not substitute reasoning text for final output.

Verification: 35 focused Python checks and a Node editor-interaction check pass. Groq Qwen and Cloudflare GPT-OSS-20B both built a monthly revenue chart and summary, and the 11 returned monthly values matched exactly after alias normalization. These are smoke checks, not an overall model-reliability benchmark. Full-suite fail-fast remains blocked by an unchanged document-processing output-metadata assertion; its log and provider artifacts stay under ignored `artifacts/local`.
