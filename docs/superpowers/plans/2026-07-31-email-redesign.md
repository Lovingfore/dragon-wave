# Dark Email Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a fixed dark-mode LFCX EPOCH email whose five-column metric table is aligned, clearly bordered, and uses the same persisted bottom forecast as the website.

**Architecture:** Move the browser's bottom-forecast calculation into a pure Python model function and persist its result under `assessment.bottomForecast` during every data refresh. The website prefers that field with its current JavaScript calculation as a backward-compatible fallback, while the notifier renders an email-client-safe inline-style table from the same field.

**Tech Stack:** Python 3.12 standard library, `unittest`, vanilla JavaScript, semantic HTML tables, GitHub Actions, Gmail SMTP.

---

## File Map

- Modify `scripts/model.py`: own the reusable bottom-forecast calculation.
- Modify `tests/test_model.py`: verify forecast math and incomplete-data behavior.
- Modify `scripts/update_data.py`: persist `assessment.bottomForecast` in generated data.
- Modify `tests/test_data_schema.py`: enforce the generated forecast contract.
- Modify `data/metrics.json`: regenerate tracked data with the new contract.
- Modify `assets/js/app.js`: prefer the persisted forecast and retain the legacy calculation as fallback.
- Create `tests/test_frontend_contract.py`: guard the website's persisted-first behavior.
- Modify `scripts/notify.py`: render the approved dark five-column email and text alternative.
- Create `tests/test_notify_email.py`: parse and verify email structure, styles, values, fallback, and escaping.
- Modify `.gitignore`: exclude `.superpowers/` visual-companion artifacts.

### Task 1: Reusable Bottom Forecast Model

**Files:**
- Modify: `tests/test_model.py`
- Modify: `scripts/model.py`

- [ ] **Step 1: Write failing forecast tests**

Add `bottom_forecast` to the import and add this deterministic fixture and assertions:

```python
class BottomForecastTests(unittest.TestCase):
    def setUp(self):
        self.series = [
            {"date": "2011-11-18", "price": 2, "mvrv": 0.40, "mvrvZ": -0.60, "wwi": 0.140, "realizedPrice": 5, "blocks": 144, "blockHeight": 150000},
            {"date": "2015-01-14", "price": 176, "mvrv": 0.56, "mvrvZ": -0.60, "wwi": 0.040, "realizedPrice": 312, "blocks": 144, "blockHeight": 340000},
            {"date": "2018-12-15", "price": 3185, "mvrv": 0.69, "mvrvZ": -0.49, "wwi": 0.017, "realizedPrice": 4613, "blocks": 144, "blockHeight": 555000},
            {"date": "2022-11-09", "price": 15758, "mvrv": 0.75, "mvrvZ": -0.36, "wwi": 0.008, "realizedPrice": 20901, "blocks": 144, "blockHeight": 762000},
            {"date": "2025-10-01", "price": 100000, "mvrv": 2.0, "mvrvZ": 2.0, "wwi": 0.8, "realizedPrice": 50000, "blocks": 144, "blockHeight": 920000},
            {"date": "2026-01-31", "price": 70000, "mvrv": 1.4, "mvrvZ": 0.7, "wwi": 0.4, "realizedPrice": 50000, "blocks": 144, "blockHeight": 940000},
            {"date": "2026-07-30", "price": 63627, "mvrv": 1.2, "mvrvZ": 0.35, "wwi": 0.207, "realizedPrice": 52865, "blocks": 144, "blockHeight": 960400},
        ]

    def test_forecast_matches_the_browser_model_contract(self):
        forecast = bottom_forecast(
            series=self.series,
            current={"realizedPrice": {"value": 52865}},
            block_height=960400,
            daily_data_date="2026-07-30",
        )
        self.assertEqual(forecast["asOf"], "2026-07-30")
        self.assertEqual(forecast["targetDate"], "2026-10-13")
        self.assertAlmostEqual(forecast["values"]["mvrv"], 0.659, places=6)
        self.assertAlmostEqual(forecast["values"]["mvrvZ"], -0.471, places=6)
        self.assertAlmostEqual(forecast["values"]["wwi"], 0.0303, places=6)
        self.assertAlmostEqual(forecast["values"]["nupl"], 1 - 1 / 0.659, places=6)
        self.assertIsNotNone(forecast["values"]["price"])
        self.assertIsNotNone(forecast["values"]["realizedPrice"])

    def test_missing_history_returns_unavailable_values(self):
        missing = bottom_forecast([], {}, None, None)
        self.assertIsNone(missing["targetDate"])
        self.assertTrue(all(value is None for value in missing["values"].values()))
```

