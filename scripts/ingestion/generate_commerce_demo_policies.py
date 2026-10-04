#!/usr/bin/env python3
"""Generate explicitly fictional Commerce Demo decision-policy PDFs."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import subprocess
import tempfile
from html.parser import HTMLParser
from pathlib import Path

import fitz

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "data/commerce_knowledge/synthetic_policies"
POLICIES = [
    {
        "id": "CD-POL-INV-001",
        "slug": "inventory-allocation",
        "title": "Chính sách giả lập: Phân bổ và rà soát tồn kho",
        "domain": "inventory_allocation",
        "summary": "Dùng dữ liệu tồn kho để ưu tiên điều tra và lập phương án; không tự động điều chuyển hàng chỉ từ cờ thiếu hàng hoặc dư hàng.",
        "pages": [
            ("Mục đích và phạm vi", [
                ("callout", "DEMO GIẢ LẬP - KHÔNG PHẢI CHÍNH SÁCH CỦA DOANH NGHIỆP THẬT"),
                ("p", "Đơn vị Commerce Demo và toàn bộ dữ liệu vận hành trong ứng dụng là giả lập. Tài liệu này được tạo để kiểm thử RAG và agent hỗ trợ quyết định; không đại diện cho quy trình đã được một nhà bán lẻ thật phê duyệt."),
                ("p", "Quy tắc này áp dụng cho việc đọc snapshot tồn kho theo danh mục và năm trong bộ dữ liệu demo. Các cờ stockout và overstock là tín hiệu ở cấp product-snapshot; một sản phẩm có thể đồng thời xuất hiện ở cả hai nhóm."),
                ("h", "Nguyên tắc quyết định"),
                ("li", "Bắt đầu bằng kỳ dữ liệu và snapshot được chọn; nêu rõ đó là ảnh chụp tồn kho, không phải toàn bộ lịch sử sự cố."),
                ("li", "So sánh danh mục để xác định nơi cần kiểm tra sâu. Không diễn giải số cờ thành số SKU duy nhất hoặc số sự cố nếu dữ liệu không bảo đảm điều đó."),
                ("li", "Tách tín hiệu thiếu hàng và dư hàng; báo cáo phần giao nhau thay vì cộng hai nhóm như các trường hợp loại trừ nhau."),
            ]),
            ("Điều kiện hành động và giới hạn dữ liệu", [
                ("h", "Khi nào được đề xuất phương án"),
                ("li", "Có thể đề xuất kiểm tra SKU, điểm bán/kho và nhu cầu theo cùng một thời điểm khi dashboard cho thấy nhóm có nhiều cờ thiếu hàng."),
                ("li", "Chỉ xem xét điều chuyển khi có đối chiếu SKU giữa nơi gửi và nơi nhận, tồn khả dụng, nhu cầu dự báo, thời gian bổ sung, chi phí vận chuyển và ràng buộc dịch vụ."),
                ("li", "Chỉ đề xuất tăng/giảm đặt hàng khi có lịch sử nhu cầu, lead time, quy cách đặt hàng, chi phí lưu kho và mục tiêu dịch vụ được phê duyệt cho demo."),
                ("h", "Không được suy diễn"),
                ("li", "Không tự đặt safety stock, reorder point, service-level target, ngưỡng ngày tồn kho hoặc tỷ lệ điều chuyển."),
                ("li", "Không khẳng định nguyên nhân stockout/overstock, lợi ích tài chính hoặc tác động nhân quả nếu SQL không có bằng chứng."),
                ("li", "Nếu thiếu trường cần thiết, nêu quyết định chưa thể chốt và liệt kê dữ liệu cần thu thập trước khi thử nghiệm."),
                ("h", "Đầu ra agent cần có"),
                ("p", "(1) snapshot/kỳ và số liệu SQL; (2) tín hiệu và phần giao nhau; (3) bước kiểm tra có điều kiện; (4) trường dữ liệu còn thiếu. Policy này không cấp quyền tự thay đổi tồn kho."),
            ]),
            ("Quản trị tài liệu", [
                ("kv", "Mã policy", "CD-POL-INV-001"),
                ("kv", "Phiên bản / hiệu lực", "Demo v1.0 / 04-10-2026; chỉ trong kịch bản Commerce Demo"),
                ("kv", "Chủ sở hữu", "Commerce Demo - fictional demo organization"),
                ("kv", "Trạng thái", "Policy giả lập để kiểm thử; không phải phê duyệt doanh nghiệp thật"),
                ("h", "Cách agent phải trình bày"),
                ("p", "Gọi đây là “policy giả lập của Commerce Demo”. Không gọi đây là policy của một nhà bán lẻ có thật. Tách quan sát từ SQL khỏi quy tắc quyết định trong tài liệu; trích dẫn cả hai khi cùng được dùng."),
                ("callout", "RÀNG BUỘC: Không ra lệnh điều chuyển hoặc tự đặt ngưỡng thiếu căn cứ."),
            ]),
        ],
    },
    {
        "id": "CD-POL-PROMO-001",
        "slug": "promotion-planning",
        "title": "Chính sách giả lập: Đánh giá và lập kế hoạch khuyến mãi",
        "domain": "promotion_planning",
        "summary": "Phân biệt kết quả quan sát với tác động tăng thêm; không tăng ngân sách chỉ vì nhóm có gắn khuyến mãi có doanh số cao.",
        "pages": [
            ("Mục đích và phạm vi", [
                ("callout", "DEMO GIẢ LẬP - KHÔNG PHẢI CHÍNH SÁCH CỦA DOANH NGHIỆP THẬT"),
                ("p", "Đơn vị Commerce Demo và dữ liệu giao dịch/khuyến mãi là giả lập. Đây là policy giả lập để kiểm thử trợ lý phân tích; không phải quy trình của doanh nghiệp ngoài đời."),
                ("p", "Quy tắc áp dụng cho phân tích tagged-versus-untagged, so sánh campaign và đề xuất kế hoạch thử nghiệm. Dashboard hiện có thể cho kết quả mô tả, nhưng nhãn khuyến mãi không tự tạo ra nhóm đối chứng."),
                ("h", "Thứ tự đánh giá"),
                ("li", "Xác nhận kỳ, campaign, nhóm sản phẩm và định nghĩa trường trước khi so sánh."),
                ("li", "Báo cáo doanh số, đơn hàng, sản lượng và mức giảm giá như kết quả quan sát; nói rõ nhóm có thể khác nhau về sản phẩm, khách hàng và thời điểm."),
                ("li", "Muốn ước lượng doanh số tăng thêm, yêu cầu thiết kế holdout/treatment-control hoặc phương pháp đối chứng phù hợp và nêu các giả định."),
            ]),
            ("Điều kiện ngân sách và bảo vệ kết luận", [
                ("h", "Điều kiện trước khi mở rộng ngân sách"),
                ("li", "Có ước lượng incrementality từ thiết kế đo lường phù hợp, không chỉ so sánh doanh số của đơn có/không có tag."),
                ("li", "Có chi phí campaign, discount funding, giá vốn và contribution margin theo cùng phạm vi để đánh giá hiệu quả lợi nhuận."),
                ("li", "Có kiểm tra tính đầy đủ dữ liệu, thời gian đo, khả năng nhiễm chéo giữa nhóm và độ bất định của kết quả."),
                ("h", "Không được suy diễn"),
                ("li", "Không gọi chênh lệch tagged/untagged là uplift hoặc tác động nhân quả."),
                ("li", "Không dùng ROAS thay ROI hoặc lợi nhuận tăng thêm; không tự tạo ngưỡng ROI, mức tăng trưởng, ngân sách hay số tuần thử nghiệm."),
                ("li", "Nếu thiếu holdout hoặc chi phí/lợi nhuận theo campaign, chỉ mô tả kết quả và đề xuất phép đo cần bổ sung; không khuyến nghị tăng ngân sách."),
                ("h", "Đầu ra agent cần có"),
                ("p", "Tách rõ: số liệu quan sát từ SQL; phương pháp đo được policy yêu cầu; kết luận hiện đủ/chưa đủ bằng chứng; dữ liệu hoặc thử nghiệm tiếp theo. Policy không đảm bảo một campaign sẽ sinh lợi."),
            ]),
            ("Quản trị tài liệu", [
                ("kv", "Mã policy", "CD-POL-PROMO-001"),
                ("kv", "Phiên bản / hiệu lực", "Demo v1.0 / 04-10-2026; chỉ trong kịch bản Commerce Demo"),
                ("kv", "Chủ sở hữu", "Commerce Demo - fictional demo organization"),
                ("kv", "Trạng thái", "Policy giả lập để kiểm thử; không phải phê duyệt doanh nghiệp thật"),
                ("h", "Cách agent phải trình bày"),
                ("p", "Gọi đây là “policy giả lập của Commerce Demo”. Không gán policy này cho retailer, marketplace hay doanh nghiệp có thật. Trích số liệu SQL và tài liệu phương pháp riêng biệt."),
                ("callout", "RÀNG BUỘC: Thiếu holdout, chi phí hoặc margin thì không tăng ngân sách."),
            ]),
        ],
    },
    {
        "id": "CD-POL-LOG-001",
        "slug": "nationwide-logistics",
        "title": "Chính sách giả lập: Theo dõi và tối ưu logistics toàn quốc",
        "domain": "nationwide_logistics",
        "summary": "Dùng số liệu vùng để phát hiện câu hỏi cần điều tra; không thiết kế lại mạng lưới từ trung bình vùng khi thiếu dữ liệu tuyến.",
        "pages": [
            ("Mục đích và phạm vi", [
                ("callout", "DEMO GIẢ LẬP - KHÔNG PHẢI CHÍNH SÁCH CỦA DOANH NGHIỆP THẬT"),
                ("p", "Commerce Demo là tổ chức giả lập; dữ liệu shipment không đại diện cho mạng lưới vận tải thật tại Việt Nam. Tài liệu dùng để thử luồng agent kết hợp SQL và RAG."),
                ("p", "Dashboard hiện tổng hợp thời gian từ ship đến delivery và shipping fee theo vùng. Các trung bình này hỗ trợ mô tả, không cho biết tuyến, carrier, điểm xuất phát, SLA cam kết hoặc năng lực kho."),
                ("h", "Nguyên tắc theo dõi"),
                ("li", "Nêu rõ định nghĩa thời gian giao hàng và kỳ được chọn; không coi thời gian trung bình là SLA hoặc tỷ lệ giao đúng hẹn."),
                ("li", "So sánh vùng/kỳ như thống kê mô tả và nêu giới hạn phân bố, cỡ mẫu hoặc khác biệt cơ cấu nếu có."),
                ("li", "Dùng chênh lệch để đặt câu hỏi điều tra, không tự gán nguyên nhân cho carrier, kho, thời tiết hay năng lực."),
            ]),
            ("Điều kiện thiết kế thay đổi mạng lưới", [
                ("h", "Dữ liệu tối thiểu trước khi đề xuất thay đổi"),
                ("li", "Shipment-level origin, destination, route/lane, carrier/service class và timestamp các mốc xử lý."),
                ("li", "SLA cam kết, ngày hứa giao, tỷ lệ giao đúng hạn, exception/return và phân bố thời gian giao."),
                ("li", "Chi phí theo tuyến/dịch vụ, phụ phí, năng lực kho/carrier, nhu cầu và giới hạn địa lý."),
                ("li", "Network design hoặc route optimization chỉ sau khi so sánh phương án trên cùng tập đơn/kỳ, ghi nhận giả định, trade-off chi phí/dịch vụ và kế hoạch pilot."),
                ("h", "Không được suy diễn"),
                ("li", "Không đề xuất đóng/mở kho, đổi carrier, chuyển năng lực hoặc đặt SLA số học chỉ từ trung bình vùng."),
                ("li", "Không tự đặt ngưỡng ngày, mức tiết kiệm, ngưỡng trễ hay tỷ lệ cải thiện mục tiêu."),
                ("li", "Nếu schema thiếu route-level evidence, nêu rõ chưa thể chọn phương án và yêu cầu tập dữ liệu cần thiết."),
                ("h", "Đầu ra agent cần có"),
                ("p", "Báo cáo dữ kiện SQL; phân biệt tín hiệu mô tả với quyết định thiết kế; nêu trường thiếu và bước phân tích/pilot tiếp theo. Không biến policy này thành chỉ thị vận hành tự động."),
            ]),
            ("Quản trị tài liệu", [
                ("kv", "Mã policy", "CD-POL-LOG-001"),
                ("kv", "Phiên bản / hiệu lực", "Demo v1.0 / 04-10-2026; chỉ trong kịch bản Commerce Demo"),
                ("kv", "Chủ sở hữu", "Commerce Demo - fictional demo organization"),
                ("kv", "Trạng thái", "Policy giả lập để kiểm thử; không phải phê duyệt doanh nghiệp thật"),
                ("h", "Cách agent phải trình bày"),
                ("p", "Gọi đây là “policy giả lập của Commerce Demo”. Không suy rộng kết quả của bộ dữ liệu sang doanh nghiệp thật hoặc toàn bộ logistics Việt Nam. Nguồn SQL và policy phải được trích riêng."),
                ("callout", "RÀNG BUỘC: Cần dữ liệu tuyến, SLA, năng lực và chi phí trước khi tối ưu."),
            ]),
        ],
    },
]


class _VisibleText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.in_style = False

    def handle_starttag(self, tag: str, attrs) -> None:
        self.in_style = tag.casefold() == "style"

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() == "style":
            self.in_style = False

    def handle_data(self, data: str) -> None:
        if not self.in_style and data.strip():
            self.parts.append(data.strip())


def write_ocr_ground_truth(manifest_path: Path) -> Path:
    """Save authored policy text as page-level OCR references for active scans."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    sources = {source["source_id"]: source for source in manifest["sources"]}
    pages = []
    for policy in POLICIES:
        source = sources.get(policy["id"])
        if not source:
            raise RuntimeError(f"Missing manifest source for {policy['id']}")
        pdf_path = ROOT / source["local_path"]
        source_hash = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
        if source.get("content_sha256") != source_hash:
            raise RuntimeError(f"Policy PDF and manifest checksum differ for {policy['id']}")
        with fitz.open(pdf_path) as document:
            if len(document) != len(policy["pages"]):
                raise RuntimeError(f"Policy page count differs from authored source for {policy['id']}")
            for page_number, page in enumerate(document, start=1):
                text = _VisibleText()
                text.feed(build_html(policy, page_number))
                pages.append({
                    "id": f"{policy['id']}-PAGE-{page_number}",
                    "document_id": policy["id"],
                    "file": source["local_path"],
                    "page": page_number,
                    "language": "vie",
                    "image_only": True,
                    "physical_scan": False,
                    "layout_type": "text",
                    "clip_rect": [0, 0, page.rect.width, page.rect.height],
                    "source_pdf_sha256": source_hash,
                    "reference_text": " ".join(text.parts),
                })
    dataset = {
        "dataset_id": "commerce-active-synthetic-policy-scan-ground-truth-v1",
        "purpose": "Score OCR on the exact active scan-only Commerce Demo policy PDFs.",
        "reference_quality": "authored_policy_html_not_human_reviewed",
        "reference_method": "Visible text extracted with Python HTMLParser from the authored policy page HTML before rasterization.",
        "primary_metric_selection_eligible": False,
        "limitations": [
            "The policies are fictional Commerce Demo examples, not real company rules.",
            "The PDFs were digitally rasterized and are not physical scans.",
            "Reference text comes from authored HTML and has not been independently human-reviewed.",
        ],
        "pages": pages,
    }
    output = ROOT / "data/evaluation/ocr/commerce_policy_scan_ground_truth.json"
    output.write_text(json.dumps(dataset, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output


def page_html(policy: dict, heading: str, blocks: list[tuple[str, ...]], page_number: int) -> str:
    body = []
    list_items = []
    for block in blocks:
        kind, *values = block
        if kind == "li":
            list_items.append(f"<li>{html.escape(values[0])}</li>")
            continue
        if list_items:
            body.append("<ul>" + "".join(list_items) + "</ul>")
            list_items = []
        if kind == "h":
            body.append(f"<h2>{html.escape(values[0])}</h2>")
        elif kind == "p":
            body.append(f"<p>{html.escape(values[0])}</p>")
        elif kind == "callout":
            body.append(f"<div class='callout'>{html.escape(values[0])}</div>")
        elif kind == "kv":
            body.append(
                f"<p class='metadata'><strong>{html.escape(values[0])}:</strong> "
                f"{html.escape(values[1])}</p>"
            )
    if list_items:
        body.append("<ul>" + "".join(list_items) + "</ul>")
    title = (
        f"<h1>{html.escape(policy['title'])}</h1>"
        f"<div class=\"summary\">{html.escape(policy['summary'])}</div>"
        if page_number == 1 else
        f"<div class=\"running-title\">{html.escape(policy['title'])}</div>"
    )
    return f"""
    <section class="page" style="page-break-before: {'auto' if page_number == 1 else 'always'}">
      <div class="banner">SYNTHETIC DEMO POLICY - NOT A REAL COMPANY POLICY</div>
      <div class="eyebrow">COMMERCE DEMO / {html.escape(policy['id'])}</div>
      {title}
      <h2>{html.escape(heading)}</h2>
      {''.join(body)}
      <div class="footer">Commerce Demo (fictional) · Demo v1.0 · 04-10-2026 · Page {page_number}/3</div>
    </section>
    """


def build_html(policy: dict, page_number: int) -> str:
    heading, blocks = policy["pages"][page_number - 1]
    page = page_html(policy, heading, blocks, page_number)
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
    @page {{ size: A4; margin: 15mm 17mm 17mm; }}
    body {{ font-family: 'Noto Sans'; color: #1b2b40; font-size: 10.2pt; line-height: 1.42; }}
    .page {{ }}
    .banner {{ background: #fff1e8; color: #9a3412; padding: 7px 10px; border-left: 4px solid #e36d36; font-size: 8pt; font-weight: bold; letter-spacing: .6px; }}
    .eyebrow {{ color: #356fd3; font-size: 8pt; font-weight: bold; letter-spacing: 1.1px; margin-top: 20px; }}
    h1 {{ font-size: 23pt; line-height: 1.16; margin: 7px 0 10px; }}
    .summary {{ background: #f2f6fc; border-left: 3px solid #4f83df; padding: 10px 12px; margin: 8px 0 16px; color: #334a66; }}
    h2 {{ color: #234d89; font-size: 14pt; margin: 14px 0 8px; }}
    p {{ margin: 7px 0; }}
    ul {{ margin: 4px 0 9px; padding-left: 20px; }}
    li {{ margin: 4px 0; padding-left: 2px; }}
    .callout {{ background: #fff7ed; border: 1px solid #fed7aa; color: #9a3412; padding: 9px 11px; font-weight: bold; margin: 10px 0; }}
    .running-title {{ color: #234d89; font-size: 10pt; font-weight: bold; margin-top: 5px; }}
    .metadata {{ margin: 5px 0; }}
    .footer {{ margin-top: 16px; padding-top: 7px; border-top: 1px solid #dbe4f0; color: #687a91; font-size: 8pt; }}
    </style></head><body>{page}</body></html>"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ground-truth-only", action="store_true",
        help="Refresh the OCR reference file against existing policy PDFs without regenerating them.",
    )
    args = parser.parse_args()
    manifest_path = ROOT / "data/commerce_knowledge/manifest.json"
    if args.ground_truth_only:
        print(f"wrote OCR references to {write_ocr_ground_truth(manifest_path).relative_to(ROOT)}")
        return

    OUTPUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="commerce-policies-") as temporary:
        temp = Path(temporary)
        for policy in POLICIES:
            page_pdfs = []
            for page_number in range(1, len(policy["pages"]) + 1):
                source = temp / f"{policy['slug']}-{page_number}.html"
                source.write_text(build_html(policy, page_number), encoding="utf-8")
                result = subprocess.run(
                    ["libreoffice", "--headless", "--convert-to", "pdf", "--outdir", str(temp), str(source)],
                    check=True, capture_output=True, text=True,
                )
                pdf_page = source.with_suffix(".pdf")
                if not pdf_page.exists():
                    raise RuntimeError(f"LibreOffice did not create a PDF page: {result.stdout} {result.stderr}")
                page_pdfs.append(pdf_page)
            generated = OUTPUT / f"{policy['slug']}.pdf"
            digital_pdf = temp / f"{policy['slug']}-digital.pdf"
            subprocess.run(
                ["pdfunite", *(str(path) for path in page_pdfs), str(digital_pdf)],
                check=True, capture_output=True, text=True,
            )
            # Keep these mock policies useful for validating the scanned-PDF path.
            # Larger rasterization and reduced repeated headers improve OCR legibility and retrieval signal.
            with fitz.open(digital_pdf) as source, fitz.open() as scanned:
                for page in source:
                    pixmap = page.get_pixmap(matrix=fitz.Matrix(4, 4), alpha=False)
                    scan_page = scanned.new_page(width=page.rect.width, height=page.rect.height)
                    scan_page.insert_image(scan_page.rect, stream=pixmap.tobytes("jpeg", jpg_quality=95))
                scanned.set_metadata({
                    "title": policy["title"],
                    "author": "Commerce Demo (fictional)",
                    "subject": "Synthetic scan-only policy for OCR/RAG demo; not a real company policy",
                    "keywords": f"synthetic demo policy, {policy['domain']}, OCR test",
                })
                scanned.save(generated, garbage=4, deflate=True)
            if not generated.exists() or not generated.read_bytes().startswith(b"%PDF-"):
                raise RuntimeError(f"The assembled policy is not a valid PDF: {generated}")
            with fitz.open(generated) as check:
                if any(page.get_text().strip() for page in check):
                    raise RuntimeError(f"The scanned policy unexpectedly contains text: {generated}")
                if any(not page.get_images() for page in check):
                    raise RuntimeError(f"A scanned policy page has no raster image: {generated}")
                print(
                    f"created scan-only {generated.relative_to(ROOT)} "
                    f"({len(check)} pages, {generated.stat().st_size} bytes)"
                )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    sources = {source["source_id"]: source for source in manifest["sources"]}
    for policy in POLICIES:
        source = sources.get(policy["id"])
        expected_path = str((OUTPUT / f"{policy['slug']}.pdf").relative_to(ROOT))
        if source is None or source.get("local_path") != expected_path:
            raise RuntimeError(f"Missing or mismatched manifest source for {policy['id']}")
        pdf_path = ROOT / source["local_path"]
        source["content_sha256"] = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    print(f"wrote OCR references to {write_ocr_ground_truth(manifest_path).relative_to(ROOT)}")


if __name__ == "__main__":
    main()
