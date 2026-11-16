import asyncio
from datetime import date
import sqlite3
import unittest

from sqlglot import parse_one
from scripts.agents.evaluate_count_queries import cases, evaluate, reference_plan, oracle, INVENTORY, ORDERS


class CountEvaluationTest(unittest.TestCase):
    def test_fixture_coverage_and_rejection_denominators_are_explicit(self):
        report = asyncio.run(evaluate())
        self.assertEqual({'passed': 32, 'total': 32}, report['summary']['fixture'])
        self.assertEqual({'passed': 18, 'total': 18}, report['summary']['rejection'])
        self.assertEqual({'passed': 0, 'total': 0}, report['summary']['live'])

    def test_independent_reference_sql_agrees_with_python_oracle(self):
        with sqlite3.connect(':memory:') as db:
            db.execute("ATTACH DATABASE ':memory:' AS commerce")
            for table, rows in [('inventory', INVENTORY), ('orders', ORDERS)]:
                fields = list(rows[0])
                db.execute('CREATE TABLE commerce.' + table + '(' + ','.join(fields) + ')')
                db.executemany('INSERT INTO commerce.' + table + ' VALUES (' + ','.join('?' for _ in fields) + ')',
                               [tuple(row[field] for field in fields) for row in rows])
            for case in cases():
                with self.subTest(case=case['name']):
                    plan = reference_plan(case['spec'])
                    cursor = db.execute(parse_one(plan.sql, read='postgres').sql(dialect='sqlite'),
                        [str(value) if isinstance(value, date) else value for value in plan.parameters])
                    actual = [dict(zip([field[0] for field in cursor.description], row)) for row in cursor]
                    actual.sort(key=lambda row: repr(sorted(row.items())))
                    expected = oracle(case['spec'], INVENTORY if case['spec']['source'] == 'commerce.inventory' else ORDERS)
                    self.assertEqual(expected, actual)
