"""Local UI demo: serves a static folder at /static and fakes the API with canned data. No backend, no keys."""
import json, os, sys, time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

STATIC = Path(sys.argv[1]).resolve()
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 8765
ROLE = sys.argv[3] if len(sys.argv) > 3 else "admin"

ANSWER = {
    "answer": "Khi nghỉ việc, nhân viên phải bàn giao toàn bộ công việc đang xử lý cho người được trưởng bộ phận chỉ định [S1].\n\n"
              "1. Lập biên bản bàn giao, liệt kê hồ sơ, tài liệu và công việc dang dở [S1].\n"
              "2. Trả lại tài sản công ty như máy tính, thẻ ra vào và con dấu (nếu có) [S2].\n"
              "3. Hoàn tất bàn giao chậm nhất 03 ngày làm việc trước ngày nghỉ chính thức [S1].\n\n"
              "Lương và các khoản còn lại chỉ được thanh toán sau khi biên bản bàn giao được ký xác nhận [S3].",
    "agent": "knowledge",
    "evidence": [
        {"citation_id": "S1", "source": "Quy chế nhân sự 2025.pdf", "source_type": "document",
         "content": "Điều 18. Bàn giao công việc. Người lao động nghỉ việc có trách nhiệm bàn giao toàn bộ công việc, hồ sơ cho người được Trưởng bộ phận chỉ định, lập biên bản bàn giao chậm nhất 03 ngày làm việc trước ngày nghỉ việc chính thức.",
         "metadata": {"page_number": 12, "chunk_index": 41}},
        {"citation_id": "S2", "source": "Quy định quản lý tài sản.pdf", "source_type": "document",
         "content": "Khi chấm dứt hợp đồng lao động, người lao động hoàn trả máy tính, thiết bị, thẻ ra vào, con dấu và các tài sản khác được cấp phát.",
         "metadata": {"page_number": 4, "chunk_index": 9}},
        {"citation_id": "S3", "source": "Quy chế nhân sự 2025.pdf", "source_type": "document",
         "content": "Công ty thanh toán tiền lương và các khoản liên quan trong vòng 07 ngày kể từ khi biên bản bàn giao được ký xác nhận.",
         "metadata": {"page_number": 13, "chunk_index": 44}},
    ],
    "data": {},
    "metadata": {"ok": True, "status": "complete", "selected_route": "knowledge",
                 "task_trace": [{"agent": "knowledge", "status": "complete", "elapsed_ms": 8420}],
                 "search": {"lexical_queries": {"vn": "bàn giao công việc khi nghỉ việc", "en": "work handover when resigning"},
                            "candidate_count": 30, "passages_to_model": 8, "reranker_model": "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1", "context_radius": 1},
                 "claim_verification": {"status": "supported", "reason": "all_claims_supported", "claim_count": 5},
                 "latency": {"request_total_ms": 9100, "stages_ms": {"database_retrieval": 1900, "reranking": 1200, "answer_generation": 3600, "claim_verification": 2100}}},
}
STAGES = ["routing", "query_translation", "database_retrieval", "reranking", "answer_generation", "claim_verification"]
FIXED = {
    "/api/auth/me": {"username": "demo.admin", "role": ROLE},
    "/api/auth/login": {"username": "demo.admin", "role": ROLE},
    "/api/auth/logout": {"ok": True},
    "/api/agents/feedback": {"saved": True},
    "/api/dashboard": {"document_count": 42, "chunk_count": 3180, "documents": [
        {"domain": "HR", "processing_status": "ready"}, {"domain": "Finance", "processing_status": "ready"},
        {"domain": "Procurement", "processing_status": "processing"}]},
    "/api/admin/access-matrix": {"roles": [
        {"role": "admin", "permissions": ["ask_documents", "upload_documents", "manage_knowledge", "view_agent_monitoring"]},
        {"role": "employee", "permissions": ["ask_documents"]},
        {"role": "finance_analyst", "permissions": ["ask_documents", "run_sql_analytics"]},
        {"role": "procurement", "permissions": ["ask_documents", "review_invoices"]},
        {"role": "document_uploader", "permissions": ["upload_documents"]},
        {"role": "document_processing_owner", "permissions": ["upload_documents", "inspect_parsing"]}]},
    "/api/admin/knowledge-documents": {"documents": []},
    "/api/invoices": {"invoices": []},
    "/api/upload-tests": {"runs": []},
    "/api/admin/answer-feedback": {"summary": {"up": 14, "down": 3}, "recent": [
        {"created_at": "2026-11-12T09:20:00Z", "rating": "down", "actor_role": "employee", "agent_name": "knowledge",
         "question": "Đi công tác 10 ngày được thanh toán khách sạn bao nhiêu?", "answer": "Tối đa 2.500.000 VND/đêm [S1].",
         "comment": "thiếu phụ cấp ăn", "claim_status": "supported"}]},
    "/api/admin/agent-monitoring": {
        "summary": {"total_runs": 128, "success_rate": 93.8, "average_elapsed_ms": 9420, "p95_elapsed_ms": 18800, "last_hour_runs": 11},
        "by_agent": [{"agent_name": "knowledge", "total_runs": 92, "completed_runs": 88, "average_elapsed_ms": 8900},
                     {"agent_name": "sql", "total_runs": 24, "completed_runs": 22, "average_elapsed_ms": 6100},
                     {"agent_name": "auto", "total_runs": 12, "completed_runs": 10, "average_elapsed_ms": 14200}],
        "recent_runs": [{"created_at": "2026-11-12T09:12:00Z", "actor_role": "employee", "agent_name": "knowledge",
                         "retrieval_method": "translated_hybrid_rerank", "status": "completed", "elapsed_ms": 8420, "citation_count": 3},
                        {"created_at": "2026-11-12T09:05:00Z", "actor_role": "finance_analyst", "agent_name": "sql",
                         "retrieval_method": "-", "status": "failed", "error_type": "timeout", "elapsed_ms": 30000, "citation_count": 0}]},
}


