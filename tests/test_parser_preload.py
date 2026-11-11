import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.services.runtime import lifespan
from document_processing.docling_adapter.processor import DoclingProcessor


class ParserStartupTest(unittest.IsolatedAsyncioTestCase):
    async def test_models_are_loaded_before_startup_completes(self):
        with patch.dict(os.environ, {"SERVICE_KIND": "document-processing", "INTERNAL_SERVICE_TOKEN": "test"}), \
                patch.object(DoclingProcessor, "preload", create=True) as preload:
            async with lifespan(FastAPI()):
                preload.assert_called_once_with()

    async def test_model_failure_blocks_startup(self):
        with patch.dict(os.environ, {"SERVICE_KIND": "document-processing", "INTERNAL_SERVICE_TOKEN": "test"}), \
                patch.object(DoclingProcessor, "preload", create=True, side_effect=RuntimeError("model unavailable")):
            with self.assertRaisesRegex(RuntimeError, "model unavailable"):
                async with lifespan(FastAPI()):
                    self.fail("Accepted requests without parser models")


class ParserPreloadTest(unittest.TestCase):
    def test_preload_initializes_scanned_and_native_routes(self):
        processor = DoclingProcessor({})
        with patch.object(processor, "_pipeline_options", create=True) as options, \
                patch("document_processing.docling_adapter.processor.get_converter", create=True) as converter:
            processor.preload()
            self.assertEqual(options.call_args_list, [
                unittest.mock.call(True, False, False),
                unittest.mock.call(False, False, False),
                unittest.mock.call(False, True, True),
            ])
            self.assertEqual(converter.return_value.initialize_pipeline.call_count, 3)

    def test_converter_is_reused_for_equivalent_options(self):
        from document_processing.docling_adapter.converters import get_converter, _converters
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        _converters.clear()
        self.addCleanup(_converters.clear)
        with patch("docling.document_converter.DocumentConverter") as build:
            first = get_converter(PdfPipelineOptions())
            second = get_converter(PdfPipelineOptions())
            self.assertIs(first, second)
            build.assert_called_once()

    def test_custom_options_do_not_retain_unbounded_model_sets(self):
        from document_processing.docling_adapter.converters import get_converter, _converters
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        _converters.clear()
        self.addCleanup(_converters.clear)
        with patch("docling.document_converter.DocumentConverter") as build:
            for scale in range(1, 7):
                get_converter(PdfPipelineOptions(images_scale=float(scale)))
            self.assertEqual(len(_converters), 4)
            get_converter(PdfPipelineOptions(images_scale=1.0))
            self.assertEqual(build.call_count, 7)


if __name__ == "__main__":
    unittest.main()
