import unittest

from app.agents import _agent_request
from app.security import ROLE_PERMISSIONS


class AgentRequestPermissionsTest(unittest.TestCase):
    def test_only_monitoring_roles_get_agent_diagnostics(self):
        admin = _agent_request({"sub": "a", "role": "admin", "permissions": ROLE_PERMISSIONS["admin"]}, "q").identity.permissions
        employee = _agent_request({"sub": "e", "role": "employee", "permissions": ROLE_PERMISSIONS["employee"]}, "q").identity.permissions
        self.assertIn("agents:diagnostics", admin)
        self.assertNotIn("agents:diagnostics", employee)
        self.assertIn("documents:read", employee)


if __name__ == "__main__":
    unittest.main()
