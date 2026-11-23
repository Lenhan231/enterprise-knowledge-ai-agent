"""Shared session authentication and role permissions for the web app."""

import logging
import os
import time

import jwt
from fastapi import Depends, HTTPException, Request, WebSocket
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError

DOCUMENT_ROLES = {
    "employee", "finance_analyst", "sustainability_analyst", "procurement",
    "operations", "legal_compliance", "executive", "admin",
}
ROLE_PERMISSIONS = {
    "employee": {"view_corpus", "ask_documents"},
    "finance_analyst": {"view_corpus", "ask_documents", "view_analytics"},
    "sustainability_analyst": {"view_corpus", "ask_documents", "view_analytics"},
    "procurement": {"view_corpus", "ask_documents"},
    "operations": {"view_corpus", "ask_documents", "view_analytics"},
    "legal_compliance": {"view_corpus", "ask_documents"},
    "executive": {"view_corpus", "ask_documents", "view_analytics"},
    "admin": {
        "view_corpus", "ask_documents", "view_analytics", "upload_documents",
        "classify_documents", "manage_access", "manage_knowledge",
        "view_agent_monitoring", "list_processing_documents",
    },
    "document_uploader": {"view_corpus", "upload_documents", "classify_documents"},
    "document_processing_owner": {
        "view_corpus", "upload_documents", "classify_documents",
        "process_documents", "list_processing_documents",
        "run_upload_tests", "review_upload_tests",
    },
}
PERMISSION_CATALOG = frozenset(
    permission for permissions in ROLE_PERMISSIONS.values() for permission in permissions
)

auth_scheme = HTTPBearer(auto_error=False)
ACCESS_DENIED_MESSAGE = "Bạn không có quyền truy cập chức năng hoặc tài liệu này."


def _roles_with_permission(permission: str) -> tuple[str, ...]:
    """Return the built-in seed grants; request authorization uses the database matrix."""
    return tuple(role for role, permissions in ROLE_PERMISSIONS.items() if permission in permissions)


def get_role_permission_matrix() -> dict[str, frozenset[str]]:
    """Load current grants from the private application RBAC table; fail closed."""
    connection = None
    try:
        from core.database.connection_limit import close_database_connection, connect_database

        connection = connect_database()
        rows = connection.execute(
            "SELECT role, permission FROM private.role_permission_grants"
        ).fetchall()
        matrix = {role: set() for role in ROLE_PERMISSIONS}
        for role, permission in rows:
            if role in matrix and permission in PERMISSION_CATALOG:
                matrix[role].add(permission)
        return {role: frozenset(permissions) for role, permissions in matrix.items()}
    except Exception as error:
        logging.getLogger(__name__).exception("Could not load role permission grants")
        raise HTTPException(
            503, "Role permissions are unavailable; apply the database migrations",
        ) from error
    finally:
        if connection is not None:
            close_database_connection(connection)


def get_role_permissions(role: str) -> frozenset[str]:
    return get_role_permission_matrix().get(role, frozenset())


def require_permission(permission: str):
    if permission not in PERMISSION_CATALOG:
        raise ValueError(f"Unknown application permission: {permission}")

    def dependency(request: Request, credentials: HTTPAuthorizationCredentials | None = Depends(auth_scheme)):
        user = _current_user(request, credentials)
        permissions = get_role_permissions(user["role"])
        if permission not in permissions:
            raise HTTPException(403, ACCESS_DENIED_MESSAGE)
        return {**user, "permissions": permissions}

    return dependency


def _current_user(request: Request | WebSocket, credentials: HTTPAuthorizationCredentials | None) -> dict:
    token = credentials.credentials if credentials and credentials.scheme.lower() == "bearer" else None
    token = token or request.cookies.get("enterprise_session")
    if not token:
        raise HTTPException(401, "Sign in to continue")
    secret = os.getenv("AUTH_SECRET_KEY", "")
    if len(secret) < 32:
        raise HTTPException(401, "Invalid or expired session")
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"])
    except InvalidTokenError:
        raise HTTPException(401, "Invalid or expired session") from None
    if payload.get("role") not in ROLE_PERMISSIONS:
        raise HTTPException(401, "Invalid or expired session")
    return payload


def require_roles(*roles: str):
    def dependency(request: Request, credentials: HTTPAuthorizationCredentials | None = Depends(auth_scheme)):
        user = _current_user(request, credentials)
        if user["role"] not in roles:
            raise HTTPException(403, ACCESS_DENIED_MESSAGE)
        return user
    return dependency


def _trusted_frontend_origins() -> set[str]:
    return {
        value.strip().rstrip("/")
        for value in os.getenv("TRUSTED_FRONTEND_ORIGINS", "").split(",")
        if value.strip()
    }


def _is_trusted_frontend_origin(origin: str | None) -> bool:
    return bool(origin and origin.rstrip("/") in _trusted_frontend_origins())


def _require_same_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if origin and origin.rstrip("/") != str(request.base_url).rstrip("/") \
            and not _is_trusted_frontend_origin(origin):
        raise HTTPException(403, "Cross-origin uploads are not allowed")
