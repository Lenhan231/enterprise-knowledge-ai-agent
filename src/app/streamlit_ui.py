"""Small Streamlit client for the FastAPI chat endpoint."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from typing import Any


AGENT_MODES = {"Knowledge": "knowledge", "SQL": "sql", "Agentic": "agentic"}


def submit_chat(question: str, agent_mode: str, *, api_url: str | None = None, opener=None) -> dict[str, Any]:
    if agent_mode not in AGENT_MODES.values():
        raise ValueError("Choose Knowledge, SQL, or Agentic mode.")
    request = Request(
        f"{(api_url or os.getenv('API_BASE_URL', 'http://127.0.0.1:8000')).rstrip('/')}/api/chat",
        data=json.dumps({"question": question, "agent_mode": agent_mode}).encode(),
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


def display_result(st: Any, result: Mapping[str, Any]) -> None:
    st.markdown(result.get("answer", "No answer returned."))
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
    if st.button("Ask", type="primary", disabled=not question.strip()):
        try:
            with st.spinner("Working…"):
                result = submit_chat(question.strip(), AGENT_MODES[mode_label])
            st.session_state["last_result"] = result
        except (RuntimeError, ValueError) as error:
            st.error(str(error))
    if "last_result" in st.session_state:
        display_result(st, st.session_state["last_result"])


if __name__ == "__main__":
    main()
