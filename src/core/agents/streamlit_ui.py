"""Small Streamlit client for the FastAPI chat endpoint."""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from typing import Any


AGENT_MODES = {
    "Knowledge": "knowledge", "SQL": "sql", "Inventory Dashboard": "dashboard",
    "Report": "report", "Agentic": "agentic",
}


def submit_chat(question: str, agent_mode: str, *, metadata: dict | None = None,
                api_url: str | None = None, opener=None) -> dict[str, Any]:
    if agent_mode not in AGENT_MODES.values():
        raise ValueError("Choose a supported agent mode.")
    request = Request(
        f"{(api_url or os.getenv('API_BASE_URL', 'http://127.0.0.1:8000')).rstrip('/')}/api/chat",
        data=json.dumps({"question": question, "agent_mode": agent_mode,
                         "metadata": metadata or {}}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with (opener or urlopen)(request, timeout=90) as response:
            return json.loads(response.read())
    except HTTPError as error:
        raise RuntimeError(f"Backend returned HTTP {error.code}.") from None
    except URLError:
        raise RuntimeError("Could not connect to the FastAPI backend.") from None


def submit_report(question: str, filename: str, content: bytes, *, api_url: str | None = None,
                  opener=None) -> tuple[bytes, str]:
    safe_name = os.path.basename(filename)
    if not safe_name or any(char in safe_name for char in ('"', "\r", "\n")):
        raise ValueError("Choose a valid DOCX or Markdown template filename.")
    extension = os.path.splitext(safe_name)[1].casefold()
    content_type = {
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".md": "text/markdown",
    }.get(extension)
    if content_type is None:
        raise ValueError("Choose a DOCX or Markdown template.")
    boundary = "----agent" + uuid.uuid4().hex
    body = b"".join((
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"question\"\r\n\r\n{question}\r\n".encode(),
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"template\"; filename=\"{safe_name}\"\r\n"
        f"Content-Type: {content_type}\r\n\r\n".encode(),
        content,
        f"\r\n--{boundary}--\r\n".encode(),
    ))
    request = Request(
        f"{(api_url or os.getenv('API_BASE_URL', 'http://127.0.0.1:8000')).rstrip('/')}/api/report",
        data=body, headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}, method="POST",
    )
    try:
        with (opener or urlopen)(request, timeout=180) as response:
            return response.read(), response.headers.get("Content-Type", content_type)
    except HTTPError as error:
        raise RuntimeError(f"Backend returned HTTP {error.code}.") from None
    except URLError:
        raise RuntimeError("Could not connect to the FastAPI backend.") from None


def display_result(st: Any, result: Mapping[str, Any]) -> None:
    st.markdown(result.get("answer", "No answer returned."))
    dashboard = (result.get("data") or {}).get("dashboard")
    if isinstance(dashboard, Mapping) and dashboard.get("outline_id") == "inventory_control":
        _display_inventory_dashboard(st, dashboard)
    else:
        _display_data(st, result.get("data") or {})
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


def _display_inventory_dashboard(st: Any, dashboard: Mapping[str, Any]) -> None:
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
        st.dataframe(exceptions, use_container_width=True, hide_index=True)
    else:
        st.caption("No flagged inventory exceptions in this snapshot.")


def _display_data(st: Any, value: Any, label: str = "Results") -> None:
    if isinstance(value, Mapping):
        sql = value.get("sql") or value.get("attempted_sql")
        if isinstance(sql, str):
            status = value.get("query_status", "executed")
            parameters = json.dumps(value.get("parameters", []), ensure_ascii=False)
            export = f"-- Query status: {status}\n-- Parameters (JSON): {parameters}\n{sql}\n"
            with st.expander(f"SQL query · {status}"):
                st.code(sql, language="sql")
                st.download_button("Download SQL", export, file_name="query.sql", mime="text/plain")
        rows = value.get("rows")
        if isinstance(rows, list) and rows and all(isinstance(row, Mapping) for row in rows):
            st.subheader(label)
            st.dataframe(rows, use_container_width=True, hide_index=True)
        for key, nested in value.items():
            if key != "rows" and isinstance(nested, Mapping):
                _display_data(st, nested, key.title())


def main() -> None:
    import streamlit as st

    st.set_page_config(page_title="Enterprise Knowledge Agent", page_icon="📊", layout="wide")
    st.title("Enterprise Knowledge Agent")
    st.caption(f"FastAPI backend: {os.getenv('API_BASE_URL', 'http://127.0.0.1:8000')}")
    mode_label = st.selectbox("Agent", list(AGENT_MODES))
    question = st.text_area("Question", height=100, placeholder="Ask about a VietStyle policy or commerce data…")
    is_report = AGENT_MODES[mode_label] == "report"
    report_template = st.file_uploader("Report template (DOCX or Markdown)", type=["docx", "md"]) if is_report else None
    category = st.text_input("Inventory category (optional)") if AGENT_MODES[mode_label] == "dashboard" else ""
    if is_report and st.button("Generate report", type="primary",
                               disabled=not question.strip() or report_template is None):
        try:
            with st.spinner("Generating report…"):
                payload, content_type = submit_report(question.strip(), report_template.name,
                                                      report_template.getvalue())
            st.download_button("Download report", payload, file_name=f"report{os.path.splitext(report_template.name)[1]}",
                               mime=content_type)
        except (RuntimeError, ValueError) as error:
            st.error(str(error))
    if not is_report and st.button("Ask", type="primary", disabled=not question.strip()):
        try:
            with st.spinner("Working…"):
                metadata = {"category": category.strip()} if category.strip() else None
                result = submit_chat(question.strip(), AGENT_MODES[mode_label], metadata=metadata)
            st.session_state["last_result"] = result
        except (RuntimeError, ValueError) as error:
            st.error(str(error))
    if "last_result" in st.session_state:
        display_result(st, st.session_state["last_result"])


if __name__ == "__main__":
    main()
