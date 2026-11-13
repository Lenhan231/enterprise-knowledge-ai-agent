# Parser output and metadata

This page describes the current `DocumentProcessor` result. It is not a
database schema or a strict allowlist: callers can add source/business context,
and parser routes can add optional fields.

## Top-level result

The common shape is:

```json
{
  "elements": [],
  "tables": [],
  "metadata": {}
}
```

Optional route-specific data includes `layout_detections`,
`page_orientation_corrections`, `page_sizes`, `page_previews`,
`invoice_extraction`, and `image_caption_extraction`. For route behavior, see
the [architecture](architecture.md), [Docling](docling-pipeline.md), and
[Vintern](vintern-pipeline.md) pages.

## Common element and table fields

| Field | Where | Meaning |
| --- | --- | --- |
| `filename` | element/table metadata and run metadata | Original uploaded filename |
| `format` | element/table metadata and run metadata | File format, such as `PDF`, `DOCX`, or `CSV` |
| `pipeline_id` | element/table metadata and run metadata | Selected route, e.g. `docling`, `docling_qwen_invoice_text`, or `vintern_image_caption` |
| `parser_engine` | element/table metadata and run metadata | Parser route selected by the caller |
| `parser` | element/table metadata | Component that produced the content, commonly `docling` or `vintern_*` |
| `text_extraction_method` | element/table metadata | Method used to produce text, such as `docling.native`, `docling.vietocr`, or `docling.tesseract` |
| `page_number` | element/table metadata when applicable | Source page; removed for standalone PNG/JPEG/SVG/WebP inputs |
| `bbox` | element metadata when available | Source location; `bbox_coordinate_system` describes its coordinates |
| `element_type`, `layout_type` | element/table metadata | Normalized shared element label |

An element contains `text`, `element_type`, and `metadata`; table markers can
reference a separate table through `table_ref`. Structured tables contain
`columns`, `rows`, and `metadata`. Parser output order is retained for
downstream chunking.

## Route-specific metadata

### Docling

- Run metadata records `parser_engine="docling"` and, for PDF, the selected
  `pdf_processing_route` (`layout_region_ocr` for VietOCR or `full_page_ocr`
  for Tesseract) plus OCR flags.
- `layout_detections` preserves raw PP-DocLayoutV3 labels, scores, page boxes,
  and coordinate conventions; normalized `elements` use the shared taxonomy.
- Chart metadata can include chart/title crop association and external
  recognition details. Tables can include `table_structure_model` and dash
  recovery metadata.

### Invoice text extraction

- Run metadata records `pipeline_id="docling_qwen_invoice_text"` and
  `parser_engine="docling"`, plus the model/revision and review status.
- `invoice_extraction.fields` is the schema-checked `invoice.v1` draft; raw
  model output and inference metrics remain in extraction metadata.
- Docling elements and structured tables retain their normal OCR/parser
  provenance; the text model does not emit or alter those results.

### Vintern

- Run metadata records `pipeline_id="vintern_image_caption"`, model/revision,
  and review status.
- `image_caption_extraction.pages` keeps raw page responses and captions.
- Vintern currently emits text elements and no structured tables.

## Parser output versus chunk metadata

Parser output is normalized in `document_processing`. The chunking stage adds
chunk-specific fields such as `chunk_index`, `actual_char_count`, and
`table_index`; those fields do not belong to every raw parser element. See the
[chunking guide](../../core/chunking/README.md) for how tables and elements
become parser chunks.

Production upload can add document/business access context. Upload Test adds
`source_type="upload_test"` and `source_sha256` and uses isolated review
storage. `format` is the file extension; `document_type` is a business
classification supplied by the caller.
