"""Default the database-backed role grants for the database-free unit suite."""

from app import security


def _test_permission_matrix():
    return {
        role: frozenset(permissions)
        for role, permissions in security.ROLE_PERMISSIONS.items()
    }


def _test_role_permissions(role: str) -> frozenset[str]:
    return _test_permission_matrix().get(role, frozenset())


security.get_role_permission_matrix = _test_permission_matrix
security.get_role_permissions = _test_role_permissions