- [ ] **Step 2: Run the model tests and confirm RED**

Run: `python -m unittest tests.test_model.BottomForecastTests -v`

Expected: FAIL because `bottom_forecast` is not defined.

- [ ] **Step 3: Implement the pure forecast function**

In `scripts/model.py`, add `BEAR_MARKET_WINDOWS`, `_median`, `_recency_weighted_mean`, `_bear_market_bottoms`, and:

```python
def bottom_forecast(series, current, block_height, daily_data_date=None):
    bottoms = _bear_market_bottoms(series)
    latest_row = next((row for row in reversed(series) if safe_float(row.get("realizedPrice")) is not None), None)
    latest_date = (latest_row or {}).get("date") or daily_data_date
    latest_bottom_date = next((row["date"] for row in reversed(bottoms) if row), None)

    current_cycle = [
        row for row in series
        if (not latest_bottom_date or row.get("date", "") >= latest_bottom_date)
        and safe_float(row.get("price")) is not None
    ]
    current_top = max(current_cycle, key=lambda row: safe_float(row["price"]), default=None)
    forecast_rows = [row for row in series if not current_top or row.get("date", "") >= current_top["date"]]

    height = safe_float(block_height if block_height is not None else (latest_row or {}).get("blockHeight"))
    phase = (height + 78750) % 210000 if height is not None else None
    blocks_to_bottom = (210000 - phase) % 210000 if phase is not None else 0
    month_start = latest_date[:8] + "01" if latest_date else None
    recent_blocks = [safe_float(row.get("blocks")) for row in series if month_start and row.get("date", "") >= month_start]
    recent_blocks = [value for value in recent_blocks if value is not None and value > 0]
    average_blocks = sum(recent_blocks) / len(recent_blocks) if recent_blocks else 144
    days_to_bottom = blocks_to_bottom / average_blocks if average_blocks > 0 else 0

    target_date = None
    if latest_date:
        target = datetime.strptime(latest_date, "%Y-%m-%d") + timedelta(days=math.floor(days_to_bottom + 0.5))
        target_date = target.strftime("%Y-%m-%d")

    historical = lambda key: [safe_float(row.get(key)) for row in bottoms if row and safe_float(row.get(key)) is not None]
    baseline_mvrv = _recency_weighted_mean(historical("mvrv"))
    expected_mvrv_z = _recency_weighted_mean(historical("mvrvZ"))
    expected_wwi = _recency_weighted_mean(historical("wwi"))
    cycle_mvrv = [safe_float(row.get("mvrv")) for row in forecast_rows if safe_float(row.get("mvrv")) is not None]
    expected_mvrv = min([baseline_mvrv] + cycle_mvrv) if baseline_mvrv is not None else None

    realized_rows = [row for row in series if safe_float(row.get("realizedPrice")) is not None]
    trend_start = realized_rows[max(0, len(realized_rows) - 181)] if realized_rows else None
    trend_end = realized_rows[-1] if realized_rows else None
    trend_days = max(1, (datetime.strptime(trend_end["date"], "%Y-%m-%d") - datetime.strptime(trend_start["date"], "%Y-%m-%d")).days) if trend_start and trend_end else 0
    trend_rate = 0
    if trend_days and safe_float(trend_start["realizedPrice"]) > 0 and safe_float(trend_end["realizedPrice"]) > 0:
        trend_rate = max(-0.001, min(0.001, math.log(safe_float(trend_end["realizedPrice"]) / safe_float(trend_start["realizedPrice"])) / trend_days))

    current_realized = safe_float(current.get("realizedPrice", {}).get("value"))
    if current_realized is None and latest_row:
        current_realized = safe_float(latest_row.get("realizedPrice"))
    projected_days = min(540, max(0, days_to_bottom))
    expected_realized = current_realized * math.exp(trend_rate * projected_days) if current_realized is not None else None
    expected_price = expected_realized * expected_mvrv if expected_realized is not None and expected_mvrv is not None else _median(historical("price"))
    expected_nupl = 1 - 1 / expected_mvrv if expected_mvrv is not None and expected_mvrv > 0 else None
    expected_risk, _ = composite_risk({
        "price": expected_price,
        "realizedPrice": expected_realized,
        "nupl": expected_nupl,
        "mvrv": expected_mvrv,
        "mvrvZ": expected_mvrv_z,
        "wwi": expected_wwi,
    })
    values = {
        "price": expected_price, "nupl": expected_nupl,
        "realizedPrice": expected_realized, "mvrv": expected_mvrv,
        "mvrvZ": expected_mvrv_z, "wwi": expected_wwi,
        "riskScore": expected_risk,
    }
    if not series:
        values = {key: None for key in values}
    return {"values": values, "asOf": daily_data_date or latest_date, "targetDate": target_date}
```

