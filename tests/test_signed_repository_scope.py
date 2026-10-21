import unittest
from worker import verify_repository_boundary

class RepositoryScopeTests(unittest.TestCase):
    def test_expected_repository_allowed(self):
        self.assertTrue(verify_repository_boundary({'GITHUB_ACTIONS':'true','GITHUB_REPOSITORY':'jeanf1982-web/aiko-cloud-worker'}))

    def test_unexpected_repository_rejected(self):
        with self.assertRaises(SystemExit):
            verify_repository_boundary({'GITHUB_ACTIONS':'true','GITHUB_REPOSITORY':'example/other'})

    def test_missing_repository_rejected(self):
        with self.assertRaises(SystemExit):
            verify_repository_boundary({'GITHUB_ACTIONS':'true'})

    def test_local_usage_unchanged(self):
        self.assertTrue(verify_repository_boundary({'GITHUB_ACTIONS':'false'}))
