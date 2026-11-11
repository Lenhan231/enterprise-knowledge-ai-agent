# Protect SQL aggregates from join duplication

Use declared Commerce primary keys to prove that joins preserve each aggregate's source grain before execution. Keep the existing approved relationships and one-repair flow. This applies to generic queries and ontology metrics through the shared SQL validator and repository boundary.

- Reject SUM, AVG, plain COUNT and other duplication-sensitive aggregates when a source row can match multiple joined rows. Follow renamed/calculated columns through CTEs and derived tables.
- Keep many-to-one dimension joins, one-to-one joins, detail measures, COUNT(DISTINCT entity_key), MIN and MAX available.
- Reject ambiguous COUNT(*) over multiplying joins and SUM(DISTINCT value) used over duplicated inputs. Equal amounts can belong to different entities.
- Prompt the planner to remove multiplying joins or use distinct entity counts. Repeated unsafe plans must not reach the repository.
- No database changes or new dependencies. Snapshot protections remain in place.

This is a conservative structural check based on primary keys in the Commerce schema migration. It does not prove join completeness, business population correctness, or recognize every safe regrouping/filter. Existing restrictions on joining aggregate CTEs remain; a query requiring an unsupported rewrite should clarify instead of execute a risky total.

Validation: 71 focused tests pass, including 15 join-duplication tests, all 17 canonical metric examples, repair-before-execution, repeated unsafe plans, nested CTEs and a scalar-subquery bypass regression. A broader run before the final bypass regression covered 372 tests with the same 13 failures and 48 errors as before; no new failing test IDs. Compilation and whitespace checks pass. The backend image is rebuilt locally; no live LLM or database query is part of these checks.
