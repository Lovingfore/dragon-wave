import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from model import composite_risk, outlook_7d, risk_state, wwi_for_height


class WolfyWaveTests(unittest.TestCase):
    def test_halving_is_midpoint(self):
        for height in (210000, 420000, 630000, 840000):
            self.assertAlmostEqual(wwi_for_height(height)["value"], 0.5, places=8)

    def test_wave_stays_bounded(self):
        for height in range(0, 1000000, 7919):
            value = wwi_for_height(height)["value"]
            self.assertGreaterEqual(value, 0.0)
            self.assertLessEqual(value, 1.0)


class RiskModelTests(unittest.TestCase):
    def test_incomplete_market_data_has_no_composite_score(self):
        score, components = composite_risk({"price": 60000, "wwi": 0.4})
        self.assertIsNone(score)
        self.assertIsNotNone(components["wwi"])

    def test_hot_market_scores_high(self):
        values = {
            "price": 240000,
            "realizedPrice": 65000,
            "nupl": 0.78,
            "mvrv": 4.0,
            "mvrvZ": 8.0,
            "wwi": 0.95,
        }
        score, _ = composite_risk(values)
        self.assertGreaterEqual(score, 85)
        self.assertEqual(risk_state(score)["key"], "near_top")

    def test_cold_market_scores_low(self):
        values = {
            "price": 15000,
            "realizedPrice": 22000,
            "nupl": -0.2,
            "mvrv": 0.7,
            "mvrvZ": -0.7,
            "wwi": 0.02,
        }
        score, _ = composite_risk(values)
        self.assertLessEqual(score, 15)
        self.assertEqual(risk_state(score)["key"], "near_bottom")

    def test_neutral_outlook(self):
        outlook = outlook_7d(51, [49, 50, 50, 51, 50, 51, 51], 0.5)
        self.assertEqual(outlook["key"], "neutral")


if __name__ == "__main__":
    unittest.main()