class Handler(SimpleHTTPRequestHandler):
    def translate_path(self, path):
        path = path.split("?")[0]
        if path in ("/", ""):
            return str(STATIC / "index.html")
        if path.startswith("/static/"):
            return str(STATIC / path[len("/static/"):])
        return str(STATIC / "__missing__")

    def send_json(self, body, status=200):
        raw = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/phone.html":
            raw = (Path(__file__).parent / "phone.html").read_bytes()
            self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.end_headers()
            return self.wfile.write(raw)
        if path == "/demo.js":
            raw = (Path(__file__).parent / "demo.js").read_bytes()
            self.send_response(200); self.send_header("Content-Type", "text/javascript"); self.end_headers()
            return self.wfile.write(raw)
        if path in ("/", "") and "shot=" in self.path or "theme=" in self.path and path in ("/", ""):
            raw = (STATIC / "index.html").read_text().replace("</head>", '<script src="/demo.js"></script></head>', 1).encode()
            self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.end_headers()
            return self.wfile.write(raw)
        if path.startswith("/api/"):
            return self.send_json(FIXED.get(path, {}))
        return super().do_GET()

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        path = self.path.split("?")[0]
        if path == "/api/agents/chat/stream":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(b": stream open\n\n"); self.wfile.flush()
            for stage in STAGES:
                self.wfile.write(f"event: stage\ndata: {json.dumps({'stage': stage, 'state': 'started'})}\n\n".encode()); self.wfile.flush()
                time.sleep(float(os.environ.get('DEMO_STAGE_SECONDS', '0.8')))
            self.wfile.write(f"event: result\ndata: {json.dumps(ANSWER, ensure_ascii=False)}\n\n".encode()); self.wfile.flush()
            return
        if path == "/api/agents/feedback":
            mode = os.environ.get("DEMO_FEEDBACK", "")
            if mode == "slow": time.sleep(2)
            if mode == "fail": time.sleep(1); return self.send_json({"detail": "Feedback storage is unavailable"}, 503)
            return self.send_json({"saved": True})
        if path == "/api/agents/chat":
            return self.send_json(ANSWER)
        return self.send_json(FIXED.get(path, {"ok": True}))

    def log_message(self, *_):
        pass


print(f"Demo UI: http://localhost:{PORT}/  (static from {STATIC}, role {ROLE})", flush=True)
ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
