"""Agent implementations and helpers have one canonical package per agent."""
import importlib
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))


class AgentPackageLayoutTest(unittest.TestCase):
    def test_agent_entry_points_use_canonical_packages(self):
        for package, name in (
            ('sql', 'SQLAnalyticsAgent'),
            ('knowledge', 'KnowledgeAgent'),
            ('report', 'ReportAgent'),
            ('dashboard', 'DashboardDocumentAgent'),
            ('decision_support', 'AgentOrchestrator'),
        ):
            module_name = 'orchestrator' if package == 'decision_support' else 'agent'
            with self.subTest(package=package):
                module = importlib.import_module(f'core.agents.{package}.{module_name}')
                self.assertEqual(getattr(module, name).__module__, module.__name__)
                self.assertEqual(Path(module.__file__).parent, ROOT / 'src/core/agents' / package)

    def test_agent_helpers_share_their_agent_package(self):
        for module_name in (
            'sql.analytics_agent', 'sql.assistant_endpoint',
            'sql.schema', 'sql.compiler_dispatch',
            'sql.text_to_sql', 'sql.sql_validation', 'sql.metric_mapping',
            'knowledge.rag_service', 'knowledge.claim_verification',
            'report.generation', 'report.templates',
            'dashboard.sql_runtime', 'dashboard.render',
            'decision_support.execution', 'decision_support.intent_classifier',
        ):
            with self.subTest(module=module_name):
                importlib.import_module(f'core.agents.{module_name}')

    def test_obsolete_agent_locations_have_no_source(self):
        for path in (
            'sql_agent', 'analytics',
            'agents/sql_analytics_agent.py', 'agents/analytics_agent.py',
            'agents/knowledge_agent.py', 'agents/report_agent.py',
            'agents/dashboard_agent.py', 'agents/hybrid_agent.py',
            'agents/router.py', 'agents/planning.py', 'agents/execution.py',
            'agents/response.py', 'agents/conversation_context.py',
            'agents/intent_classifier.py', 'reports', 'dashboards', 'rag',
        ):
            with self.subTest(path=path):
                location = ROOT / 'src/core' / path
                if location.is_dir():
                    self.assertEqual(list(location.rglob('*.py')), [])
                else:
                    self.assertFalse(location.exists())
