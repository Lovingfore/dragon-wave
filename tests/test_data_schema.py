import json
import math
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class GeneratedDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads((ROOT / "data" / "metrics.json").read_text(encoding="utf-8"))

    def test_has_long_history(self):
        series = self.data["series"]
        self.assertGreater(len(series), 6000)
        self.assertEqual(series, sorted(series, key=lambda row: row["date"]))

    def test_required_current_metrics_exist(self):
        required = {"price", "nupl", "realizedPrice", "mvrv", "mvrvZ", "leverage", "wwi"}
        self.assertEqual(set(self.data["current"]), required)
        for key in required - {"leverage"}:
            self.assertIsNotNone(self.data["current"][key]["value"])

    def test_scores_are_bounded(self):
        for row in self.data["series"]:
            score = row.get("riskScore")
            if score is not None:
                self.assertTrue(math.isfinite(score))
                self.assertGreaterEqual(score, 0)
                self.assertLessEqual(score, 100)

    def test_current_wave_is_bounded(self):
        value = self.data["current"]["wwi"]["value"]
        self.assertGreaterEqual(value, 0)
        self.assertLessEqual(value, 1)

    def test_bear_market_bottom_snapshots_are_available(self):
        windows = [
            ("2011-06-01", "2012-11-28"),
            ("2013-12-01", "2016-07-09"),
            ("2017-12-01", "2020-05-11"),
            ("2021-11-01", "2024-04-20"),
        ]
        required = {"price", "nupl", "realizedPrice", "mvrv", "mvrvZ", "wwi", "riskScore"}
        for start, end in windows:
            candidates = [row for row in self.data["series"] if start <= row["date"] <= end and row.get("price") is not None]
            self.assertTrue(candidates)
            bottom = min(candidates, key=lambda row: row["price"])
            for key in required:
                self.assertIsNotNone(bottom.get(key), f"{key} missing at {bottom['date']}")


if __name__ == "__main__":
    unittest.main()
