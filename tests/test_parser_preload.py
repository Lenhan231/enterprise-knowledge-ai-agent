import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.services.runtime import lifespan
from document_processing.docling_adapter.processor import DoclingProcessor
from document_processing.docling_adapter.layout_model import PPDocLayoutModel


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
    def test_layout_warmup_uses_a_dummy_page_without_changing_model_settings(self):
        layout = PPDocLayoutModel.__new__(PPDocLayoutModel)
        layout.options = SimpleNamespace(score_threshold=0.25)
        layout.model = SimpleNamespace(predict=unittest.mock.Mock(return_value=iter([object()])))

        layout.warmup()

        kwargs = layout.model.predict.call_args.kwargs
        self.assertEqual(kwargs["input"].shape, (800, 800, 3))
        self.assertEqual(kwargs["input"].max(), 255)
        self.assertEqual(kwargs["threshold"], 0.25)
        self.assertEqual(kwargs["batch_size"], 1)
        self.assertTrue(kwargs["layout_nms"])

    def test_preload_initializes_scanned_and_native_routes(self):
        processor = DoclingProcessor({})
        converter = unittest.mock.Mock()
        converter.initialized_pipelines = {}
        with patch.object(processor, "_pipeline_options", create=True) as options, \
                patch("document_processing.docling_adapter.processor.get_converter", return_value=converter):
            processor.preload()
            self.assertEqual(options.call_args_list, [
                unittest.mock.call(True, False, False),
                unittest.mock.call(False, False, False),
                unittest.mock.call(False, True, True),
                unittest.mock.call(True, False, False, table_mode="fast"),
            ])
            self.assertEqual(converter.initialize_pipeline.call_count, 4)

    def test_preload_warms_accurate_and_fast_invoice_layout_models(self):
        processor = DoclingProcessor({})
        processor._pipeline_options = unittest.mock.Mock(return_value=object())
        warmups = [unittest.mock.Mock() for _ in range(4)]
        converters = [unittest.mock.Mock() for _ in range(4)]
        for converter, warmup in zip(converters, warmups):
            converter.initialized_pipelines = {
                "pdf": SimpleNamespace(layout_model=SimpleNamespace(warmup=warmup))
            }

        with (
            patch("document_processing.docling_adapter.processor.get_converter", side_effect=converters),
            patch("document_processing.docling_adapter.orientation.preload_paddle_page_orientation_model"),
            patch("document_processing.docling_adapter.orientation.preload_paddle_textline_orientation_model") as textline_preload,
        ):
            processor.preload()

        for warmup in (warmups[0], warmups[3]):
            warmup.assert_called_once_with()
        for warmup in (warmups[1], warmups[2]):
            warmup.assert_not_called()
        textline_preload.assert_called_once_with()
        for converter in converters:
            converter.initialize_pipeline.assert_called_once()

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

    def test_converter_cache_distinguishes_custom_ocr_options(self):
        from document_processing.docling_adapter.converters import get_converter, _converters
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from document_processing.docling_adapter.scanned.vietocr import VietOcrOptions
        _converters.clear()
        self.addCleanup(_converters.clear)

        def options(batch_size):
            return PdfPipelineOptions(
                ocr_options=VietOcrOptions(recognition_batch_size=batch_size)
            )

        with patch("docling.document_converter.DocumentConverter") as build:
            get_converter(options(16))
            get_converter(options(32))
            get_converter(options(32))
            self.assertEqual(build.call_count, 2)

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