- [ ] **Step 4: Run the focused and full model tests**

Run: `python -m unittest tests.test_model.BottomForecastTests -v`

Expected: PASS.

Run: `python -m unittest tests.test_model -v`

Expected: all model tests PASS.

- [ ] **Step 5: Commit the model change**

```bash
git add scripts/model.py tests/test_model.py
git commit -m "feat: calculate persisted bottom forecast"
```

### Task 2: Persist the Forecast in Generated Data

**Files:**
- Modify: `scripts/update_data.py`
- Modify: `tests/test_data_schema.py`
- Modify: `data/metrics.json`

- [ ] **Step 1: Write the failing schema test**

Add:

```python
def test_bottom_forecast_contract(self):
    forecast = self.data["assessment"]["bottomForecast"]
    self.assertRegex(forecast["asOf"], r"^\d{4}-\d{2}-\d{2}$")
    self.assertRegex(forecast["targetDate"], r"^\d{4}-\d{2}-\d{2}$")
    self.assertEqual(
        set(forecast["values"]),
        {"price", "nupl", "realizedPrice", "mvrv", "mvrvZ", "wwi", "riskScore"},
    )
    for value in forecast["values"].values():
        self.assertIsNotNone(value)
        self.assertTrue(math.isfinite(value))
```

- [ ] **Step 2: Confirm the schema test fails**

Run: `python -m unittest tests.test_data_schema.GeneratedDataTests.test_bottom_forecast_contract -v`

Expected: ERROR with missing `bottomForecast`.

- [ ] **Step 3: Persist the model output**

Import `bottom_forecast` in `scripts/update_data.py`. After creating `current`, calculate:

```python
forecast = bottom_forecast(
    series,
    current,
    tip_height,
    latest_onchain["date"],
)
```

Add `"bottomForecast": forecast` to `payload["assessment"]`.

- [ ] **Step 4: Regenerate tracked data**

Run: `python scripts/update_data.py --daily-only`

Expected: prints a line beginning with `Updated ` and ending with the price and on-chain dates, and writes `assessment.bottomForecast` to `data/metrics.json` without changing source credentials or notification state.

- [ ] **Step 5: Verify generated data**

Run: `python -m unittest tests.test_data_schema -v`

Expected: all generated-data tests PASS.

- [ ] **Step 6: Commit the data contract**

