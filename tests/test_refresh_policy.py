import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from refresh_policy import should_refresh


class RefreshPolicyTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 7, 31, 12, 45, tzinfo=timezone.utc)

    def payload(self, generated_at):
        return {"metadata": {"generatedAt": generated_at}}

    def test_data_younger_than_threshold_is_fresh(self):
        self.assertFalse(
            should_refresh(self.payload("2026-07-31T12:00:01Z"), self.now, 45)
        )

    def test_data_at_threshold_is_stale(self):
        self.assertTrue(
            should_refresh(self.payload("2026-07-31T12:00:00Z"), self.now, 45)
        )

    def test_force_bypasses_freshness(self):
        self.assertTrue(
            should_refresh(
                self.payload("2026-07-31T12:44:00Z"), self.now, 45, force=True
            )
        )

    def test_missing_malformed_and_future_dates_refresh(self):
        self.assertTrue(should_refresh({}, self.now, 45))
        self.assertTrue(should_refresh(self.payload("not-a-date"), self.now, 45))
        self.assertTrue(
            should_refresh(self.payload("2026-07-31T12:46:00Z"), self.now, 45)
        )


if __name__ == "__main__":
    unittest.main()
