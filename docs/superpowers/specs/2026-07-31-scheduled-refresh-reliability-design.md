# Scheduled Refresh Reliability Design

Date: 2026-07-31
Status: Approved for implementation planning

## Problem

The dashboard depends on a single hourly GitHub Actions schedule at minute 7. GitHub documents scheduled workflows as best-effort: an event can be delayed or dropped under load. The first scheduled event after deployment was not dispatched.

The data workflow can still be run manually and successfully commits refreshed `data/metrics.json`. However, that commit uses the repository `GITHUB_TOKEN`, so it does not trigger the separate Pages workflow's `push` event. Data can therefore be current in `main` while the published site remains stale.

## Goals

- Stay entirely on GitHub and require no paid or third-party scheduler.
- Recover from one missed hourly schedule within approximately 20 minutes.
- Avoid unnecessary refresh commits when data was updated recently.
- Preserve the daily 22:00 Asia/Shanghai email run and manual dispatch modes.
- Publish Pages automatically after every successful data workflow.
- Keep failures visible in Actions and never deploy after a failed refresh.

## Non-Goals

- Guarantee execution at an exact minute; GitHub schedules cannot provide that guarantee.
- Change market-data providers, risk calculations, notification rules, or dashboard UI.
- Add credentials beyond the existing optional Gmail secrets.

## Design

### Redundant schedule

Replace the single hourly cron with three staggered candidates at minutes 7, 27, and 47. Keep the dedicated daily cron at 14:00 UTC.

Each staggered event checks freshness before doing network work. A successful refresh makes later candidates no-ops until the stored `metadata.generatedAt` is at least 45 minutes old. This normally produces one refresh per hour while giving two fallback opportunities when GitHub drops an event.

Manual dispatch and the daily-email schedule always bypass the freshness gate.

### Refresh policy

Add a small Python policy module under `scripts/` that:

- parses the stored UTC `generatedAt` timestamp;
- reports whether the data is at least 45 minutes old;
- treats a missing, malformed, or future timestamp as stale so recovery is attempted;
- accepts an explicit force flag for manual and daily runs.

The workflow exposes the policy decision as a step output. Data update, notification, and persistence steps run only when the decision is `true`. A skipped candidate logs a clear message and exits successfully.

### Pages publication

Make the Pages workflow reusable with `workflow_call` while preserving its existing `push` and manual triggers. The monitor job exposes whether its persistence step created a data commit, and a dependent job calls the reusable Pages workflow only when that output is `true`.

The reusable Pages workflow explicitly checks out `main`, so a call from the monitor uses the data commit that the monitor just pushed rather than the older triggering SHA. A freshness no-op does not call Pages.

## Error Handling

- Data-fetch or model failures fail the monitor workflow and prevent downstream deployment.
- Missing Gmail secrets continue to skip email without blocking data persistence.
- Invalid freshness metadata forces a refresh instead of suppressing recovery.
- Concurrent monitor runs remain serialized by the existing concurrency group.
- A successful no-op freshness check does not deploy because the monitor reports that no data commit was produced.

## Testing

- Unit-test fresh, stale, missing, malformed, future, and forced policy inputs.
- Add workflow regression tests for the three staggered schedules, the 45-minute freshness gate, forced daily/manual behavior, the monitor's update output, and the reusable Pages call.
- Run the full existing unittest suite.
- After deployment, manually dispatch the monitor workflow and verify:
  - the data workflow succeeds;
  - a new data commit reaches `main`;
  - Pages starts automatically without a manual Pages dispatch;
  - the published metadata matches the new commit.

## Success Criteria

- Missing one GitHub schedule no longer postpones the next opportunity by a full hour.
- Normal operation creates no more than roughly one data refresh per hour.
- Daily and manual runs are never blocked by freshness.
- Every successful data refresh automatically reaches the public Pages site.
- All tests and both production workflows complete successfully.