```bash
git add scripts/update_data.py tests/test_data_schema.py data/metrics.json
git commit -m "feat: persist bottom forecast in metrics"
```

### Task 3: Make the Website Prefer Persisted Forecast Data

**Files:**
- Create: `tests/test_frontend_contract.py`
- Modify: `assets/js/app.js`

- [ ] **Step 1: Add a failing source-contract test**

```python
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class FrontendForecastContractTests(unittest.TestCase):
    def test_bottom_table_prefers_persisted_forecast_with_legacy_fallback(self):
        source = (ROOT / "assets" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("state.data.assessment?.bottomForecast", source)
        self.assertIn("persistedForecast?.values ? persistedForecast : expectedBottomForecast(bottoms)", source)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Confirm the frontend contract test fails**

Run: `python -m unittest tests.test_frontend_contract -v`

Expected: FAIL because `renderBottomComparison` always recalculates locally.

- [ ] **Step 3: Add persisted-first selection**

At the start of `renderBottomComparison`, replace the direct forecast call with:

```javascript
const persistedForecast = state.data.assessment?.bottomForecast;
const forecast = persistedForecast?.values ? persistedForecast : expectedBottomForecast(bottoms);
```

- [ ] **Step 4: Run the frontend contract test**

Run: `python -m unittest tests.test_frontend_contract -v`

Expected: PASS.

- [ ] **Step 5: Commit the website integration**

```bash
git add assets/js/app.js tests/test_frontend_contract.py
git commit -m "feat: share bottom forecast with dashboard"
```

### Task 4: Render the Approved Dark Five-Column Email

**Files:**
- Create: `tests/test_notify_email.py`
- Modify: `scripts/notify.py`

- [ ] **Step 1: Add failing structured HTML tests**

Use `xml.etree.ElementTree` to parse `build_email` output from a fixture containing all six current metrics and `assessment.bottomForecast`. Assert:

```python
root = ElementTree.fromstring(html_body)
table = root.find(".//table[@data-role='metrics']")
headers = [cell.text for cell in table.findall("./thead/tr/th")]
self.assertEqual(headers, ["指标", "最新值", "预测底部值", "1 日", "7 日"])
self.assertEqual(root.find("body").attrib["bgcolor"], "#0e1113")
self.assertIn("#181c1f", html_body)
self.assertIn("#465158", html_body)
self.assertIn("#312c20", html_body)
self.assertIn("$34,268", html_body)

for row in table.findall("./tbody/tr"):
    cells = row.findall("td")
    self.assertEqual(len(cells), 5)
    self.assertEqual(cells[0].attrib["align"], "left")
    self.assertTrue(all(cell.attrib["align"] == "right" for cell in cells[1:]))
    self.assertTrue(all("border:1px solid #465158" in cell.attrib["style"] for cell in cells))
