import unittest

from screen_guard import DetectionResult, normalize_text, positive_float, positive_int


class ScreenGuardHelpersTests(unittest.TestCase):
    def test_normalize_text(self):
        self.assertEqual(normalize_text("  Buy   NOW\n"), "buy now")

    def test_total_score(self):
        result = DetectionResult(intrusive_ad_score=0.5, adult_score=0.25, ocr_hits=["porn", "casino"])
        self.assertAlmostEqual(result.total_score, 1.45)

    def test_positive_float(self):
        self.assertEqual(positive_float("1.5"), 1.5)
        with self.assertRaises(Exception):
            positive_float("0")

    def test_positive_int(self):
        self.assertEqual(positive_int("3"), 3)
        with self.assertRaises(Exception):
            positive_int("-1")


if __name__ == "__main__":
    unittest.main()
