"""Request-local deadlines and bounded synchronous work shared by agent calls."""
from __future__ import annotations

import asyncio
import contextvars
import inspect
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


async def run_sync(function, *args, **kwargs):
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
    return await asyncio.wait_for(asyncio.shield(task), remaining())


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
