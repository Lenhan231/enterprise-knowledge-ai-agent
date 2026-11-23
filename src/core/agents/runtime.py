"""Request-local deadlines and bounded synchronous work shared by agent calls."""
from __future__ import annotations

import asyncio
import contextvars
import inspect
import logging
import os
import re
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.error import HTTPError

logger = logging.getLogger(__name__)
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
        except StopIteration as error:
            raise RuntimeError('Synchronous agent provider stopped unexpectedly') from error
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


def _log_generation_failure(stage, provider, model, prompt, error):
    http_status = getattr(error, 'status_code', None)
    for cause in (error, error.__cause__):
        if isinstance(cause, HTTPError):
            http_status = cause.code
            break
    context_limit_hint = bool(re.search(
        r'context_(?:length|window)_exceeded|maximum context length|context window (?:limit|exceeded)'
        r'|maximum (?:input|prompt) (?:length|tokens)|(?:input(?: text| sequence)?|prompt) is too long'
        r'|too many input tokens',
        f'{getattr(error, "code", None)} {error}', re.I,
    ))
    logger.warning(
        'LLM request failed stage=%s provider=%s model=%s prompt_chars=%d '
        'error_type=%s http_status=%s context_limit_hint=%s',
        stage, provider, model, len(prompt), type(error).__name__,
        http_status if type(http_status) is int else None, context_limit_hint,
    )


async def generate(provider, prompt, *, timeout=15, max_output_tokens=None, log_stage=None):
    token = deadline.set(time.monotonic() + remaining(timeout))
    try:
        kwargs = {}
        if max_output_tokens is not None:
            try:
                parameters = inspect.signature(provider.generate).parameters.values()
                if any(parameter.name == 'max_output_tokens' or parameter.kind == inspect.Parameter.VAR_KEYWORD
                       for parameter in parameters):
                    kwargs['max_output_tokens'] = max_output_tokens
            except (TypeError, ValueError):
                pass
        if inspect.iscoroutinefunction(provider.generate):
            return await asyncio.wait_for(provider.generate(prompt, **kwargs), remaining(timeout))
        result = await run_sync(provider.generate, prompt, **kwargs)
        if inspect.isawaitable(result):
            return await asyncio.wait_for(result, remaining(timeout))
        return result
    except Exception as error:
        if log_stage:
            _log_generation_failure(log_stage, type(provider).__name__,
                                    getattr(provider, 'model_name', None), prompt, error)
        raise
    finally:
        deadline.reset(token)


async def generate_with_codex_cli(prompt, *, timeout=90):
    """Run the authenticated local Codex CLI as an explicitly selected provider."""
    executable = shutil.which('codex')
    if not executable:
        raise RuntimeError('Codex CLI provider is selected but codex is unavailable')
    prompt = (
        'Local debugging response rule: answer in the language used by the user question in this prompt. '
        'If the question is Vietnamese, keep all user-facing text in Vietnamese. Preserve the requested JSON or other output format.\n\n'
        + prompt
    )
    process = await asyncio.create_subprocess_exec(
        executable, 'exec', '--ephemeral', '--sandbox', 'read-only', '--skip-git-repo-check',
        '-C', '/tmp', '-',
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(prompt.encode('utf-8')), timeout=remaining(timeout)
        )
    except asyncio.TimeoutError as error:
        process.kill()
        await process.communicate()
        raise TimeoutError('Local Codex CLI generation exceeded its deadline') from error
    except asyncio.CancelledError:
        process.kill()
        await process.communicate()
        raise
    if process.returncode:
        detail = stderr.decode('utf-8', errors='replace').strip()
        raise RuntimeError(f'Codex CLI generation failed: {detail[-1000:]}')
    answer = stdout.decode('utf-8', errors='replace').strip()
    if not answer:
        raise RuntimeError('Codex CLI returned an empty response')
    return answer


class CodexCLIProvider:
    """Provider adapter for local planner and SQL generation calls."""

    def __init__(self, *, timeout=60):
        self.timeout = timeout

    async def generate(self, prompt, *, max_output_tokens=None):
        return await generate_with_codex_cli(prompt, timeout=self.timeout)


async def generate_with_local_codex(prompt, provider_error, *, log_stage=None):
    # SQL's local fallback is opt-in; production should use a configured API provider.
    if os.getenv('CODEX_CLI_SQL_FALLBACK', 'false').casefold() != 'true':
        raise provider_error
    try:
        return await generate_with_codex_cli(prompt)
    except Exception as error:
        if log_stage:
            _log_generation_failure(log_stage, 'CodexCLIProvider', None, prompt, error)
        raise
