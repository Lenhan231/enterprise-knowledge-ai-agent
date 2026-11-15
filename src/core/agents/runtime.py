"""Request-local deadlines and bounded synchronous work shared by agent calls."""
from __future__ import annotations

import asyncio
import contextvars
import inspect
import os
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor

deadline = contextvars.ContextVar('agent_deadline', default=None)
_slots = threading.BoundedSemaphore(8)
_workers = ThreadPoolExecutor(max_workers=8, thread_name_prefix='agent')


def remaining(default=60.0):
    end = deadline.get()
    value = default if end is None else min(default, end - time.monotonic())
    if value <= 0:
        raise TimeoutError('Agent request deadline exhausted')
    return value


async def run_sync(function, *args, _timeout=60.0, **kwargs):
    # Keep the slot until the actual thread exits, even if its caller times out.
    if not _slots.acquire(blocking=False):
        raise RuntimeError('Agent worker capacity is busy')

    def work():
        try:
            remaining()
            return function(*args, **kwargs)
        finally:
            _slots.release()

    try:
        future = _workers.submit(contextvars.copy_context().run, work)
    except BaseException:
        _slots.release()
        raise
    future.add_done_callback(lambda done: _slots.release() if done.cancelled() else None)
    task = asyncio.wrap_future(future)
    task.add_done_callback(lambda done: None if done.cancelled() else done.exception())
    return await asyncio.wait_for(asyncio.shield(task), remaining(_timeout))


async def generate(provider, prompt, *, timeout=15):
    token = deadline.set(time.monotonic() + remaining(timeout))
    try:
        if inspect.iscoroutinefunction(provider.generate):
            return await asyncio.wait_for(provider.generate(prompt), remaining(timeout))
        result = await run_sync(provider.generate, prompt)
        if inspect.isawaitable(result):
            return await asyncio.wait_for(result, remaining(timeout))
        return result
    finally:
        deadline.reset(token)


async def generate_with_local_codex(prompt, provider_error):
    # Local debugging only: use authenticated Codex CLI after provider failure.
    # This opt-in is not intended for deployed environments or main.
    if os.getenv('CODEX_CLI_SQL_FALLBACK', 'false').casefold() != 'true':
        raise provider_error
    executable = shutil.which('codex')
    if not executable:
        raise RuntimeError('Local Codex CLI fallback is enabled but codex is unavailable') from provider_error
    prompt = (
        'Local debugging response rule: answer in the language used by the user question in this prompt. '
        'If the question is Vietnamese, keep all user-facing text in Vietnamese. Preserve the requested JSON or other output format.\n\n'
        + prompt
    )
    process = await asyncio.create_subprocess_exec(
        executable, 'exec', '--ephemeral', '--sandbox', 'read-only', '--skip-git-repo-check', '-',
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(prompt.encode('utf-8')), timeout=remaining(60)
        )
    except asyncio.TimeoutError as error:
        process.kill()
        await process.communicate()
        raise TimeoutError('Local Codex CLI generation exceeded its deadline') from error
    if process.returncode:
        detail = stderr.decode('utf-8', errors='replace').strip()
        raise RuntimeError(f'Local Codex CLI generation failed: {detail[-1000:]}') from provider_error
    answer = stdout.decode('utf-8', errors='replace').strip()
    if not answer:
        raise RuntimeError('Local Codex CLI returned an empty response') from provider_error
    return answer
