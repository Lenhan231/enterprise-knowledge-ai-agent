# Dashboard monthly-revenue execution failure

The deployed primary and fallback backends both returned `DataError` for the user's January–December 2026 monthly-revenue query:

```sql
SELECT DATE_TRUNC('month', s.date) AS month, SUM(s.revenue) AS revenue
FROM commerce.sales AS s
WHERE s.date BETWEEN $1 AND $2
GROUP BY 1 ORDER BY 1 LIMIT 200
```

The date-parameter detector recognized comparisons and `IN`, but omitted `BETWEEN`. Consequently the approved query passed date strings to asyncpg. A read-only reproduction returned `invalid input for query argument $1 ... 'str' object has no attribute 'toordinal'`.

Local generation had used separate `>=`/`<=` comparisons, whose parameters were correctly converted. Both SQL forms are valid; the missing conversion made the behavior depend on the model's chosen predicate.

The fix detects direct bounds of `BETWEEN` on approved or discovered date columns and applies the existing native-date conversion and invalid-date rejection. Numeric bounds are unchanged. Source allowlists, SQL validation, read-only permissions and clarity decisions are unchanged.

Failed dashboard sources now retain attempted SQL and show the safe exception type. Missing SQL text is labeled unavailable instead of claiming that no SQL executed. Database exception messages and credentials are not exposed.

Validation: four new binding checks, 24 SQL-generation checks and 24 dashboard checks pass. The exact failed SQL, decoded through the fixed path and executed through the read-only repository, returned 11 monthly rows. Deployment-level verification is separate from this database reproduction; old failed saved dashboards need a data refresh after deployment.
