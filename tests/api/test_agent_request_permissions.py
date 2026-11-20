import unittest

from app.agents import _agent_request


class AgentRequestPermissionsTest(unittest.TestCase):
    def test_only_monitoring_roles_get_agent_diagnostics(self):
        admin = _agent_request({"sub": "a", "role": "admin"}, "q").identity.permissions
        employee = _agent_request({"sub": "e", "role": "employee"}, "q").identity.permissions
        self.assertIn("agents:diagnostics", admin)
        self.assertNotIn("agents:diagnostics", employee)
        self.assertIn("documents:read", employee)


if __name__ == "__main__":
    unittest.main()
