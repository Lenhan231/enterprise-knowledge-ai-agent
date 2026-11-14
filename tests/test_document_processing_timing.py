import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from docling.datamodel.settings import DebugSettings, scoped, settings
from docling.datamodel.pipeline_options import TableFormerMode

from document_processing.docling_adapter.processor import DoclingProcessor
from document_processing.docling_adapter.processor import _summarize_docling_timings


class DoclingTimingSummaryTest(unittest.TestCase):
    def test_tableformer_fast_mode_is_explicit_and_accurate_stays_default(self):
        accurate = DoclingProcessor({})._pipeline_options(True, False, False)
        fast = DoclingProcessor({"docling_table_mode": "fast"})._pipeline_options(True, False, False)

        self.assertEqual(accurate.table_structure_options.mode, TableFormerMode.ACCURATE)
        self.assertEqual(fast.table_structure_options.mode, TableFormerMode.FAST)

    def test_tableformer_mode_rejects_unknown_values(self):
        with self.assertRaisesRegex(ValueError, "docling_table_mode"):
            DoclingProcessor({"docling_table_mode": "unknown"})._pipeline_options(True, False, False)

    def test_preload_warms_page_orientation_after_pipeline_initialization(self):
        processor = DoclingProcessor({})
        processor._pipeline_options = Mock(return_value=object())
        converter = Mock()
        converter.initialized_pipelines = {}

        with (
            patch("document_processing.docling_adapter.processor.get_converter", return_value=converter) as get_converter,
            patch("document_processing.docling_adapter.orientation.preload_paddle_page_orientation_model") as warm_orientation,
        ):
            processor.preload()

        self.assertEqual(get_converter.call_count, 3)
        self.assertEqual(converter.initialize_pipeline.call_count, 3)
        warm_orientation.assert_called_once_with()

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
