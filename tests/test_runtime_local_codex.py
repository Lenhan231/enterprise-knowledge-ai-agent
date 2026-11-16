import os
import sys
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.agents.runtime import deadline, generate_with_local_codex


class LocalCodexFallbackTest(unittest.IsolatedAsyncioTestCase):
    async def test_fallback_uses_remaining_task_budget_instead_of_an_independent_60s_cap(self):
        process = SimpleNamespace(
            communicate=AsyncMock(return_value=(b'OK', b'')),
            returncode=0,
        )
        captured = {}

        async def capture_timeout(awaitable, timeout):
            captured['timeout'] = timeout
            return await awaitable

        token = deadline.set(time.monotonic() + 80)
        try:
            with patch.dict(os.environ, {'CODEX_CLI_SQL_FALLBACK': 'true'}), patch(
                    'core.agents.runtime.shutil.which', return_value='/usr/bin/codex'), patch(
                    'core.agents.runtime.asyncio.create_subprocess_exec', new=AsyncMock(return_value=process)), patch(
                    'core.agents.runtime.asyncio.wait_for', new=capture_timeout):
                await generate_with_local_codex('Return OK.', RuntimeError('provider down'))
        finally:
            deadline.reset(token)

        self.assertGreater(captured['timeout'], 60)
        self.assertLessEqual(captured['timeout'], 80)

    async def test_fallback_preserves_question_language_and_output_format(self):
        process = SimpleNamespace(
            communicate=AsyncMock(return_value=(b'{"clarification":"Vui long lam ro."}', b'')),
            returncode=0,
        )
        with patch.dict(os.environ, {'CODEX_CLI_SQL_FALLBACK': 'true'}), patch(
                'core.agents.runtime.shutil.which', return_value='/usr/bin/codex'), patch(
                'core.agents.runtime.asyncio.create_subprocess_exec', new=AsyncMock(return_value=process)):
            answer = await generate_with_local_codex(
                'Question: "sản phẩm bán chạy nhất tháng trước"\nReturn only JSON.', RuntimeError('provider down'))

        sent_prompt = process.communicate.call_args.args[0].decode()
        self.assertIn('answer in the language used by the user question', sent_prompt)
        self.assertIn('keep all user-facing text in Vietnamese', sent_prompt)
        self.assertIn('Preserve the requested JSON or other output format', sent_prompt)
        self.assertIn('Return only JSON.', sent_prompt)
        self.assertEqual(answer, '{"clarification":"Vui long lam ro."}')


if __name__ == '__main__':
    unittest.main()
