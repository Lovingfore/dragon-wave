import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import notify


class EmailRenderingTests(unittest.TestCase):
    def setUp(self):
        self.data = {
            "metadata": {
                "generatedAt": "2026-07-31T15:00:35Z",
                "dailyDataDate": "2026-07-30",
            },
            "current": {
                "price": {
                    "value": 63627.395,
                    "change1d": -0.43,
                    "change7d": -2.25,
                },
                "nupl": {
                    "value": 0.169143,
                    "change1d": -2.10,
                    "change7d": -9.85,
                },
                "realizedPrice": {
                    "value": 52865.228,
                    "change1d": 0.002,
                    "change7d": -0.03,
                },
                "mvrv": {
                    "value": 1.2035,
                    "change1d": -0.44,
                    "change7d": -2.22,
                },
                "mvrvZ": {
                    "value": 0.3549,
                    "change1d": -2.53,
                    "change7d": -11.92,
                },
                "wwi": {
                    "value": 0.2066,
                    "change1d": -2.03,
                    "change7d": -8.98,
                },
            },
            "assessment": {
                "riskScore": 19.6,
                "outlook7d": {
                    "label": "未来七日继续向底部区间靠近",
                    "detail": "尚未确认到达底部，但风险分位正在下降。",
                },
                "bottomForecast": {
                    "asOf": "2026-07-30",
                    "targetDate": "2026-10-16",
                    "values": {
                        "price": 34269.4,
                        "nupl": -0.5065,
                        "realizedPrice": 51627.3,
                        "mvrv": 0.6638,
                        "mvrvZ": -0.4704,
                        "wwi": 0.0314,
                        "riskScore": 0.7,
                    },
                },
            },
        }
        self.state = {
            "key": "bottom_watch",
            "label": "底部区间观察",
            "tone": "info",
        }

    def render(self, data=None):
        return notify.build_email(data or self.data, self.state, "test")

    def metrics_table(self, html_body):
        root = ElementTree.fromstring(html_body[html_body.index("<html") :])
        table = root.find(".//table[@data-role='metrics']")
        self.assertIsNotNone(table)
        return root, table

    def test_dark_metric_table_has_five_aligned_bordered_columns(self):
        _, text_body, html_body = self.render()
        root, table = self.metrics_table(html_body)
        headers = [
            "".join(cell.itertext()).strip()
            for cell in table.findall("./thead/tr/th")
        ]

        self.assertEqual(
            headers,
            ["指标", "最新值", "预测底部值", "1 日", "7 日"],
        )
        self.assertEqual(root.find("body").attrib["bgcolor"], "#0e1113")
        self.assertIn("#181c1f", html_body)
        self.assertIn("#465158", html_body)
        self.assertIn("#312c20", html_body)
        self.assertIn("$34,269", html_body)
        self.assertIn("预测底部值", text_body)

        rows = table.findall("./tbody/tr")
        self.assertEqual(len(rows), 6)
        for row in rows:
            cells = row.findall("td")
            self.assertEqual(len(cells), 5)
            self.assertEqual(cells[0].attrib["align"], "left")
            self.assertTrue(
                all(cell.attrib["align"] == "right" for cell in cells[1:])
            )
            self.assertTrue(
                all(
                    "border:1px solid #465158" in cell.attrib["style"]
                    for cell in cells
                )
            )
            self.assertEqual(cells[2].attrib["bgcolor"], "#312c20")

    def test_missing_forecast_renders_placeholders_without_failing(self):
        data = {
            **self.data,
            "assessment": {
                key: value
                for key, value in self.data["assessment"].items()
                if key != "bottomForecast"
            },
        }

        _, text_body, html_body = self.render(data)
        _, table = self.metrics_table(html_body)
        predicted = [
            row.findall("td")[2].text for row in table.findall("./tbody/tr")
        ]

        self.assertEqual(predicted, ["--"] * 6)
        self.assertGreaterEqual(text_body.count("--"), 6)

    def test_dynamic_text_and_labels_are_html_escaped(self):
        unsafe = '<script>alert("x")</script>&'
        data = {
            **self.data,
            "assessment": {
                **self.data["assessment"],
                "outlook7d": {
                    "label": unsafe,
                    "detail": unsafe,
                },
            },
        }

        with patch.dict(notify.LABELS, {"price": unsafe}, clear=False):
            _, _, html_body = self.render(data)

        root, _ = self.metrics_table(html_body)
        self.assertIsNone(root.find(".//script"))
        self.assertGreaterEqual(
            "".join(root.itertext()).count(unsafe),
            3,
        )

    def test_mobile_styles_keep_all_columns_visible(self):
        _, _, html_body = self.render()

        self.assertIn("@media only screen and (max-width:520px)", html_body)
        self.assertNotIn("display:none", html_body)


if __name__ == "__main__":
    unittest.main()
