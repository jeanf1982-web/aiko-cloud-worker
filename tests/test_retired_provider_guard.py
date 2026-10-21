"""AIKO cloud CI regression: do not depend on retired model inference APIs.

GitHub Models' inference endpoints were retired on 2026-07-30.
Source: https://github.blog/changelog/2026-07-30-github-models-is-now-retired/
This test is static and does not call any provider or touch any other project.
"""
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
RETIRED_HOSTS = ("models."+"github.ai", "models.inference.ai."+"azure.com")


def retired_references(text):
    lowered = text.lower()
    return [host for host in RETIRED_HOSTS if host in lowered]


class RetiredModelEndpointTests(unittest.TestCase):
    def test_retired_models_cannot_be_used_in_aiko_runtime(self):
        paths = [
            ROOT / "worker.py",
            ROOT / "aiko_cloud_chess_executor.py",
            ROOT / "project_boundary.py",
            *(ROOT / "cloud_b8_003").rglob("*.py"),
            *(ROOT / ".github/workflows").glob("*.yml"),
            *(ROOT / ".github/workflows").glob("*.yaml"),
        ]
        for path in paths:
            if path.is_file():
                with self.subTest(path=str(path.relative_to(ROOT))):
                    body = path.read_text(encoding="utf8")
                    self.assertFalse(retired_references(body),
                        "Retired provider present: " + str(path.relative_to(ROOT)))
                    if path.suffix in {".yaml", ".yml"}:
                        self.assertNotIn("models: read", body.lower())

    def test_retirement_guard_detects_invalid_urls(self):
        self.assertEqual(retired_references("https://" + RETIRED_HOSTS[0] + "/inference"), [RETIRED_HOSTS[0]])
        self.assertEqual(retired_references("https://" + RETIRED_HOSTS[1]), [RETIRED_HOSTS[1]])

    def test_fails_closed_without_banning_working_cloud(self):
        self.assertEqual(retired_references("https://api.github.com/repos/example/repo/actions/runs"), [])
        self.assertEqual(retired_references("https://api.cloudflare.com/client/v4"), [])


if __name__ == "__main__":
    unittest.main()
