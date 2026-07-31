import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class FrontendForecastContractTests(unittest.TestCase):
    def test_bottom_table_prefers_persisted_forecast_with_legacy_fallback(self):
        source = (ROOT / "assets" / "js" / "app.js").read_text(
            encoding="utf-8"
        )

        self.assertIn("state.data.assessment?.bottomForecast", source)
        self.assertIn(
            "persistedForecast?.values"
            " ? persistedForecast"
            " : expectedBottomForecast(bottoms)",
            source,
        )


if __name__ == "__main__":
    unittest.main()
