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
from typing import Any


AGENT_MODES = {
    "Auto (Knowledge + SQL)": "auto", "Knowledge": "knowledge", "SQL": "sql",
    "Inventory Dashboard": "dashboard", "Report": "report",
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


def submit_report(question: str, filename: str | None = None, content: bytes | None = None, *,
                  api_url: str | None = None, opener=None, source_mode="documents", output_format=None,
                  agent_prefix="/api", conversation_id: str | None = None) -> tuple[bytes, str, str]:
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
            return (response.read(), response.headers.get("Content-Type", content_type or "text/markdown"),
                    response.headers.get("X-Report-Status", "complete"))
    except HTTPError as error:
        try:
            detail = json.loads(error.read()).get("detail", {})
            message = "; ".join(detail.get("limitations", [])) if isinstance(detail, dict) else str(detail)
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
    if is_report and st.button("Generate report", type="primary",
                               disabled=not question.strip()):
        st.session_state.pop("report_download", None)
        report_client = st.session_state.get('api_opener')
        try:
            with st.spinner("Generating report…"):
                payload, content_type, status = submit_report(
                    question.strip(), report_template.name if report_template else None,
                    report_template.getvalue() if report_template else None,
                    source_mode=source_mode, output_format=output_format, opener=opener, agent_prefix=prefix,
                    conversation_id=st.session_state['report_conversation_id'])
            if (st.session_state.get('report_conversation_id') == report_id
                    and st.session_state.get('api_opener') is report_client):
                st.session_state["report_download"] = (payload, content_type, status)
        except (RuntimeError, ValueError) as error:
            st.error(str(error))
    if is_report and "report_download" in st.session_state:
        payload, content_type, status = st.session_state["report_download"]
        if status == "partial":
            st.warning("Partial report: some sections or sources are unavailable. Review the limitations in the report.")
        else:
            st.success("Report generated. Review the verification scope and sources before use.")
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
            with st.chat_message('assistant'), st.spinner('Working...'):
                metadata = {"category": category.strip()} if category.strip() else None
                turn['result'] = submit_chat(question.strip(),AGENT_MODES[mode_label],metadata=metadata,
                    opener=opener,agent_prefix=prefix,conversation_id=conversation_id)
        except (RuntimeError,ValueError) as error:
            turn['error'] = str(error)
        if (st.session_state.get('conversation_id') == conversation_id
                and st.session_state.get('api_opener') is authenticated_client):
            st.session_state['chat_turns'] = (st.session_state['chat_turns']+[turn])[-20:]
        st.rerun()


if __name__ == "__main__":
    main()
