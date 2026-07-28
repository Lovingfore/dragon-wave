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


if __name__ == "__main__":
    unittest.main()

