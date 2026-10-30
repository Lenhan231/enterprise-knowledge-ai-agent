"""Reuse loaded Docling pipelines across documents with the same options."""

from collections import OrderedDict
from threading import Lock

_converters = OrderedDict()
_lock = Lock()


def get_converter(options):
    from docling.datamodel.base_models import InputFormat
    from docling.document_converter import DocumentConverter, ImageFormatOption, PdfFormatOption

    key = (type(options.ocr_options), options.model_dump_json())
    with _lock:
        if key not in _converters:
            _converters[key] = DocumentConverter(format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=options),
                InputFormat.IMAGE: ImageFormatOption(pipeline_options=options),
            })
            # Bound retained model sets when callers supply custom parser options.
            if len(_converters) > 4:
                _converters.popitem(last=False)
        _converters.move_to_end(key)
        return _converters[key]
