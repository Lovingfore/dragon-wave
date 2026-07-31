# Scheduled Refresh Reliability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make hourly data refreshes resilient to one missed GitHub schedule and automatically publish every successful data commit to GitHub Pages.

**Architecture:** A focused Python freshness policy decides whether a staggered cron candidate should run. The monitor workflow exposes whether it committed new data and conditionally calls the Pages workflow as a reusable workflow, which checks out the latest `main` branch.

**Tech Stack:** Python 3.12 standard library, `unittest`, GitHub Actions YAML, GitHub Pages.

---

## File Map

- Create `scripts/refresh_policy.py`: parse refresh metadata and make the force/staleness decision.
- Create `tests/test_refresh_policy.py`: unit coverage for freshness edge cases.
- Create `tests/test_workflows.py`: structural regression coverage for workflow wiring.
- Modify `.github/workflows/monitor.yml`: redundant cron candidates, freshness gate, update output, and reusable deploy call.
- Modify `.github/workflows/pages.yml`: add `workflow_call` and always deploy the latest `main` content.

### Task 1: Refresh Policy

**Files:**
- Create: `tests/test_refresh_policy.py`
- Create: `scripts/refresh_policy.py`

- [ ] **Step 1: Write the failing policy tests**

```python
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
        self.assertFalse(should_refresh(self.payload("2026-07-31T12:00:01Z"), self.now, 45))

    def test_data_at_threshold_is_stale(self):
        self.assertTrue(should_refresh(self.payload("2026-07-31T12:00:00Z"), self.now, 45))

    def test_force_bypasses_freshness(self):
        self.assertTrue(should_refresh(self.payload("2026-07-31T12:44:00Z"), self.now, 45, force=True))

    def test_missing_malformed_and_future_dates_refresh(self):
        self.assertTrue(should_refresh({}, self.now, 45))
        self.assertTrue(should_refresh(self.payload("not-a-date"), self.now, 45))
        self.assertTrue(should_refresh(self.payload("2026-07-31T12:46:00Z"), self.now, 45))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the policy tests and verify the missing module failure**

Run: `python -m unittest tests.test_refresh_policy -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'refresh_policy'`.

- [ ] **Step 3: Implement the minimal policy and CLI**

```python
import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path


def parse_generated_at(payload):
    value = payload.get("metadata", {}).get("generatedAt")
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def should_refresh(payload, now=None, max_age_minutes=45, force=False):
    if force:
        return True
    current_time = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    generated_at = parse_generated_at(payload)
    if generated_at is None or generated_at > current_time:
        return True
    return current_time - generated_at >= timedelta(minutes=max_age_minutes)


