import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import runner
from core.agents.sql.agent import SQLAnalyticsAgent


class RunnerFollowupTests(unittest.IsolatedAsyncioTestCase):
    async def test_frozen_followups_reach_the_sql_agent_with_prior_context(self):
        case_path = runner.V3_1_DIR / "cases_v3_1_draft.json"
        case_set = json.loads(case_path.read_text(encoding="utf-8"))
        agent = SimpleNamespace(run_payload=AsyncMock(return_value={"ok": True}))
        with tempfile.TemporaryDirectory() as directory:
            store = runner.ExperimentStore(Path(directory) / "run", {}, case_set)
            with patch.object(runner, "instrument_agent", return_value=lambda: None):
                data = await runner.run_cases(agent, case_set, store)

        followups = 0
        for case, call, observed in zip(
            case_set["cases"], agent.run_payload.await_args_list, data["cases"], strict=True
        ):
            request = call.args[0]
            question = SQLAnalyticsAgent._query_text(request)
            self.assertEqual(observed["question"], case["question"])
            self.assertEqual(request.identity.permissions, {"analytics:read"})
            setup = case.get("conversation_setup")
            if setup is None:
                self.assertEqual(question, case["question"])
                continue
            followups += 1
            self.assertIn(setup["prior_user_question"], question)
            self.assertIn(runner.canonical_json(setup["semantic_context"]), question)
            self.assertIn(case["question"], question)
            self.assertEqual(observed["followup_context"]["context_sha256"],
                             setup["semantic_context_sha256"])
        self.assertEqual(followups, 5)