```

Add a second test with no `bottomForecast` and assert every predicted cell is `--`. Add a third test with HTML metacharacters in labels/detail and assert escaped text is preserved after parsing rather than interpreted as markup. Assert the plain-text header contains `预测底部值`.

- [ ] **Step 2: Confirm the email tests fail**

Run: `python -m unittest tests.test_notify_email -v`

Expected: FAIL because the current email has four columns, light backgrounds, and no forecast.

- [ ] **Step 3: Implement the email-safe dark layout**

Keep the existing subject/lead branches and SMTP boundary. Update row generation to read `assessment.bottomForecast.values`, use `format_value` for both current and forecast values, and render five cells with explicit width/alignment:

```python
cell_base = "padding:10px 8px;border:1px solid #465158;line-height:1.35"
row_bg = "#1d2225" if index % 2 else "#181c1f"
rows.append(
    f'<tr bgcolor="{row_bg}">'
    f'<td width="29%" align="left" style="{cell_base};color:#e8edef">{escaped_label}</td>'
    f'<td width="18%" align="right" style="{cell_base};color:#e8edef;white-space:nowrap">{escaped_value}</td>'
    f'<td width="25%" align="right" bgcolor="#312c20" style="{cell_base};background:#312c20;color:#f2d889;white-space:nowrap">{escaped_forecast}</td>'
    f'<td width="14%" align="right" style="{cell_base};color:#e8edef;white-space:nowrap">{escaped_day}</td>'
    f'<td width="14%" align="right" style="{cell_base};color:#e8edef;white-space:nowrap">{escaped_week}</td>'
    '</tr>'
)
```

Build the outer layout with presentation tables, `bgcolor` fallbacks, `max-width:680px`, and inline colors from the approved design. Mark the data table `data-role="metrics"`, use exact text headers, and include the dynamic-estimate disclaimer. Add a small media query that reduces outer padding, font size, and cell padding below 520px without hiding any column.

Update the plain-text table header and each row to include the formatted forecast between current value and daily change. Missing forecasts become `--`.

- [ ] **Step 4: Run focused email and privacy tests**

Run: `python -m unittest tests.test_notify_email tests.test_privacy -v`

Expected: all email structure, escaping, missing-data, credential privacy, and SMTP error tests PASS.

- [ ] **Step 5: Commit the email redesign**

```bash
git add scripts/notify.py tests/test_notify_email.py
git commit -m "feat: redesign notification email for dark mode"
```

### Task 5: Repository Hygiene and End-to-End Verification

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: Ignore visual-companion artifacts**

Add `.superpowers/` to `.gitignore`, then confirm `git status --short` no longer lists the mockup session.

- [ ] **Step 2: Run the full test suite**

Run: `python -m unittest discover -s tests -v`

Expected: all tests PASS with no credential values in output.

- [ ] **Step 3: Generate a real email preview**

Run a small temporary Python command that loads `data/metrics.json`, calculates `state = risk_state(data["assessment"]["riskScore"])`, calls `build_email(data, state, "test")`, and writes only element 2 of the returned tuple (the HTML body) to a temporary preview file outside tracked source files.

Expected: valid HTML containing six metric rows and five columns.

- [ ] **Step 4: Verify desktop and mobile rendering**

Serve the temporary preview locally and inspect it at 1280x900 and 390x844. Confirm:

- dark background fills the message;
- no blank canvas or missing content;
- all header and numeric cells align;
- grid borders are visible;
- the forecast column remains distinct but subdued;
- no horizontal overflow or overlapping text at mobile width.

- [ ] **Step 5: Run repository checks**

Run: `git diff --check`

Expected: no output.

Run: `git status --short`

Expected: only intended source, test, data, plan, and `.gitignore` changes, or clean after commits.

- [ ] **Step 6: Commit hygiene changes and the plan**

```bash
git add .gitignore docs/superpowers/plans/2026-07-31-email-redesign.md
git commit -m "docs: plan and ignore email design previews"
```

### Task 6: Publish and Send the Test Email

**Files:** None.

- [ ] **Step 1: Synchronize with remote main**

Run: `git fetch origin --prune`

If `origin/main` advanced, run `git rebase origin/main`, preserving the implementation commits. Run the full test suite again after any rebase.

- [ ] **Step 2: Push the reviewed commits**

Run: `git push origin HEAD:main`

Expected: push succeeds without force and updates `main`.

- [ ] **Step 3: Dispatch the existing workflow in test mode**

Trigger `.github/workflows/monitor.yml` on `main` with `notify_mode=test` through the existing authenticated GitHub session. Do not print or persist the GitHub credential or Gmail secrets.

Expected: the workflow refreshes data, sends one test email, commits refreshed data when changed, and invokes Pages deployment.

- [ ] **Step 4: Wait for remote verification**

Wait until the workflow and reusable Pages job finish. Verify both are successful and that the newest `main` commit contains `assessment.bottomForecast`.

- [ ] **Step 5: Report delivery state**

Report the workflow run URL/status and ask the user only to confirm the visual appearance of the received test email. Do not include the recipient address or any secret value in the response.
