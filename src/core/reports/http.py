"""One report download/status contract for both FastAPI entry points."""

from io import BytesIO

from fastapi import HTTPException
from fastapi.responses import StreamingResponse


def report_response(result, payload, media_type):
    if result.metadata.get("clarification_required"):
        raise HTTPException(422, detail={"status": "clarification_required", "code": "clarification_required",
                                         "clarification": result.answer, "limitations": [result.answer]})
    status = result.metadata.get("status", "complete" if result.metadata.get("ok", True) else "partial")
    if status == "complete" and result.metadata.get("ok") is False:
        status = "partial"
    if status == "failed" or not payload:
        failure_type = result.metadata.get("failure_type", "validation_failed")
        code = 503 if failure_type in {"source_unavailable", "provider_unavailable"} else 422
        raise HTTPException(code, detail={"status": "failed", "code": failure_type,
                                         "limitations": result.metadata.get("limitations", [])})
    extension = ".docx" if media_type.startswith("application/vnd.openxmlformats") else ".md"
    return StreamingResponse(BytesIO(payload), media_type=media_type, headers={
        "Content-Disposition": f'attachment; filename="report{extension}"',
        "X-Report-Status": status,
        "Access-Control-Expose-Headers": "X-Report-Status, Content-Disposition",
    })
