"""Map persisted parser output to the shared chunking input contract."""

from copy import deepcopy
import math

from core.chunking.table.references import resolve_table_references


def map_output(row: dict, document: dict) -> tuple[dict, list[str]]:
    """Restore text/table references while retaining the untouched source separately."""
    warnings = []
    elements = []
    common = {
        **row["document_metadata"],
        "document_id": row["document_id"],
        "document_title": document["title"],
        "domain": document["domain"],
        "document_type": document["document_type"],
        "allowed_roles": document["allowed_roles"] or [],
    }
    if not common.get("company"):
        warnings.append("Company is missing; resolve document scope before indexing.")
    if not common["allowed_roles"]:
        warnings.append("allowed_roles is empty: deny access; do not activate this document for retrieval.")
    if not document.get("knowledge_base_active"):
        warnings.append("Document is inactive for the knowledge base.")

    if "elements" in row:
        for field in ("elements", "tables"):
            if not isinstance(row.get(field), list) or any(not isinstance(v, dict) for v in row[field]):
                raise ValueError(f"{field} must be an array of objects")
        tables = deepcopy(row["tables"])
        for index, table in enumerate(tables):
            if not isinstance(table.get("rows"), list) or any(not isinstance(r, dict) for r in table["rows"]):
                raise ValueError("Table rows must be an array of objects")
            table["metadata"] = {**common, **(table.get("metadata") or {}),
                                 "document_id": row["document_id"], "allowed_roles": common["allowed_roles"],
                                 "source_elements": [{"field": "tables", "index": index}]}
        referenced = resolve_table_references(row["elements"], tables)
        for index, source in enumerate(row["elements"]):
            element = deepcopy(source)
            if "table_ref" in element:
                ref = element["table_ref"]
                source_index, source_metadata = referenced[ref]
                if index != source_index:
                    continue
            else:
                source_metadata = element.get("metadata") or {}
            metadata = {**common, **source_metadata,
                        "document_id": row["document_id"], "allowed_roles": common["allowed_roles"],
                        "source_elements": [{"field": "elements", "index": index}]}
            kind = metadata.get("element_type") or metadata.get("layout_type") or element.get("element_type") or "text"
            if kind in {"figure", "seal"}:
                continue
            if kind == "table":
                ref = element.get("table_ref")
                metadata = {**tables[ref]["metadata"], **metadata,
                            "element_type": "table", "layout_type": "table"}
                metadata["source_elements"].append({"field": "tables", "index": ref})
            elif not isinstance(element.get("text"), str):
                raise ValueError("Text elements must contain string text")
            element["metadata"] = metadata
            elements.append(element)
        if len(referenced) != len(tables):
            warnings.append("Unreferenced tables will follow the elements; verify source ordering.")
        warnings.append("Stored elements order retained; migrated legacy rows may have reconstructed cross-type order.")
        return {"metadata": {**common, "reading_order_method": "stored_elements_order"},
                "elements": elements, "tables": tables}, warnings

    for field in ("text_elements", "structured_tables", "figures"):
        if not isinstance(row[field], list) or any(not isinstance(v, dict) for v in row[field]):
            raise ValueError(f"{field} must be an array of objects")
    tables = deepcopy(row["structured_tables"])
    for field, items in (("text_elements", row["text_elements"]), ("structured_tables", tables)):
        for index, item in enumerate(items):
            metadata = {**common, **deepcopy(item.get("metadata") or {})}
            metadata.update({"document_id": row["document_id"], "allowed_roles": common["allowed_roles"]})
            metadata["source_elements"] = [{"field": field, "index": index}]
            element = deepcopy(item)
            if field == "structured_tables":
                if not isinstance(item.get("rows"), list) or any(not isinstance(r, dict) for r in item["rows"]):
                    raise ValueError("Table rows must be an array of objects")
                metadata.update({"element_type": "table", "layout_type": "table"})
                metadata["page_number"] = item.get("page_number", metadata.get("page_number"))
                item["metadata"] = deepcopy(metadata)
                element = {"table_ref": index}
            elif not isinstance(item.get("text"), str):
                raise ValueError("Text elements must contain string text")
            element["metadata"] = metadata
            element["source_order"] = item.get("source_order", metadata.get("source_order"))
            elements.append(element)

    orders = [e["source_order"] for e in elements]
    if elements and all(type(v) is int and v >= 0 for v in orders) and len(set(orders)) == len(orders):
        elements.sort(key=lambda e: e["source_order"])
        ordering = "source_order"
    else:
        # shortcut: geometric reading order is approximate; use parser source_order when available.
        ordering = "page_bbox_approximation"
        warnings.append("Reading order inferred from page/bbox; multi-column order and table context require visual review.")

        def position(element: dict) -> tuple:
            m = element["metadata"]
            page, box = m.get("page_number"), m.get("bbox")
            valid_box = isinstance(box, list) and len(box) == 4 and all(
                isinstance(v, (int, float)) and math.isfinite(v) for v in box
            )
            origin = m.get("bbox_coordinate_origin")
            if not isinstance(page, int) or not valid_box or origin not in {"BOTTOMLEFT", "TOPLEFT"}:
                warnings.append("Some elements lack usable page/bbox coordinates; unresolved positions sort last on their page.")
                return (page if isinstance(page, int) else math.inf, math.inf, math.inf)
            top = -max(box[1], box[3]) if origin == "BOTTOMLEFT" else min(box[1], box[3])
            return page, top, min(box[0], box[2])

        elements.sort(key=position)
    for element in elements:
        element.pop("source_order", None)
    return {"metadata": {**common, "reading_order_method": ordering}, "elements": elements, "tables": tables}, list(dict.fromkeys(warnings))
