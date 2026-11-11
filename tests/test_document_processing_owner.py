"""Processing ownership is enforced by API permissions, not only navigation."""
import os
import unittest
from unittest.mock import patch

from app.main import app, _issue_token, _role_accounts
from app.security import DOCUMENT_ROLES, ROLE_PERMISSIONS, _roles_with_permission


class ProcessingOwnerTest(unittest.TestCase):
    def test_owner_permissions_are_exclusive(self):
        for permission in ('process_documents', 'run_upload_tests', 'review_upload_tests'):
            self.assertEqual(_roles_with_permission(permission), ('document_processing_owner',))
        self.assertNotIn('document_processing_owner', DOCUMENT_ROLES)
        self.assertNotIn('manage_knowledge', ROLE_PERMISSIONS['document_processing_owner'])

    def test_owner_account_uses_environment_configuration(self):
        with patch.dict(os.environ, {
            'DEMO_DOCUMENT_PROCESSING_OWNER_USERNAME': 'processing-owner-test',
            'DEMO_DOCUMENT_PROCESSING_OWNER_PASSWORD': 'test-password',
        }):
            self.assertEqual(_role_accounts()['processing-owner-test'],
                             ('test-password', 'document_processing_owner'))

    def test_other_roles_cannot_access_processing_or_upload_test(self):
        from fastapi import HTTPException
        from starlette.requests import Request
        from app.security import require_permission
        with patch.dict(os.environ, {'AUTH_SECRET_KEY': 'test-secret-' * 4}):
            for role in ('admin', 'employee', 'document_uploader'):
                token = _issue_token('test', role)
                request = Request({'type': 'http', 'headers': [
                    (b'cookie', ('enterprise_session=' + token).encode()),
                ]})
                for permission in ('process_documents', 'run_upload_tests', 'review_upload_tests'):
                    with self.assertRaises(HTTPException) as error:
                        require_permission(permission)(request, None)
                    self.assertEqual(error.exception.status_code, 403)

    def test_owner_session_passes_processing_and_upload_test_permissions(self):
        from starlette.requests import Request
        from app.security import require_permission
        with patch.dict(os.environ, {'AUTH_SECRET_KEY': 'test-secret-' * 4}):
            token = _issue_token('owner', 'document_processing_owner')
            request = Request({'type': 'http', 'headers': [
                (b'cookie', ('enterprise_session=' + token).encode()),
            ]})
            for permission in ('process_documents', 'run_upload_tests', 'review_upload_tests'):
                self.assertEqual(require_permission(permission)(request, None)['role'],
                                 'document_processing_owner')


if __name__ == '__main__':
    unittest.main()
