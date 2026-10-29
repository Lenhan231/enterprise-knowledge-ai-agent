import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from core.models.agents import Evidence
from core.reports.grounding import validate_claim
from core.reports.sources import authorize_sources


class GroundingTest(unittest.TestCase):
    def test_unknown_missing_and_unsupported_citations_fail(self):
        source = [Evidence(citation_id="S1", source_type="document", source="a", content="Revenue 100 in 2024; margin 25%.")]
        for text in ("Revenue 999 [S1]", "Revenue 100 [S2]", "Revenue 100", "Margin 25 [S1]", "Revenue 1e6 [S1]"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                validate_claim(text, source)
        validate_claim("Revenue 100 in 2024 [S1]", source)
        validate_claim("Margin 25% [S1]", source)

    def test_ambiguous_locale_numbers_are_not_certified(self):
        source = [Evidence(citation_id="S1", source_type="document", source="a", content="Revenue 1,000")]
        with self.assertRaises(ValueError):
            validate_claim("Revenue 1,000 [S1]", source)


if __name__ == "__main__":
    unittest.main()
