"""Single-user local UI for the Docling document-processing store."""

from __future__ import annotations

import hashlib
from io import BytesIO
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import streamlit as st
from PIL import Image, ImageDraw

from document_processing.document_processor import DocumentProcessor, SUPPORTED_FORMATS
from document_processing.element_taxonomy import normalize_element_label


PACKAGE_DIR = Path(__file__).resolve().parent
STORE_DIR = Path(os.environ.get("DOCUMENT_PROCESSING_STORE", PACKAGE_DIR / ".owner_store")).expanduser()
MAX_UPLOAD_BYTES = 50 * 1024 * 1024


def _load_runs() -> list[dict[str, Any]]:
    runs = []
    if not STORE_DIR.exists():
        return runs
    for manifest_path in STORE_DIR.glob("*/manifest.json"):
        try:
            runs.append(json.loads(manifest_path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    return sorted(runs, key=lambda run: run.get("processed_at", ""), reverse=True)


def _normalize_saved_output(output: dict[str, Any]) -> dict[str, Any]:
    """Present older saved parser results with the shared element labels."""
    for element in output.get("elements", []):
        metadata = element.setdefault("metadata", {})
        metadata.pop("word_style", None)
        metadata.pop("word_style_id", None)
        label = normalize_element_label(
            metadata.get("element_type") or metadata.get("layout_type") or element.get("element_type")
        )
        metadata["element_type"] = label
        metadata["layout_type"] = label
        if "element_type" in element:
            element["element_type"] = label
    for table in output.get("tables", []):
        metadata = table.setdefault("metadata", {})
        metadata.pop("word_style", None)
        metadata.pop("word_style_id", None)
        metadata.update({"element_type": "table", "layout_type": "table"})
    return output


def _page_count(run_dir: Path) -> int:
    return sum(1 for _ in run_dir.glob("page-*.png"))


def _table_display_name(table: dict[str, Any], index: int) -> str:
    metadata = table.get("metadata") or {}
    context = table.get("context") or {}
    title = (
        table.get("table_name")
        or context.get("table_title")
        or context.get("table_name")
        or metadata.get("table_name")
        or metadata.get("table_title")
    )
    if title and str(title).strip():
        return str(title).strip()
    columns = [str(column).strip() for column in (table.get("columns") or []) if str(column).strip()]
    return " · ".join(columns[:3]) or f"Table {index}"


def _page_preview(run_dir: Path, page_number: int) -> bytes | None:
    preview_path = run_dir / f"page-{page_number}.png"
    return preview_path.read_bytes() if preview_path.is_file() else None


def _page_preview_with_boxes(
    preview: bytes,
    elements: list[dict[str, Any]],
    tables: list[dict[str, Any]],
    page_size: dict[str, float] | None,
    *,
    default_origin: str,
) -> bytes:
    image = Image.open(BytesIO(preview)).convert("RGB")
    draw = ImageDraw.Draw(image)
    page_width = float((page_size or {}).get("width") or image.width)
    page_height = float((page_size or {}).get("height") or image.height)
    scale_x, scale_y = image.width / page_width, image.height / page_height

    def draw_bbox(metadata: dict[str, Any], color: str, label: str) -> None:
        bbox = metadata.get("bbox")
        if not isinstance(bbox, list) or len(bbox) != 4:
            return
        try:
            left, top_or_bottom, right, bottom_or_top = map(float, bbox)
        except (TypeError, ValueError):
            return
        origin = str(metadata.get("bbox_coordinate_origin") or default_origin).upper()
        if origin == "BOTTOMLEFT":
            top, bottom = page_height - bottom_or_top, page_height - top_or_bottom
        else:
            top, bottom = top_or_bottom, bottom_or_top
        xyxy = (
            round(left * scale_x),
            round(top * scale_y),
            round(right * scale_x),
            round(bottom * scale_y),
        )
        draw.rectangle(xyxy, outline=color, width=max(2, image.width // 900))
        if label:
            draw.text((xyxy[0] + 2, max(0, xyxy[1] - 14)), label, fill=color)

    for element in elements:
        metadata = element.get("metadata") or {}
        kind = normalize_element_label(metadata.get("element_type") or metadata.get("layout_type") or metadata.get("docling_label"))
        color = {
            "title": "#ff9b69",
            "title_table": "#e879f9",
            "section_header": "#38bdf8",
            "text": "#58aeff",
            "footnote": "#f472b6",
            "document_index": "#fbbf24",
            "formula": "#c084fc",
            "figure": "#ffcf5c",
            "seal": "#fb7185",
            "page_header": "#a78bfa",
            "page_footer": "#f472b6",
            "table": "#65d99b",
        }[kind]
        draw_bbox(metadata, color, kind)
    for table in tables:
        draw_bbox(table.get("metadata") or {}, "#65d99b", "table")

    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _process_upload(
    filename: str,
    content: bytes,
    *,
    ocr_engine: str,
    language: str,
    device: str,
    ocr_enabled: bool,
    table_structure: bool,
    num_threads: int,
) -> dict[str, Any]:
    run_id = uuid.uuid4().hex
    run_dir = STORE_DIR / run_id
    STORE_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    STORE_DIR.chmod(0o700)
    run_dir.mkdir(mode=0o700, exist_ok=False)
    try:
        source_path = run_dir / "source"
        source_path.write_bytes(content)
        source_path.chmod(0o600)
        config = {
            "parser_engine": "docling",
            "docling_device": device,
            "docling_ocr": ocr_enabled,
            "docling_ocr_engine": ocr_engine,
            "docling_ocr_language": language,
            "docling_table_structure": table_structure,
            "docling_num_threads": num_threads,
            "docling_page_images": True,
        }
        metadata = {
            "source_type": "local_owner_store",
            "source_sha256": hashlib.sha256(content).hexdigest(),
        }
        output = DocumentProcessor(config).process(filename, content, metadata)
        page_previews = output.pop("page_previews", {})
        for page_number, image_bytes in page_previews.items():
            preview_path = run_dir / f"page-{int(page_number)}.png"
            preview_path.write_bytes(image_bytes)
            preview_path.chmod(0o600)
        output_text = json.dumps(output, ensure_ascii=False, indent=2, default=str)
        output_path = run_dir / "output.json"
        output_path.write_text(output_text, encoding="utf-8")
        output_path.chmod(0o600)
        manifest = {
            "run_id": run_id,
            "filename": filename,
            "processed_at": datetime.now(timezone.utc).isoformat(),
            "source_sha256": metadata["source_sha256"],
            "element_count": len(output.get("elements", [])),
            "table_count": len(output.get("tables", [])),
            "config": config,
        }
        manifest_path = run_dir / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8",
        )
        manifest_path.chmod(0o600)
        return {"manifest": manifest, "output": output, "output_text": output_text}
    except Exception:
        for path in run_dir.iterdir():
            path.unlink()
        run_dir.rmdir()
        raise


st.set_page_config(page_title="Document store", layout="wide")
st.markdown(
    """
    <style>
    [data-testid="stAppViewContainer"] .main .block-container {
        max-width: 1440px;
        padding-top: 2.25rem;
        padding-bottom: 4rem;
    }
    [data-testid="stFileUploader"] section {
        border: 1px dashed rgba(128, 128, 128, 0.55);
        border-radius: 12px;
        padding: 1rem;
    }
    [data-testid="stMetric"] {
        background: var(--secondary-background-color);
        border: 1px solid rgba(128, 128, 128, 0.18);
        border-radius: 12px;
        padding: 0.8rem 1rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.caption("PRIVATE DOCUMENT WORKSPACE")
st.title("Document store")
st.markdown("Upload a file, review Docling’s extracted content, and keep the results on this machine.")

upload_column, settings_column = st.columns([1.7, 1], gap="large")
with settings_column:
    with st.container(border=True):
        st.subheader("Processing settings")
        ocr_engine = st.selectbox(
            "OCR engine",
            ["vietocr", "tesseract"],
            format_func={
                "vietocr": "VietOCR · benchmark best",
                "tesseract": "Tesseract",
            }.__getitem__,
            index=0,
        )
        language = "vie+eng"
        if ocr_engine == "tesseract":
            language = st.selectbox(
                "OCR languages",
                ["vie+eng", "vie", "eng"],
                format_func={
                    "vie+eng": "Vietnamese + English",
                    "vie": "Vietnamese only",
                    "eng": "English only",
                }.__getitem__,
            )
        device = st.selectbox("Device", ["cpu", "cuda"], format_func={
            "cpu": "CPU",
            "cuda": "NVIDIA CUDA",
        }.__getitem__)
        ocr_enabled = st.selectbox("OCR", [True, False], format_func={
            True: "On · scanned pages",
            False: "Off · digital text only",
        }.__getitem__)
        table_structure = st.selectbox("Table structure recognition", [True, False], format_func={
            True: "On",
            False: "Off",
        }.__getitem__)
        num_threads = st.number_input("CPU threads", min_value=1, max_value=16, value=4)
        st.caption("Tables: Accurate mode")
        st.caption(
            "VietOCR uses RapidOCR line detection + vgg_seq2seq greedy recognition (512 px), "
            "matching the 58-page OCR benchmark."
            if ocr_engine == "vietocr"
            else "Tesseract PSM 6 with the selected languages."
        )

with upload_column:
    with st.container(border=True):
        st.subheader("Add a document")
        st.caption("PDF, Office, CSV, TXT, Markdown, or image · maximum 50 MiB")
        uploaded = st.file_uploader(
            "Choose a file",
            type=sorted(suffix.lstrip(".") for suffix in SUPPORTED_FORMATS),
            label_visibility="collapsed",
        )
        if uploaded is not None:
            st.caption(f"Selected: **{Path(uploaded.name).name}** · {len(uploaded.getvalue()) / 1024:,.1f} KB")
            if st.button("Process and save", type="primary", use_container_width=True):
                content = uploaded.getvalue()
                if len(content) > MAX_UPLOAD_BYTES:
                    st.error("The document exceeds the 50 MiB limit.")
                else:
                    with st.spinner(f"Processing document with {ocr_engine} OCR…"):
                        try:
                            st.session_state["latest_run"] = _process_upload(
                                Path(uploaded.name).name,
                                content,
                                ocr_engine=ocr_engine,
                                language=language,
                                device=device,
                                ocr_enabled=ocr_enabled,
                                table_structure=table_structure,
                                num_threads=int(num_threads),
                            )
                        except Exception as error:
                            st.error(f"Could not process {Path(uploaded.name).name}.")
                            with st.expander("Technical details"):
                                st.exception(error)
                            st.stop()
                    st.success("Document processed and saved.")
        else:
            st.info("Choose a document to begin processing.")

st.divider()
runs = _load_runs()
st.subheader("Saved documents")
if not runs:
    st.info(f"No saved documents yet. Results will be stored locally in `{STORE_DIR}`.")
else:
    st.caption(f"{len(runs):,} saved document{'s' if len(runs) != 1 else ''} · stored locally")
    labels = {
        run["run_id"]: f'{run["filename"]} · {run["processed_at"][:19].replace("T", " ")}'
        for run in runs
    }
    selected_id = st.selectbox("Select a document", labels, format_func=labels.__getitem__)
    selected_manifest = next(run for run in runs if run["run_id"] == selected_id)
    try:
        selected_output_path = STORE_DIR / selected_id / "output.json"
        selected_output_text = selected_output_path.read_text(encoding="utf-8")
        selected_output = _normalize_saved_output(json.loads(selected_output_text))
        selected_output_text = json.dumps(selected_output, ensure_ascii=False, indent=2, default=str)
    except (OSError, json.JSONDecodeError, KeyError) as error:
        st.error(f"Could not open this saved result: {error}")
    else:
        elements = selected_output.get("elements", [])
        raw_text = "\n\n".join(
            str(element.get("text") or "").strip()
            for element in elements
            if str(element.get("text") or "").strip()
        )
        metric_columns = st.columns([1, 1, 2, 2])
        metric_columns[0].metric("Elements", f'{selected_manifest["element_count"]:,}')
        metric_columns[1].metric("Tables", f'{selected_manifest["table_count"]:,}')
        metric_columns[2].download_button(
            "Download raw text",
            raw_text,
            file_name=f'{Path(selected_manifest["filename"]).stem}.txt',
            mime="text/plain; charset=utf-8",
            disabled=not raw_text,
            use_container_width=True,
        )
        metric_columns[3].download_button(
            "Download parser output JSON",
            selected_output_text,
            file_name=f'{selected_manifest["filename"]}.docling.json',
            mime="application/json",
            use_container_width=True,
        )
        if st.button(
            "Upload parser output to Supabase (no chunking)",
            key=f"upload-parser-output-{selected_id}",
            help="Save parser output plus separate text-element and figure rows. Table regions remain in the raw parser output; no chunks or embeddings are created.",
        ):
            from dotenv import load_dotenv

            load_dotenv(Path(__file__).resolve().parents[2] / ".env")
            repository = None
            try:
                from core.database.document_processing_output_repository import DocumentProcessingOutputRepository

                repository = DocumentProcessingOutputRepository()
                parser_metadata = selected_output.get("metadata") or {}
                document_id = f"PARSER-{selected_id}"
                element_count, table_count = repository.save_parser_output(
                    document_id=document_id,
                    title=Path(selected_manifest["filename"]).stem,
                    file_format=Path(selected_manifest["filename"]).suffix.lstrip(".").upper(),
                    source_sha256=selected_manifest["source_sha256"],
                    pipeline_id=str(parser_metadata.get("pipeline_id") or parser_metadata.get("parser_engine") or "docling"),
                    elements=elements,
                    tables=selected_output.get("tables", []),
                    document_metadata={
                        **parser_metadata,
                        "filename": selected_manifest["filename"],
                        "source_sha256": selected_manifest["source_sha256"],
                        "local_parser_run_id": selected_id,
                        "chunking_applied": False,
                        "embeddings_created": False,
                    },
                )
                st.success(
                    f"Saved {element_count:,} parser elements and {table_count:,} structured tables to Supabase · {document_id} · no chunks or embeddings created."
                )
            except Exception as error:
                st.error(f"Supabase parser-output upload failed: {error}")
            finally:
                if repository is not None:
                    repository.close()

        run_dir = STORE_DIR / selected_id
        source_path = run_dir / "source"
        page_tab, raw_tab, tables_tab, handoff_tab, details_tab = st.tabs(
            ["Page review", "Raw text", "Tables", "Text elements", "Run details"]
        )
        with page_tab:
            page_count = _page_count(run_dir) if source_path.is_file() else 0
            if page_count:
                page_number = 1
                if page_count > 1:
                    page_number = st.selectbox(
                        "Page",
                        range(1, page_count + 1),
                        format_func=lambda number: f"Page {number}",
                    )
                if page_count == 1:
                    page_elements = elements
                    page_tables = selected_output.get("tables", [])
                else:
                    page_elements = [
                        element for element in elements
                        if (element.get("metadata") or {}).get("page_number") is not None
                        and int(element["metadata"]["page_number"]) == page_number
                    ]
                    page_tables = []
                    for table in selected_output.get("tables", []):
                        table_page = table.get("page_number")
                        if table_page is None:
                            table_page = (table.get("metadata") or {}).get("page_number")
                        if table_page is not None and int(table_page) == page_number:
                            page_tables.append(table)

                raw_column, extracted_column = st.columns(2, gap="large")
                with raw_column:
                    with st.container(border=True):
                        st.subheader(f"Page preview · {page_number}")
                        preview = _page_preview(run_dir, page_number)
                        if preview is not None:
                            show_boxes = st.checkbox("Show bounding boxes", value=True)
                            if show_boxes:
                                page_sizes = selected_output.get("page_sizes") or {}
                                preview = _page_preview_with_boxes(
                                    preview,
                                    page_elements,
                                    page_tables,
                                    page_sizes.get(str(page_number)),
                                    default_origin=(
                                        "BOTTOMLEFT"
                                        if Path(selected_manifest["filename"]).suffix.lower() == ".pdf"
                                        else "TOPLEFT"
                                    ),
                                )
                            st.image(preview, use_container_width=True)
                        else:
                            st.info("Source page preview is not available for this file.")
                with extracted_column:
                    with st.container(border=True):
                        st.subheader("Extracted output")
                        st.caption(f"{len(page_elements):,} elements · {len(page_tables):,} tables")
                        if not page_elements:
                            st.info("No document elements were extracted from this page.")
                        for index, element in enumerate(page_elements, 1):
                            metadata = element.get("metadata", {})
                            element_type = normalize_element_label(
                                metadata.get("element_type") or metadata.get("layout_type") or metadata.get("docling_label")
                            )
                            st.markdown(f"**Element {index} · {element_type}**")
                            st.text(element.get("text") or "[Table reference]")
                        for index, table in enumerate(page_tables, 1):
                            st.markdown(f"**{_table_display_name(table, index)}**")
                            st.dataframe(table.get("rows", []), hide_index=True, use_container_width=True)
            else:
                st.info("This file type has no page preview. Download the original file from Run details.")
                if elements:
                    st.subheader("Extracted output")
                    for index, element in enumerate(elements, 1):
                        metadata = element.get("metadata", {})
                        element_type = normalize_element_label(
                            metadata.get("element_type")
                            or metadata.get("layout_type")
                            or metadata.get("docling_label")
                        )
                        st.markdown(f"**Element {index} · {element_type}**")
                        st.text(element.get("text") or "[Table reference]")
        with raw_tab:
            if raw_text:
                st.caption("Extracted text, in document reading order.")
                st.code(raw_text, language="text", wrap_lines=True)
            else:
                st.info("No raw text was extracted from this document.")
        with tables_tab:
            tables = selected_output.get("tables", [])
            if not tables:
                st.info("No structured tables were extracted.")
            for index, table in enumerate(tables, 1):
                st.markdown(f"**{_table_display_name(table, index)}**")
                st.dataframe(table.get("rows", []), hide_index=True, use_container_width=True)
        with handoff_tab:
            st.caption(
                "Inspect the ordered elements that will be passed to chunking."
            )
            furniture_elements = [
                element
                for element in elements
                if (element.get("metadata") or {}).get("element_type")
                in {"page_header", "page_footer"}
            ]
            if furniture_elements:
                st.markdown("**Page headers and footers**")
                for element in furniture_elements:
                    element_type = element["metadata"]["element_type"]
                    st.markdown(f"**{element_type}** · {element.get('text') or '[No text]'}")
            else:
                st.caption("No page_header or page_footer elements in this saved run.")
            page_numbers = sorted({
                int(element["metadata"]["page_number"])
                for element in elements
                if (element.get("metadata") or {}).get("page_number") is not None
            })
            if page_numbers:
                handoff_page = st.selectbox(
                    "Parser data page",
                    page_numbers,
                    index=page_numbers.index(26) if 26 in page_numbers else 0,
                    format_func=lambda number: f"Page {number}",
                    key="handoff_page",
                )
                page_elements = [
                    element for element in elements
                    if (element.get("metadata") or {}).get("page_number") == handoff_page
                ]
                st.caption(f"{len(page_elements)} ordered elements on this page.")
                st.json(page_elements, expanded=True)
            else:
                st.caption("This format has no page numbers, so all ordered elements are shown.")
                st.json(elements, expanded=True)
        with details_tab:
            run_config = selected_manifest.get("config") or {}
            source_suffix = Path(selected_manifest["filename"]).suffix.lower()
            uses_pdf_pipeline = source_suffix in {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff"}
            if uses_pdf_pipeline:
                layout_model = "Docling Heron (`docling-project/docling-layout-heron`)"
                table_recognition_model = (
                    "Docling TableFormer (Accurate, cell matching)"
                    if run_config.get("docling_table_structure", True)
                    else "Disabled"
                )
                if not run_config.get("docling_ocr", True):
                    text_recognition_model = "OCR disabled (Docling native text)"
                elif run_config.get("docling_ocr_engine", "tesseract") == "vietocr":
                    text_recognition_model = "VietOCR vgg_seq2seq (greedy, 512 px)"
                else:
                    language = run_config.get("docling_ocr_language", "vie")
                    text_recognition_model = f"Tesseract (language: {language}, PSM 6)"
            else:
                text_recognition_model = "Docling native text extraction (no OCR model)"
                layout_model = "Docling native document structure (no page layout model)"
                table_recognition_model = "Docling native table extraction"
            st.write(f'**File:** {selected_manifest["filename"]}')
            st.write(f'**Processed:** {selected_manifest["processed_at"][:19].replace("T", " ")} UTC')
            st.write(f'**Parser:** {selected_manifest.get("config", {}).get("parser_engine", "docling")}')
            st.write(f"**Text recognition model:** {text_recognition_model}")
            st.write(f"**Layout model:** {layout_model}")
            st.write(f"**Table recognition model:** {table_recognition_model}")
            st.write(f'**SHA-256:** `{selected_manifest["source_sha256"]}`')
            if source_path.is_file():
                st.download_button(
                    "Download original file",
                    source_path.read_bytes(),
                    file_name=selected_manifest["filename"],
                    mime="application/octet-stream",
                )
            st.json(selected_output.get("metadata", {}))
