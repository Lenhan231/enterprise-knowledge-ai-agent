import asyncio
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from app.agents import AgentChatRequest, agent_chat, agent_chat_stream
from core.latency import measure
from core.models.agents import AgentResult


def _events(body: str) -> list[tuple[str, dict]]:
    out = []
    for block in body.split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines() if not line.startswith(":"))
        if lines:
            out.append((lines["event"], json.loads(lines["data"])))
    return out


def _stream(runtime, payload=None) -> list[tuple[str, dict]]:
    async def collect():
        with patch("app.agents._get_runtime", new=AsyncMock(return_value=runtime)), \
                patch("app.agents._record_agent_run"):
            response = await agent_chat_stream(
                payload or AgentChatRequest(question="policy?", agent_mode="knowledge"), Mock(),
                user={"role": "admin", "sub": "test"})
            assert response.headers["content-type"].startswith("text/event-stream")
            return "".join([chunk async for chunk in response.body_iterator])
    return _events(asyncio.run(collect()))


class ChatStreamTest(unittest.TestCase):
    def test_clarification_choice_metadata_reaches_the_selected_agent(self):
        selection = {'question': 'How should revenue be calculated?', 'index': 1}
        received = {}

        async def run_mode(request, mode):
            received.update(request.metadata)
            return AgentResult(answer='Selected', agent=mode)

        runtime = Mock()
        runtime.run_mode = run_mode
        payload = AgentChatRequest(question='Dựa trên order_items', agent_mode='knowledge',
                                   metadata={'clarification_choice': selection})
        events = _stream(runtime, payload)

        self.assertEqual(received['clarification_choice'], selection)
        self.assertEqual(events[-1][1]['answer'], 'Selected')

    def test_versioned_clarification_reply_reaches_router_for_stream(self):
        reply = {'clarification_id': 'opaque-pending-id-0001', 'version': 3,
                 'choice_id': 'opaque-choice-id-0001'}
        received = {}

        async def run_mode(request, mode):
            received.update(request.metadata)
            return AgentResult(answer='Selected', agent=mode)

        runtime = Mock()
        runtime.run_mode = run_mode
        payload = AgentChatRequest(question='All regions', agent_mode='sql',
                                   clarification_reply=reply)
        events = _stream(runtime, payload)

        self.assertEqual(received['clarification_reply'], reply)
        self.assertEqual(events[-1][1]['answer'], 'Selected')

    def test_custom_clarification_reply_reaches_router_and_preserves_contract_on_post(self):
        reply = {'clarification_id': 'opaque-pending-id-0001', 'version': 3}
        ui = {'id': reply['clarification_id'], 'version': reply['version'],
              'question': 'Specify a region', 'choices': [], 'allow_custom': True}
        received = {}

        async def run_mode(request, mode):
            received.update(request.metadata)
            return AgentResult(answer='Specify a region', agent=mode,
                               metadata={'status': 'clarification_required', 'clarification_ui': ui})

        runtime = Mock()
        runtime.run_mode = run_mode
        payload = AgentChatRequest(question='Hanoi', agent_mode='sql', clarification_reply=reply)

        async def request_post():
            with patch('app.agents._get_runtime', new=AsyncMock(return_value=runtime)), \
                    patch('app.agents._record_in_background'):
                return await agent_chat(payload, Mock(headers={}), user={'role': 'admin', 'sub': 'test'})

        result = asyncio.run(request_post())
        self.assertEqual(received['clarification_reply'], reply)
        self.assertEqual(result.metadata['clarification_ui'], ui)

    def test_stages_from_worker_threads_arrive_before_the_verified_answer(self):
        def rerank():
            with measure("reranking"):
                pass

        async def run_mode(request, mode):
            await asyncio.to_thread(rerank)
            with measure("claim_verification"):
                pass
            return AgentResult(answer="Answer [S1]", agent="knowledge")

        runtime = Mock()
        runtime.run_mode = run_mode
        events = _stream(runtime)

        self.assertEqual([(kind, data.get("stage"), data.get("state")) for kind, data in events[:-1]], [
            ("stage", "reranking", "started"), ("stage", "reranking", "completed"),
            ("stage", "claim_verification", "started"), ("stage", "claim_verification", "completed"),
        ])
        kind, result = events[-1]
        self.assertEqual(kind, "result")
        self.assertEqual(result["answer"], "Answer [S1]")
        self.assertIn("latency", result["metadata"])

    def test_failure_is_sent_as_an_error_event_without_an_answer(self):
        runtime = Mock()
        runtime.run_mode = AsyncMock(side_effect=RuntimeError("boom"))
        events = _stream(runtime)

        self.assertEqual(events, [("error", {"status": 503, "detail": "The agent service is unavailable"})])


if __name__ == "__main__":
    unittest.main()
