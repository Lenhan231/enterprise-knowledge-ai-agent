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
def _invoice(i, name, seller, no, status, total, days):
    return {"invoice_id": f"inv-{i}", "source_filename": name, "processing_status": status, "source_available": True,
            "created_at": f"2026-11-{days:02d}T08:30:00Z", "updated_at": f"2026-11-{days:02d}T09:10:00Z",
            "invoice_data": {} if status in ("processing", "failed") else {
                "invoice_no": no, "date": f"{days:02d}/11/2026", "seller": seller, "buyer": "Công ty TNHH Demo Commerce",
                "subtotal": f"{total:,}".replace(",", "."), "tax_amount": f"{total // 10:,}".replace(",", "."),
                "total_amount": f"{total + total // 10:,}".replace(",", "."),
                "items": [{"description": "Thùng carton 3 lớp 40×30×30", "quantity": "500", "unit": "thùng", "unit_price": "12.000", "amount": "6.000.000"},
                          {"description": "Băng keo đóng hàng 5 cm", "quantity": "120", "unit": "cuộn", "unit_price": "18.500", "amount": "2.220.000"}]},
            "error_message": "OCR could not read page 1" if status == "failed" else None,
            "ocr_elements": [{"page_number": 1, "label": "Header", "text": f"HÓA ĐƠN GIÁ TRỊ GIA TĂNG\nSố: {no}"}], "ocr_tables": []}


INVOICES = [_invoice(1, "HD-0012-bao-bi-minh-phat.pdf", "Công ty Bao bì Minh Phát", "0012", "review_required", 8220000, 12),
            _invoice(2, "HD-0458-van-tai-sao-viet.pdf", "Vận tải Sao Việt", "0458", "review_required", 15400000, 11),
            _invoice(3, "scan-hoa-don-1103.jpg", "", "", "processing", 0, 13),
            _invoice(4, "invoice_0854.png", "In ấn Tân Long", "0091", "approved", 4300000, 8),
            _invoice(5, "hoa-don-mo.png", "", "", "failed", 0, 7)]
