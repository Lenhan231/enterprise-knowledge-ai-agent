# Independent review checklist

Use one copy per reviewer. Reviewers should work independently before adjudication. “Looks plausible” is not approval; cite the question, schema contract, SQL, and frozen snapshot evidence.

## Case wording and intent

- [ ] The request has one defensible interpretation and uses business terminology clearly.
- [ ] Metric, population, date/snapshot scope, grain, filters, ranking, tie-break, and output match the question.
- [ ] Follow-up cases inherit only the specified prior user context and apply only the requested change.
- [ ] Clarifications ask for missing information without implying unavailable data exists.
- [ ] Unsupported and destructive requests produce no business SQL.
- [ ] The case is not a duplicate of another v3 case or the pilot cohort.

## Gold SQL and results

- [ ] Tables, columns, metric formulas, approved joins, and join grain are correct.
- [ ] Date bounds are half-open or otherwise justified by verified column type.
- [ ] NULL behavior, aggregation, grouping, ranking, tie-break, and limit are correct.
- [ ] Bound parameters match the stated time/filter scope.
- [ ] Gold result rows and output columns match a fresh read-only execution.
- [ ] Tolerances are justified and fixed before any SQL Agent run.
- [ ] SQL Agent output was not used to author Gold SQL or results.

## Discriminative quality

- [ ] Each applicable mutation changes the intended semantic property.
- [ ] Result-based detection and validator rejection are counted separately.
- [ ] Valid observationally equivalent mutations are recorded as such.
- [ ] No artificial data or altered database records were used.

## Reviewer record

| Field | Value |
|---|---|
| Reviewer ID | |
| Date | |
| Case IDs reviewed | |
| Per-case decision artifact | |
| Blocking issues | |
| Approval | PENDING |

Adjudication must resolve every blocking disagreement and preserve the original reviewer records. No review is recorded in this draft.
