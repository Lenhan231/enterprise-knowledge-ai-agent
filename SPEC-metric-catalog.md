# Spec: metric-catalog

Status: implementation specification transcribed from the user's detailed task and explicit Inventory Management scope approval. Module boundaries and inventory conventions were approved in conversation. Scope changes outside inventory require renewed review.

## Objective
Versioned Inventory Management definitions, catalog schema validation and documented unresolved inventory candidates. Load inventory definitions into the existing ontology; retain unrelated pre-existing definitions without extending them.

## Stack and structure
Python 3.11, Pydantic, sqlglot, PyYAML already in the dependency lock; unittest. Runtime: src/core/analytics and src/core/agents; catalog: data/semantic/vietstyle_metrics_v1.yaml; tests: tests/test_inventory_metric_dictionary.py; reports: docs/business_metric_dictionary.md and docs/metric_validation_report.md.

## Commands
Focused tests: .venv/Scripts/python.exe -m unittest discover -s tests -p test_inventory_metric_dictionary.py -v
Full tests: .venv/Scripts/python.exe -m unittest discover -s tests -v
Compile: .venv/Scripts/python.exe -m compileall -q src tests
Whitespace: git diff --check

## Style
Reuse get_metric_definition(name), resolve_metric_names(question), validate_metric_definitions(sql, names, parameters, columns). Keep plain functions and structured MetricDefinitionError codes; no registry/service duplicating the catalog.

## Acceptance and testing
Catalog provenance/approval/validation are independent. Stored values and aggregates have explicit meanings. Exact dates or explicit database-latest selection are mandatory for snapshots; historical trends keep exact snapshot groups. Reject cross-date sums, unsupported dimensions, unresolved formulas, unknown inventory aggregates, unsafe joins and unauthorized execution. Fixtures must check numbers, not just SQL syntax. Existing unrelated behavior remains outside this scoped change.

## Boundaries
Always: preserve unrelated working files, existing benchmarks, read-only permissions, parameterization and output limits; record limitations and actual test results.
Ask first: a new business convention outside the reviewed inventory assumptions, database changes, model changes or unrelated feature work.
Never: production DML/RLS/migrations, inferred currency, invented source formulas, Schema Discovery Agent, fine-tuning, or changed Report section generation.

## Unresolved
Original fill-rate denominator/weighting; operational reorder point/quantity, safety stock, lead times, live stock, inventory accuracy and turnover/valuation definitions without their required evidence remain non-executable.