def main():
    parser = argparse.ArgumentParser(description="Decide whether LFCX data needs a refresh")
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--max-age-minutes", type=int, default=45)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    try:
        payload = json.loads(args.data.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        payload = {}
    print(str(should_refresh(payload, max_age_minutes=args.max_age_minutes, force=args.force)).lower())


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the policy tests and verify they pass**

Run: `python -m unittest tests.test_refresh_policy -v`

Expected: 4 tests pass.

- [ ] **Step 5: Commit the policy**

```bash
git add scripts/refresh_policy.py tests/test_refresh_policy.py
git commit -m "feat: add refresh freshness policy"
```

### Task 2: Reliable Workflow Wiring

**Files:**
- Create: `tests/test_workflows.py`
- Modify: `.github/workflows/monitor.yml`
- Modify: `.github/workflows/pages.yml`

- [ ] **Step 1: Write failing workflow regression tests**

```python
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MONITOR = (ROOT / ".github" / "workflows" / "monitor.yml").read_text(encoding="utf-8")
PAGES = (ROOT / ".github" / "workflows" / "pages.yml").read_text(encoding="utf-8")


class MonitorWorkflowTests(unittest.TestCase):
    def test_has_staggered_refresh_candidates_and_freshness_gate(self):
        self.assertIn('cron: "7,27,47 * * * *"', MONITOR)
        self.assertIn("python scripts/refresh_policy.py", MONITOR)
        self.assertIn("--max-age-minutes 45", MONITOR)
        self.assertIn("steps.freshness.outputs.should_refresh == 'true'", MONITOR)

    def test_manual_and_daily_runs_force_refresh(self):
        self.assertIn("github.event_name == 'workflow_dispatch'", MONITOR)
        self.assertIn("github.event.schedule == '0 14 * * *'", MONITOR)

    def test_data_commit_conditionally_calls_pages(self):
        self.assertIn("updated: ${{ steps.persist.outputs.updated }}", MONITOR)
        self.assertIn("needs.monitor.outputs.updated == 'true'", MONITOR)
        self.assertIn("uses: ./.github/workflows/pages.yml", MONITOR)


class PagesWorkflowTests(unittest.TestCase):
    def test_is_reusable_and_checks_out_latest_main(self):
        self.assertIn("workflow_call:", PAGES)
        self.assertIn("ref: main", PAGES)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the workflow tests and verify they fail**

Run: `python -m unittest tests.test_workflows -v`

Expected: FAIL because the staggered cron, freshness gate, reusable call, and `main` checkout are absent.

- [ ] **Step 3: Update the monitor workflow**

Implement these exact behaviors in `.github/workflows/monitor.yml`:

```yaml
on:
  schedule:
    - cron: "7,27,47 * * * *"
    - cron: "0 14 * * *"
  workflow_dispatch:
    inputs:
      notify_mode:
        description: Email mode
        required: true
        default: auto
        type: choice
        options: [auto, daily, test]

jobs:
  monitor:
    outputs:
      updated: ${{ steps.persist.outputs.updated }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Decide whether refresh is due
        id: freshness
        env:
          FORCE_REFRESH: ${{ github.event_name == 'workflow_dispatch' || github.event.schedule == '0 14 * * *' }}
        run: |
          force_arg=""
          if [ "$FORCE_REFRESH" = "true" ]; then force_arg="--force"; fi
          decision=$(python scripts/refresh_policy.py --data data/metrics.json --max-age-minutes 45 $force_arg)
          echo "should_refresh=$decision" >> "$GITHUB_OUTPUT"
      - name: Skip fresh candidate
        if: steps.freshness.outputs.should_refresh != 'true'
        run: echo "Data was refreshed less than 45 minutes ago"
```

Keep the existing update, notification, and persistence commands, add `if: steps.freshness.outputs.should_refresh == 'true'` to all three, set `id: persist`, and write `updated=false` or `updated=true` to `$GITHUB_OUTPUT` in the two persistence branches.

Add a reusable workflow job after `monitor`:

```yaml
  deploy:
    needs: monitor
    if: needs.monitor.outputs.updated == 'true'
    permissions:
      contents: read
      pages: write
      id-token: write
    uses: ./.github/workflows/pages.yml
```

- [ ] **Step 4: Make the Pages workflow reusable**

Add `workflow_call:` under `on` in `.github/workflows/pages.yml`, and make checkout explicitly use current `main`:

```yaml
      - uses: actions/checkout@v4
        with:
          ref: main
```

- [ ] **Step 5: Run workflow and privacy regression tests**

Run: `python -m unittest tests.test_workflows tests.test_privacy -v`

Expected: all workflow and privacy tests pass.

- [ ] **Step 6: Commit workflow reliability**

```bash
git add .github/workflows/monitor.yml .github/workflows/pages.yml tests/test_workflows.py
git commit -m "fix: make scheduled refreshes resilient"
```

### Task 3: Integrate, Deploy, and Verify

**Files:**
- Verify all files changed in Tasks 1 and 2.

- [ ] **Step 1: Run the complete local test suite**

Run: `python -m unittest discover -s tests -v`

Expected: all existing and new tests pass with zero failures.

- [ ] **Step 2: Check repository integrity**

Run: `git diff --check`

Expected: no whitespace errors.

Run: `git status --short --branch`

Expected: a clean branch containing the design, plan, policy, tests, and workflow commits.

- [ ] **Step 3: Rebase onto the automated data commit and push**

```bash
git fetch origin main
git rebase origin/main
git push origin main
```

Expected: the branch fast-forwards remote `main` without force-push.

- [ ] **Step 4: Verify the source push deployment**

Use the GitHub Actions API to wait for `Deploy dashboard` on the pushed implementation SHA.

Expected: conclusion `success` and the public page returns HTTP 200.

- [ ] **Step 5: Manually dispatch the optimized monitor**

Dispatch `monitor.yml` on `main` with `notify_mode=auto` using the authenticated GitHub API.

Expected: the monitor forces a refresh, commits a new `data/metrics.json`, and its dependent reusable Pages job succeeds without a separate manual Pages dispatch.

- [ ] **Step 6: Verify published metadata**

Compare `generatedAt`, `dailyDataDate`, `priceDataDate`, `spotSource`, and `dataQuality` between raw `main` and the Pages URL with a cache-busting query.

Expected: raw and published metadata match, `dataQuality` is `complete`, and the live page returns HTTP 200.
