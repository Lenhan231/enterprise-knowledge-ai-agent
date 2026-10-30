import asyncio
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from core.agents.conversation_context import ConversationStore
from core.models.agents import AgentRequest, VerifiedIdentity, validate_chat_metadata


def request(subject='alice', roles=('admin',), conversation='c'):
    return AgentRequest(question='Revenue in 2022?', conversation_id=conversation,
                        identity=VerifiedIdentity(subject=subject, permissions={'documents:read'},
                                                  document_roles=roles))


class ConversationContextTest(unittest.IsolatedAsyncioTestCase):
    async def test_context_is_isolated_by_user_and_permissions(self):
        store = ConversationStore()
        async with store.session(request()) as history:
            history.append({'question': 'Revenue in 2022?', 'scope': 'Revenue 2022'})
        async with store.session(request()) as history:
            self.assertEqual(history[0]['scope'], 'Revenue 2022')
        async with store.session(request('bob')) as history:
            self.assertEqual(history, [])
        async with store.session(request(roles=('employee',))) as history:
            self.assertEqual(history, [])

    async def test_expiry_size_bounds_and_stateless_requests(self):
        now = [0]
        store = ConversationStore(clock=lambda: now[0], capacity=2, ttl=10, max_chars=100)
        async with store.session(request()) as history:
            history.extend([{'question': 'x' * 25, 'scope': str(i)} for i in range(10)])
        async with store.session(request()) as history:
            self.assertLessEqual(len(history), 6)
            self.assertLessEqual(sum(len(v) for item in history for v in item.values()), 100)
        now[0] = 11
        async with store.session(request()) as history:
            self.assertEqual(history, [])
        async with store.session(request(conversation=None)) as history:
            history.append({'question': 'secret', 'scope': 'secret'})
        async with store.session(request(conversation=None)) as history:
            self.assertEqual(history, [])

    async def test_active_context_cannot_be_evicted_and_cancelled_waiter_cleans_up(self):
        store = ConversationStore(capacity=1)
        entered = asyncio.Event()
        async def waiter():
            async with store.session(request()) as history:
                entered.set()
        async with store.session(request()):
            pending = asyncio.create_task(waiter())
            await asyncio.sleep(0)
            self.assertFalse(entered.is_set())
            with self.assertRaisesRegex(RuntimeError, 'busy'):
                async with store.session(request('bob')):
                    pass
            pending.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await pending
        async with store.session(request('bob')) as history:
            self.assertEqual(history, [])

    def test_client_cannot_inject_internal_metadata(self):
        for key in ['identity', 'history', 'plan', 'task_results', 'deadline', '_orchestration']:
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_chat_metadata({key: 'forged'})
        self.assertEqual(validate_chat_metadata({'category': 'Outdoor'}), {'category': 'Outdoor'})
