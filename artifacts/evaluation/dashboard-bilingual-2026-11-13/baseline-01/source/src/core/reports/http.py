"""One report download/status contract for both FastAPI entry points."""

from io import BytesIO
import json

from fastapi import HTTPException
from fastapi.responses import StreamingResponse


def report_response(result, payload, media_type):
    if result.metadata.get('confirmation_required'):
        raise HTTPException(409, detail={key: result.metadata[key] for key in (
            'status', 'confirmation_required', 'mismatch_reasons', 'unsupported_requirements',
            'suggested_structure', 'template_decision_required', 'scope_decision_required')})
    if result.metadata.get('status') == 'unsupported':
        raise HTTPException(422, detail={'status': 'unsupported', 'code': 'unsupported',
                                        'limitations': result.metadata.get('limitations', [])})
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
                                         'error_code': result.metadata.get('error_code', failure_type),
                                         "limitations": result.metadata.get("limitations", [])})
    extension = ".docx" if media_type.startswith("application/vnd.openxmlformats") else ".md"
    sections = list(result.metadata.get('sections', {}).values())
    summary = {
        'complete': sections.count('complete'), 'failed': sections.count('failed'),
        'unavailable': sections.count('unavailable'),
        'omitted_from_narrative': sum(value.get('facts_omitted', 0)+value.get('documents_omitted', 0)
                                      for value in result.metadata.get('narrative_coverage', {}).values()),
        'reasons': sorted({str(value).split(';')[0].replace('_', ' ')[:120]
                           for value in result.metadata.get('issues', {}).values()})[:8],
    }
    return StreamingResponse(BytesIO(payload), media_type=media_type, headers={
        "Content-Disposition": f'attachment; filename="report{extension}"',
        "X-Report-Status": status,
        'X-Report-Summary': json.dumps(summary, separators=(',', ':')),
        "Access-Control-Expose-Headers": "X-Report-Status, X-Report-Summary, Content-Disposition",
    })
