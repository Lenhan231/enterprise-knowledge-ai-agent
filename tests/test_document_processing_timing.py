import unittest
from types import SimpleNamespace

from docling.datamodel.settings import DebugSettings, scoped, settings

from document_processing.docling_adapter.processor import _summarize_docling_timings


class DoclingTimingSummaryTest(unittest.TestCase):
    def test_pipeline_profile_setting_is_scoped_and_restored(self):
        original = settings.debug.profile_pipeline_timings

        with scoped(debug=DebugSettings(profile_pipeline_timings=True)):
            self.assertTrue(settings.debug.profile_pipeline_timings)

        self.assertEqual(settings.debug.profile_pipeline_timings, original)

    def test_summarizes_stage_intervals_without_combining_overlapping_stages(self):
        timings = {
            "layout": SimpleNamespace(
                scope=SimpleNamespace(value="page"), count=2, times=[0.25, 0.5]
            ),
            "ocr": SimpleNamespace(scope="page", count=1, times=[1.25]),
            "unused": SimpleNamespace(scope="page", count=0, times=[]),
        }

        summary = _summarize_docling_timings(timings)

        self.assertEqual(summary, {
            "layout": {
                "scope": "page", "count": 2, "total_ms": 750.0,
                "intervals_ms": [250.0, 500.0],
            },
            "ocr": {
                "scope": "page", "count": 1, "total_ms": 1250.0,
                "intervals_ms": [1250.0],
            },
        })


if __name__ == "__main__":
    unittest.main()