INVOICE_SOURCE = """<!doctype html><meta charset="utf-8"><body style="font:14px/1.5 Georgia,serif;margin:28px;color:#222">
<p style="font:12px sans-serif;color:#888">Synthetic demo invoice</p><h2 style="margin:0">HÓA ĐƠN GIÁ TRỊ GIA TĂNG</h2><p>Số: 0012 · Ngày 12/11/2026</p>
<p><b>Đơn vị bán:</b> Công ty Bao bì Minh Phát<br><b>Người mua:</b> Công ty TNHH Demo Commerce</p>
<table border="1" cellpadding="6" style="border-collapse:collapse;width:100%"><tr><th>Hàng hóa</th><th>SL</th><th>Đơn giá</th><th>Thành tiền</th></tr>
<tr><td>Thùng carton 3 lớp 40×30×30</td><td>500</td><td>12.000</td><td>6.000.000</td></tr><tr><td>Băng keo đóng hàng 5 cm</td><td>120</td><td>18.500</td><td>2.220.000</td></tr></table>
<p style="text-align:right">Cộng: 8.220.000 · Thuế GTGT 10%: 822.000<br><b>Tổng cộng: 9.042.000</b></p></body>"""
INVOICE_IMAGE = """<svg xmlns="http://www.w3.org/2000/svg" width="1240" height="1754" viewBox="0 0 1240 1754" font-family="Arial, sans-serif">
<rect width="1240" height="1754" fill="#fff"/><text x="90" y="80" font-size="22" fill="#999">Synthetic demo invoice (scan)</text>
<text x="90" y="170" font-size="54" font-weight="700" fill="#1f5f4a">HÓA ĐƠN BÁN HÀNG</text>
<text x="1150" y="170" font-size="34" text-anchor="end">Ngày: 2026-11-13</text><text x="1150" y="225" font-size="30" text-anchor="end" fill="#666">Khách hàng: KH-41029</text>
<rect x="90" y="300" width="1060" height="70" rx="10" fill="#e6f2ec"/>
<text x="110" y="347" font-size="28" fill="#1f5f4a">SẢN PHẨM</text><text x="700" y="347" font-size="28" fill="#1f5f4a">SL</text><text x="880" y="347" font-size="28" fill="#1f5f4a">ĐƠN GIÁ</text><text x="1130" y="347" font-size="28" text-anchor="end" fill="#1f5f4a">THÀNH TIỀN</text>
<text x="110" y="440" font-size="30">VietMode RP-34 · SKU 1442</text><text x="700" y="440" font-size="30">8</text><text x="880" y="440" font-size="30">5.598,43</text><text x="1130" y="440" font-size="30" text-anchor="end">38.069,32</text>
<line x1="90" y1="500" x2="1150" y2="500" stroke="#ddd" stroke-width="2"/>
<text x="600" y="600" font-size="30" fill="#666">Tạm tính trước giảm giá</text><text x="1150" y="600" font-size="40" font-weight="700" text-anchor="end">38.069,32 VND</text>
<text x="600" y="680" font-size="30" fill="#666">Thuế GTGT (8%)</text><text x="1150" y="680" font-size="34" text-anchor="end">3.045,55 VND</text>
<line x1="600" y1="730" x2="1150" y2="730" stroke="#bbb" stroke-width="2"/>
<text x="600" y="810" font-size="40" font-weight="700" fill="#1f5f4a">TỔNG CỘNG</text><text x="1150" y="810" font-size="46" font-weight="700" text-anchor="end" fill="#1f5f4a">41.114,87 VND</text>
<text x="90" y="1650" font-size="22" fill="#999">VIETSTYLE · VS-788316</text></svg>"""
KNOWLEDGE_DOCS = [
    {"document_id": "vs-policy-v1", "title": "VietStyle Enterprise Operating Policy v1.0", "synthetic_company_policy": True, "source_publisher": "VietStyle (synthetic)",
     "format": "PDF", "chunk_count": 412, "processing_status": "ready", "knowledge_base_active": True, "knowledge_domains": ["inventory_allocation", "promotion_planning"],
     "allowed_roles": ["employee", "finance_analyst", "procurement", "operations"], "has_processing_output": True},
    {"document_id": "hr-2025", "title": "Quy chế nhân sự 2025", "source_type": "user_upload", "source_publisher": "HR department", "format": "PDF", "chunk_count": 96,
     "processing_status": "ready", "knowledge_base_active": True, "knowledge_domains": [], "allowed_roles": ["employee", "executive"]},
    {"document_id": "asset-rules", "title": "Quy định quản lý tài sản", "source_type": "user_upload", "source_publisher": "Administration", "format": "DOCX", "chunk_count": 0,
     "processing_status": "failed", "knowledge_base_active": True, "knowledge_domains": [], "allowed_roles": ["employee"]},
    {"document_id": "old-logistics", "title": "Logistics handbook 2023", "source_type": "user_upload", "source_publisher": "Operations", "format": "PDF", "chunk_count": 58,
     "processing_status": "ready", "knowledge_base_active": False, "knowledge_domains": ["nationwide_logistics"], "allowed_roles": ["operations"]},
]
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
    "/api/admin/knowledge-documents": {"documents": KNOWLEDGE_DOCS},
    "/api/invoices": {"invoices": INVOICES},
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
        if path == "/api/auth/me" and "demo_logout=1" in (self.headers.get("Cookie") or ""):
            return self.send_json({"detail": "Not signed in"}, 401)
        if path.startswith("/api/invoices/") and path.endswith("/source"):
            found = next((i for i in INVOICES if i["invoice_id"] == path.split("/")[3]), {})
            is_image = found.get("source_filename", "").lower().endswith((".png", ".jpg", ".jpeg"))
            raw = (INVOICE_IMAGE if is_image else INVOICE_SOURCE).encode()
            self.send_response(200)
            self.send_header("Content-Type", "image/svg+xml" if is_image else "text/html; charset=utf-8"); self.end_headers()
            return self.wfile.write(raw)
        if path.startswith("/api/invoices/"):
            found = next((i for i in INVOICES if i["invoice_id"] == path.rsplit("/", 1)[1]), None)
            return self.send_json(found or {"detail": "Not found"}, 200 if found else 404)
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
