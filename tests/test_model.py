import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import model
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


class BottomForecastTests(unittest.TestCase):
    def setUp(self):
        self.series = [
            {
                "date": "2011-11-18",
                "price": 2,
                "mvrv": 0.40,
                "mvrvZ": -0.60,
                "wwi": 0.140,
                "realizedPrice": 5,
                "blocks": 144,
                "blockHeight": 150000,
            },
            {
                "date": "2015-01-14",
                "price": 176,
                "mvrv": 0.56,
                "mvrvZ": -0.60,
                "wwi": 0.040,
                "realizedPrice": 312,
                "blocks": 144,
                "blockHeight": 340000,
            },
            {
                "date": "2018-12-15",
                "price": 3185,
                "mvrv": 0.69,
                "mvrvZ": -0.49,
                "wwi": 0.017,
                "realizedPrice": 4613,
                "blocks": 144,
                "blockHeight": 555000,
            },
            {
                "date": "2022-11-09",
                "price": 15758,
                "mvrv": 0.75,
                "mvrvZ": -0.36,
                "wwi": 0.008,
                "realizedPrice": 20901,
                "blocks": 144,
                "blockHeight": 762000,
            },
            {
                "date": "2025-10-01",
                "price": 100000,
                "mvrv": 2.0,
                "mvrvZ": 2.0,
                "wwi": 0.8,
                "realizedPrice": 50000,
                "blocks": 144,
                "blockHeight": 920000,
            },
            {
                "date": "2026-01-31",
                "price": 70000,
                "mvrv": 1.4,
                "mvrvZ": 0.7,
                "wwi": 0.4,
                "realizedPrice": 50000,
                "blocks": 144,
                "blockHeight": 940000,
            },
            {
                "date": "2026-07-30",
                "price": 63627,
                "mvrv": 1.2,
                "mvrvZ": 0.35,
                "wwi": 0.207,
                "realizedPrice": 52865,
                "blocks": 144,
                "blockHeight": 960400,
            },
        ]

    def test_forecast_matches_browser_model_contract(self):
        self.assertTrue(hasattr(model, "bottom_forecast"))

        forecast = model.bottom_forecast(
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
        self.assertAlmostEqual(
            forecast["values"]["nupl"],
            1 - 1 / 0.659,
            places=6,
        )
        self.assertIsNotNone(forecast["values"]["price"])
        self.assertIsNotNone(forecast["values"]["realizedPrice"])

    def test_missing_history_returns_unavailable_values(self):
        self.assertTrue(hasattr(model, "bottom_forecast"))

        forecast = model.bottom_forecast([], {}, None, None)

        self.assertIsNone(forecast["targetDate"])
        self.assertTrue(
            all(value is None for value in forecast["values"].values())
        )


if __name__ == "__main__":
    unittest.main()
