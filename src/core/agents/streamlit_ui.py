"""Small Streamlit client for the FastAPI chat endpoint."""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.request import build_opener, HTTPCookieProcessor
from http.cookiejar import CookieJar
from typing import Any, Callable


AGENT_MODES = {
    "Auto (Knowledge + SQL)": "auto", "Knowledge": "knowledge", "SQL": "sql",
    "Decision Support": "decision_support", "Inventory Dashboard": "dashboard", "Report": "report",
}


def submit_chat(question: str, agent_mode: str, *, metadata: dict | None = None,
                api_url: str | None = None, opener=None, agent_prefix="/api",
                conversation_id: str | None = None) -> dict[str, Any]:
    if agent_mode not in {*AGENT_MODES.values(), "agentic"}:
        raise ValueError("Choose a supported agent mode.")
    payload = {"question": question, "agent_mode": agent_mode, "metadata": metadata or {}}
    if conversation_id:
        payload["conversation_id"] = conversation_id
    request = Request(
        f"{(api_url or os.getenv('API_BASE_URL', 'http://127.0.0.1:8000')).rstrip('/')}{agent_prefix}/chat",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with (opener or urlopen)(request, timeout=135) as response:
            return json.loads(response.read())
    except HTTPError as error:
        raise RuntimeError(f"Backend returned HTTP {error.code}.") from None
    except URLError:
        raise RuntimeError("Could not connect to the FastAPI backend.") from None


def submit_chat_stream(question: str, agent_mode: str, *, metadata: dict | None = None,
                       api_url: str | None = None, opener=None, agent_prefix="/api",
                       conversation_id: str | None = None,
                       on_stage: Callable[[str, str], None] | None = None) -> dict[str, Any]:
    if agent_mode not in {*AGENT_MODES.values(), "agentic"}:
        raise ValueError("Choose a supported agent mode.")
    payload = {"question": question, "agent_mode": agent_mode, "metadata": metadata or {}}
    if conversation_id:
        payload["conversation_id"] = conversation_id
    request = Request(
        f"{(api_url or os.getenv('API_BASE_URL', 'http://127.0.0.1:8000')).rstrip('/')}{agent_prefix}/chat/stream",
        data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with (opener or urlopen)(request, timeout=300) as response:
            event = None
            result = None
            for raw_line in response:
                line = raw_line.decode("utf-8").strip()
                if line.startswith("event:"):
                    event = line[6:].strip()
                elif line.startswith("data:"):
                    data = json.loads(line[5:].strip())
                    if event == "stage" and on_stage:
                        on_stage(data.get("stage", ""), data.get("state", ""))
                    elif event == "result":
                        result = data
                    elif event == "error":
                        raise RuntimeError(data.get("detail", "Agent request failed."))
                elif not line:
                    event = None
            if result is None:
                raise RuntimeError("The agent stream ended before returning a result.")
            return result
    except HTTPError as error:
        raise RuntimeError(f"Backend returned HTTP {error.code}.") from None
    except URLError:
        raise RuntimeError("Could not connect to the FastAPI backend.") from None


def submit_sql_assistant(question: str, *, mode="draft", sql=None, parameters=None,
                         api_url: str | None = None, opener=None) -> dict[str, Any]:
    if mode not in {"draft", "execute"} or (mode == "execute" and not sql):
        raise ValueError("Provide a draft request or the SQL you approved.")
    payload = {"question": question, "mode": mode}
    if sql is not None:
        payload["sql"] = sql
    if parameters is not None:
        payload["parameters"] = parameters
    request = Request(
        f"{(api_url or os.getenv('API_BASE_URL', 'http://127.0.0.1:8000')).rstrip('/')}/api/sql/assistant",
        data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with (opener or urlopen)(request, timeout=135) as response:
            return json.loads(response.read())
    except HTTPError as error:
        try:
            detail = json.loads(error.read()).get("detail", "SQL assistant request failed.")
        except (ValueError, AttributeError):
            detail = "SQL assistant request failed."
        raise RuntimeError(f"HTTP {error.code}: {detail}") from None
    except URLError:
        raise RuntimeError("Could not connect to the FastAPI backend.") from None


class ReportConfirmationRequired(RuntimeError):
    def __init__(self, detail):
        super().__init__('Review the report structure and supported scope before generation.')
        self.detail = detail


class ReportStatus(str):
    """Keep the existing three-value download contract while carrying UI status detail."""
    def __new__(cls, value, summary=None):
        result = super().__new__(cls, value)
        result.summary = summary if isinstance(summary, dict) else {}
        return result


def submit_report(question: str, filename: str | None = None, content: bytes | None = None, *,
                  api_url: str | None = None, opener=None, source_mode="documents", output_format=None,
                  agent_prefix="/api", conversation_id: str | None = None,
                  template_choice=None, accept_supported_scope=False) -> tuple[bytes, str, str]:
    safe_name = os.path.basename(filename) if filename is not None else None
    if filename is not None and (not safe_name or any(char in safe_name for char in ('"', "\r", "\n"))):
        raise ValueError("Choose a valid DOCX or Markdown template filename.")
    extension = os.path.splitext(safe_name)[1].casefold() if safe_name else None
    content_type = {
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".md": "text/markdown",
    }.get(extension)
    if filename is not None and content_type is None:
        raise ValueError("Choose a DOCX or Markdown template.")
    boundary = "----agent" + uuid.uuid4().hex
    fields = {"question": question, "source_mode": source_mode}
    if conversation_id:
        fields['conversation_id'] = conversation_id
    if output_format:
        fields["output_format"] = output_format
    if template_choice:
        fields['template_choice'] = template_choice
    if accept_supported_scope:
        fields['accept_supported_scope'] = 'true'
    parts = [f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode()
             for key, value in fields.items()]
    if safe_name:
        parts.extend((f'--{boundary}\r\nContent-Disposition: form-data; name="template"; filename="{safe_name}"\r\n'
                      f'Content-Type: {content_type}\r\n\r\n'.encode(), content or b"", b"\r\n"))
    parts.append(f"--{boundary}--\r\n".encode())
    body = b"".join(parts)
    request = Request(
        f"{(api_url or os.getenv('API_BASE_URL', 'http://127.0.0.1:8000')).rstrip('/')}{agent_prefix}/report",
        data=body, headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}, method="POST",
    )
    try:
        with (opener or urlopen)(request, timeout=600) as response:
            try:
                summary = json.loads(response.headers.get('X-Report-Summary', '{}'))
            except (ValueError, TypeError):
                summary = {}
            return (response.read(), response.headers.get("Content-Type", content_type or "text/markdown"),
                    ReportStatus(response.headers.get("X-Report-Status", "complete"), summary))
    except HTTPError as error:
        try:
            detail = json.loads(error.read()).get("detail", {})
            if error.code == 409 and isinstance(detail, dict) and detail.get('confirmation_required'):
                raise ReportConfirmationRequired(detail)
            message = "; ".join(detail.get("limitations", [])) if isinstance(detail, dict) else str(detail)
            if isinstance(detail, dict) and detail.get('status') == 'unsupported':
                raise RuntimeError(message) from None
            if isinstance(detail, dict) and detail.get("code") == "clarification_required":
                message = "Clarification needed: " + detail["clarification"]
                raise RuntimeError(message) from None
        except (ValueError, AttributeError):
            message = "Report request failed."
        raise RuntimeError(f"HTTP {error.code}: {message}") from None
    except URLError:
        raise RuntimeError("Could not connect to the FastAPI backend.") from None


def display_result(st: Any, result: Mapping[str, Any], *, key_prefix: str | None = None) -> None:
    metadata = result.get("metadata") or {}
    if metadata.get('context_used'):
        scope = metadata.get('semantic_interpretation') or {}
        temporal = scope.get('time') or {}
        st.caption('Following previous SQL scope. Snapshot: '+str(temporal.get('start') or temporal.get('mode','unknown')))
        filters = scope.get('filters') or []
        if filters:
            st.caption('Filters: '+', '.join(f"{f['field']} {f['operator']} {f['value']}" for f in filters))
    if metadata.get("status"):
        st.caption("Status: " + metadata["status"].replace("_", " ") +
                   (" · evidence fallback" if metadata.get("fallback") else ""))
    st.markdown(result.get("answer", "No answer returned."))
    dashboard = (result.get("data") or {}).get("dashboard")
    if isinstance(dashboard, Mapping) and dashboard.get("outline_id") == "inventory_control":
        _display_inventory_dashboard(st, dashboard, key_prefix=key_prefix)
    else:
        _display_data(st, result.get("data") or {}, key_prefix=key_prefix)
    evidence = result.get("evidence") or []
    if evidence:
        with st.expander("Sources"):
            for item in evidence:
                st.markdown(f"**{item.get('citation_id', '')} · {item.get('source', '')}**")
                if item.get("content"):
                    st.caption(item["content"])
    limitations = result.get("metadata", {}).get("limitations") or []
    for limitation in limitations:
        st.caption(f"Limitation: {limitation}")
    if metadata.get("task_trace"):
        with st.expander("Execution details"):
            st.dataframe(metadata["task_trace"], use_container_width=True, hide_index=True,
                         **({'key':key_prefix+':trace'} if key_prefix else {}))


def _display_inventory_dashboard(st: Any, dashboard: Mapping[str, Any], *, key_prefix: str | None = None) -> None:
    st.subheader(dashboard.get("title", "Inventory Control & Exceptions"))
    st.caption(f"Latest available snapshot: {dashboard.get('snapshot_date', 'unknown')}")
    kpis = dashboard.get("kpis") or {}
    labels = (
        ("SKUs", "sku_count"), ("Stockout rate", "stockout_rate"),
        ("Overstock rate", "overstock_rate"), ("Mean fill rate", "mean_fill_rate"),
        ("Overstock flagged with days of supply", "high_days_of_supply_count"),
    )
    columns = st.columns(len(labels))
    for column, (label, key) in zip(columns, labels):
        value = kpis.get(key)
        if key.endswith("rate"):
            value = f"{float(value):.1f}%" if value is not None else "Unavailable"
        elif key == "mean_fill_rate":
            value = f"{float(value):.1%}" if value is not None else "Unavailable"
        column.metric(label, value if value is not None else "Unavailable")
    stockout = dashboard.get("stockout_by_category") or []
    flags = dashboard.get("inventory_flags") or []
    if stockout:
        st.subheader("Stockout rate by category")
        st.bar_chart(stockout, x="category", y="stockout_rate")
    if flags:
        st.subheader("Inventory flags by category")
        st.bar_chart(flags, x="category", y=[
            "stockout_flag_count", "overstock_flag_count", "both_flags_count",
        ])
    exceptions = dashboard.get("exceptions") or []
    st.subheader("Inventory exceptions")
    if exceptions:
        st.dataframe(exceptions, use_container_width=True, hide_index=True,
                     **({'key':key_prefix+':exceptions'} if key_prefix else {}))
    else:
        st.caption("No flagged inventory exceptions in this snapshot.")


def _display_data(st: Any, value: Any, label: str = "Results", *, key_prefix: str | None = None) -> None:
    if isinstance(value, Mapping):
        sql = value.get("sql") or value.get("attempted_sql")
        if isinstance(sql, str):
            status = value.get("query_status", "executed")
            parameters = json.dumps(value.get("parameters", []), ensure_ascii=False)
            export = f"-- Query status: {status}\n-- Parameters (JSON): {parameters}\n{sql}\n"
            with st.expander(f"SQL query · {status}"):
                st.code(sql, language="sql")
                if value.get("parameters"):
                    st.caption("Parameters: " + parameters)
                st.download_button("Download SQL", export, file_name="query.sql", mime="text/plain",
                                   **({'key':key_prefix+':sql'} if key_prefix else {}))
        rows = value.get("rows")
        if isinstance(rows, list) and rows and all(isinstance(row, Mapping) for row in rows):
            st.subheader(label)
            st.dataframe(rows, use_container_width=True, hide_index=True,
                         **({'key':key_prefix+':rows'} if key_prefix else {}))
        for key, nested in value.items():
            if key != "rows" and isinstance(nested, Mapping):
                _display_data(st, nested, key.title(), key_prefix=key_prefix+':'+key if key_prefix else None)


def reset_conversation(state, *, sign_out=False):
    for key in list(state):
        if key in {'chat_turns','last_result','report_download','conversation_id','report_conversation_id'} or str(key).startswith(('chat_input:','report_','category:')):
            state.pop(key,None)
    if sign_out:
        state.pop('api_opener',None)
        state.pop('agent_mode',None)
        state.pop('login_username',None)
        state.pop('login_password',None)
    else:
        state['conversation_id'] = uuid.uuid4().hex
        state['report_conversation_id'] = uuid.uuid4().hex
        state['chat_turns'] = []


def main() -> None:
    import streamlit as st

    st.set_page_config(page_title="Enterprise Knowledge Agent", page_icon="📊", layout="wide")
    st.title("Enterprise Knowledge Agent")
    st.caption(f"FastAPI backend: {os.getenv('API_BASE_URL', 'http://127.0.0.1:8000')}")
    prefix = os.getenv("API_AGENT_PREFIX", "/api/agents")
    if prefix == "/api/agents" and "api_opener" not in st.session_state:
        with st.form("sign_in"):
            username = st.text_input("Username",key='login_username')
            password = st.text_input("Password", type="password",key='login_password')
            signed_in = st.form_submit_button("Sign in")
        if signed_in:
            opener = build_opener(HTTPCookieProcessor(CookieJar()))
            login_request = Request(
                os.getenv("API_BASE_URL", "http://127.0.0.1:8000").rstrip("/") + "/api/auth/login",
                data=json.dumps({"username": username, "password": password}).encode(),
                headers={"Content-Type": "application/json"}, method="POST")
            try:
                with opener.open(login_request, timeout=30) as response:
                    response.read()
                reset_conversation(st.session_state)
                st.session_state["api_opener"] = opener
                st.rerun()
            except (HTTPError, URLError):
                st.error("Sign-in failed. Check your account and backend connection.")
        st.stop()
    opener = st.session_state["api_opener"].open if "api_opener" in st.session_state else None
    if opener and st.button("Sign out",key='sign_out'):
        reset_conversation(st.session_state,sign_out=True)
        st.rerun()
    if "conversation_id" not in st.session_state:
        st.session_state["conversation_id"] = uuid.uuid4().hex
    if "report_conversation_id" not in st.session_state:
        st.session_state["report_conversation_id"] = uuid.uuid4().hex
    st.session_state.setdefault('chat_turns',[])
    if st.button("New conversation",key='new_conversation'):
        reset_conversation(st.session_state)
        st.rerun()
    if st.session_state.get('agent_mode') not in AGENT_MODES:
        st.session_state.pop('agent_mode', None)
    mode_label = st.selectbox("Agent", list(AGENT_MODES),key='agent_mode')
    is_report = AGENT_MODES[mode_label] == "report"
    report_id = st.session_state['report_conversation_id']
    question = st.text_area('Report question',height=100,key='report_question:'+report_id) if is_report else ''
    report_template = st.file_uploader("Report template (optional DOCX or Markdown)", type=["docx", "md"],key='report_template:'+report_id) if is_report else None
    source_mode = st.selectbox("Report sources", ["orchestrated", "documents", "analytics"],
        format_func=lambda mode: {'orchestrated': 'Auto (Knowledge + SQL)',
                                  'documents': 'Documents only', 'analytics': 'Analytics only'}[mode],key='report_source:'+report_id) if is_report else "documents"
    output_format = st.selectbox("Output format", ["markdown", "docx"],key='report_format:'+report_id) if is_report and report_template is None else None
    category = st.text_input("Inventory category (optional)",key='category:'+st.session_state['conversation_id']) if AGENT_MODES[mode_label] == "dashboard" else ""
    confirmation_key = 'report_confirmation:'+report_id
    report_inputs = (question, report_template.name if report_template else None,
                     report_template.getvalue() if report_template else None, source_mode, output_format)
    pending = st.session_state.get(confirmation_key)
    if pending and pending['inputs'] != report_inputs:
        st.session_state.pop(confirmation_key, None)
        pending = None
    template_choice, accept_scope, confirmed = None, False, False
    if is_report and pending:
        detail = pending['detail']
        st.warning('Review the report structure and supported scope before generation.')
        for reason in detail.get('mismatch_reasons', []) + detail.get('unsupported_requirements', []):
            st.write(reason)
        st.write('Suggested sections: '+ '; '.join(s['heading'] for s in detail.get('suggested_structure', [])))
        if detail.get('template_decision_required'):
            label = st.radio('Report structure', ['Use suggested structure', 'Continue with uploaded template'], key='report_choice:'+report_id)
            template_choice = 'suggested' if label == 'Use suggested structure' else 'uploaded'
        accept_scope = bool(detail.get('scope_decision_required'))
        confirmed = st.button('Generate supported report' if accept_scope else 'Generate with selected structure', key='confirm_report:'+report_id)
        if st.button('Cancel report', key='cancel_report:'+report_id):
            st.session_state.pop(confirmation_key, None)
            st.rerun()
    generate = st.button("Generate report", type="primary", disabled=not question.strip() or bool(pending)) if is_report else False
    if is_report and (generate or confirmed):
        st.session_state.pop("report_download", None)
        report_client = st.session_state.get('api_opener')
        try:
            with st.spinner("Generating report…"):
                payload, content_type, status = submit_report(
                    question.strip(), report_template.name if report_template else None,
                    report_template.getvalue() if report_template else None,
                    source_mode=source_mode, output_format=output_format, opener=opener, agent_prefix=prefix,
                    conversation_id=st.session_state['report_conversation_id'],
                    template_choice=template_choice, accept_supported_scope=accept_scope if confirmed else False)
            if (st.session_state.get('report_conversation_id') == report_id
                    and st.session_state.get('api_opener') is report_client):
                st.session_state["report_download"] = (payload, content_type, status)
                st.session_state.pop(confirmation_key, None)
        except ReportConfirmationRequired as error:
            st.session_state[confirmation_key] = {'inputs': report_inputs, 'detail': error.detail}
            st.rerun()
        except (RuntimeError, ValueError) as error:
            st.error(str(error))
    if is_report and "report_download" in st.session_state:
        payload, content_type, status = st.session_state["report_download"]
        if status == "partial":
            st.warning("Partial report: some sections or sources are unavailable. Review the limitations in the report.")
        else:
            st.success("Report generated. Review the verification scope and sources before use.")
        summary = getattr(status, 'summary', {})
        if summary:
            st.caption(f"Sections: {summary.get('complete', 0)} complete, {summary.get('unavailable', 0)} unavailable, {summary.get('failed', 0)} failed. "
                       f"Evidence items omitted from narrative: {summary.get('omitted_from_narrative', 0)}; review detail tables and coverage.")
            for reason in summary.get('reasons', []):
                st.write(reason)
        extension = ".docx" if "wordprocessingml" in content_type else ".md"
        st.download_button("Download report", payload, file_name=f"report{extension}", mime=content_type,key='report_download:'+report_id)
        if extension == ".md":
            with st.expander("Report preview and limitations", expanded=True):
                st.markdown(payload.decode("utf-8"))
    if is_report:
        return
    st.caption('This session shows the latest 20 exchanges. Inventory SQL follow-up context expires after 30 minutes of inactivity and is separate from other modes.')
    for turn in st.session_state['chat_turns']:
        with st.chat_message('user'):
            st.caption(turn['mode'])
            st.markdown(turn['question'])
        with st.chat_message('assistant'):
            if 'error' in turn:
                st.error(turn['error'])
            else:
                display_result(st,turn['result'],key_prefix=turn['id'])
    question = st.chat_input('Ask a question',max_chars=2000,key='chat_input:'+st.session_state['conversation_id'])
    if question and question.strip():
        conversation_id = st.session_state['conversation_id']
        authenticated_client = st.session_state.get('api_opener')
        turn = {'id':uuid.uuid4().hex,'question':question.strip(),'mode':mode_label}
        with st.chat_message('user'):
            st.caption(mode_label)
            st.markdown(question.strip())
        try:
            with st.chat_message('assistant'):
                metadata = {"category": category.strip()} if category.strip() else None
                with st.status('Đang bắt đầu xử lý…', expanded=True) as progress:
                    stage_labels = {
                        'routing': 'Phân loại câu hỏi',
                        'schema_discovery': 'Khám phá cấu trúc database',
                        'metric_retrieval': 'Tra cứu định nghĩa metric trong RAG',
                        'metric_interpretation': 'Diễn giải yêu cầu theo metric',
                        'sql_planning': 'Tạo và kiểm tra câu truy vấn',
                        'sql_execution': 'Chạy truy vấn trên database',
                        'agent_workflow': 'Xử lý yêu cầu',
                        'answer_synthesis': 'Tổng hợp câu trả lời',
                    }
                    def show_stage(stage, state):
                        label = stage_labels.get(stage, stage.replace('_', ' ').capitalize())
                        icon = {'started': '⏳', 'completed': '✓', 'failed': '⚠'}.get(state, '·')
                        progress.write(f'{icon} {label}')
                    turn['result'] = submit_chat_stream(question.strip(),AGENT_MODES[mode_label],metadata=metadata,
                        opener=opener,agent_prefix=prefix,conversation_id=conversation_id,on_stage=show_stage)
                    progress.update(label='Đã hoàn tất', state='complete')
        except (RuntimeError,ValueError) as error:
            turn['error'] = str(error)
        if (st.session_state.get('conversation_id') == conversation_id
                and st.session_state.get('api_opener') is authenticated_client):
            st.session_state['chat_turns'] = (st.session_state['chat_turns']+[turn])[-20:]
        st.rerun()


if __name__ == "__main__":
    main()
