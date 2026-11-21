# Independent review and freeze checklist

**Do not mark a case approved until both reviewers have independently completed it.** The current decision file is entirely pending.

## Per-case review (all B40-001 through B40-040)

- [ ] Wording has one intended interpretation and matches the expected behavior.
- [ ] Metric, population, date field/range, filters, grouping, ranking/ties and output contract match the wording.
- [ ] Source tables/columns and joins exist in the approved schema and preserve grain.
- [ ] NULL policy and numeric tolerance are appropriate and frozen before model outputs are inspected.
- [ ] Pilot overlap disposition and any replacement from the original design are accepted.
- [ ] For execute cases: gold SQL and bound parameters independently reviewed against the contract.
- [ ] For clarify/abstain cases: missing/ambiguous fields and safe terminal behavior are explicit.
- [ ] Provisional rows match independently reviewed gold semantics; no SQL Agent output was used to create gold.

## Cohort and experiment gates

- [ ] Exactly 40 cases; 30 execute, 5 clarify, 5 abstain; no exact duplicate questions.
- [ ] Two reviewers work independently; disagreements are recorded and adjudicated.
- [ ] Freeze question wording, case hash, SQL/parameter hash, output tolerances, result/oracle hash and protocol version.
- [ ] Confirm frozen DB fingerprint, read-only role, source hashes and allowed schema immediately before use.
- [ ] Keep the five pilot/development examples out of the held-out cohort after overlap adjudication.
- [ ] SQL Agent invocation remains 0 during gold preparation; no 40-case agent run until explicit later authorization.
- [ ] For any later model comparison, freeze primary/fallback provider policy; model attribution must reflect every fallback call.

## Reviewer signatures

| Role | Reviewer identity | Decision | Date | Notes |
|---|---|---|---|---|
| Reviewer 1 | PENDING | PENDING | | |
| Reviewer 2 | PENDING | PENDING | | |
| Adjudicator | PENDING | PENDING | | |
