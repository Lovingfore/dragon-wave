import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MONITOR = (ROOT / ".github" / "workflows" / "monitor.yml").read_text(
    encoding="utf-8"
)
PAGES = (ROOT / ".github" / "workflows" / "pages.yml").read_text(
    encoding="utf-8"
)


class MonitorWorkflowTests(unittest.TestCase):
    def test_has_staggered_refresh_candidates_and_freshness_gate(self):
        self.assertIn('cron: "7,27,47 * * * *"', MONITOR)
        self.assertIn("python scripts/refresh_policy.py", MONITOR)
        self.assertIn("--max-age-minutes 45", MONITOR)
        self.assertIn(
            "steps.freshness.outputs.should_refresh == 'true'", MONITOR
        )

    def test_manual_and_daily_runs_force_refresh(self):
        self.assertIn("github.event_name == 'workflow_dispatch'", MONITOR)
        self.assertIn("github.event.schedule == '0 14 * * *'", MONITOR)

    def test_data_commit_conditionally_calls_pages(self):
        self.assertIn(
            "updated: ${{ steps.persist.outputs.updated }}", MONITOR
        )
        self.assertIn("needs.monitor.outputs.updated == 'true'", MONITOR)
        self.assertIn("uses: ./.github/workflows/pages.yml", MONITOR)


class PagesWorkflowTests(unittest.TestCase):
    def test_is_reusable_and_checks_out_latest_main(self):
        self.assertIn("workflow_call:", PAGES)
        self.assertIn("ref: main", PAGES)


if __name__ == "__main__":
    unittest.main()
