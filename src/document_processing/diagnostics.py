"""Structured errors for document processing stages."""

from contextlib import contextmanager
import json
from urllib.error import HTTPError


class PageLimitExceeded(ValueError):
    def __init__(self, page_count: int, page_limit: int, *, count_unit: str = "pages"):
        self.page_count = page_count
        self.page_limit = page_limit
        self.count_unit = count_unit
        unit = count_unit.removesuffix("s")
        super().__init__(f"File exceeds the {page_limit}-{unit} limit ({page_count} {count_unit})")


def document_log_context(metadata: dict, **details) -> dict:
    references = {
        key: metadata[key]
        for key in ("document_id", "invoice_id", "source_sha256")
        if isinstance(metadata.get(key), (str, int))
    }
    return {**references, **details}


def log_component_error(logger, component: str, **details) -> None:
    logger.error(
        "DOCUMENT_PROCESS_COMPONENT_ERROR %s",
        json.dumps({"component": component, **details}, separators=(",", ":")),
    )


@contextmanager
def component_errors(logger, component: str, **context):
    try:
        yield
    except Exception as error:
        details = {"error_type": type(error).__name__}
        if error.__cause__ is not None:
            details["cause_type"] = type(error.__cause__).__name__
        if isinstance(error, PageLimitExceeded):
            details.update(
                error_code="page_limit_exceeded",
                page_count=error.page_count,
                page_limit=error.page_limit,
                count_unit=error.count_unit,
            )
        status_code = getattr(error, "status_code", None)
        if isinstance(error.__cause__, HTTPError):
            status_code = error.__cause__.code
        if isinstance(status_code, int):
            details["status_code"] = status_code
        log_component_error(logger, component, **context, **details)
        raise
