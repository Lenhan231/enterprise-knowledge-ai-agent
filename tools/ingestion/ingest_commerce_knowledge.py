#!/usr/bin/env python3
"""Download and index approved Commerce decision-support references."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
APPROVED_HOSTS = {
    "seller-vn.tiktok.com",
    "corporate.walmart.com",
    "marketplace.walmart.com",
    "cdngarenanow-a.akamaihd.net",
    "help.shopee.vn",
    "help.shopify.com",
    "www.shopify.com",
    "shopify.com",
    "advertising.amazon.com",
    "m.media-amazon.com",
    "supplychain.amazon.com",
    "advertising.doordash.com",
    "www.thekrogerco.com",
    "hocvien.tiki.vn",
    "business.gov.au",
    "iabeurope.eu",
}
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from core.database.document_chunks_repository import DocumentChunkRepository  # noqa: E402
from core.database.document_repository import DocumentRepository  # noqa: E402
from core.database.processed_chunks_repository import ProcessedChunksRepository  # noqa: E402
from core.database.structured_store import StructuredDataStore  # noqa: E402
from core.document_processing.ingest_documents import Ingestion  # noqa: E402
from core.embeddings import EmbeddingService  # noqa: E402


def download(url: str) -> tuple[bytes, str]:
    if urlparse(url).scheme != "https" or urlparse(url).hostname not in APPROVED_HOSTS:
        raise ValueError(f"Unapproved source host/path: {url}")
    request = Request(url, headers={"User-Agent": "CommerceKnowledgeResearch/1.0"})
    with urlopen(request, timeout=30) as response:
        if response.status != 200:
            raise RuntimeError(f"HTTP {response.status} for {url}")
        final_host = urlparse(response.geturl()).hostname
        if final_host not in APPROVED_HOSTS:
            raise ValueError(f"Redirected to unapproved source host: {final_host}")
        content_type = response.headers.get_content_type()
        content = response.read()
        expected_type = "application/pdf" if url.lower().endswith(".pdf") else "text/html"
        if content_type != expected_type:
            raise ValueError(f"Expected {expected_type}, received {content_type} for {url}")
        if expected_type == "application/pdf" and not content.startswith(b"%PDF-"):
            raise ValueError(f"PDF signature missing for {url}")
        return content, expected_type


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ids", nargs="*", help="Source IDs from data/commerce_knowledge/manifest.json")
    parser.add_argument("--download-only", action="store_true", help="Fetch registered sources without writing to the database")
    args = parser.parse_args()
    manifest_path = ROOT / "data/commerce_knowledge/manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    sources = [item for item in manifest["sources"] if item.get("retrieval_status") == "active"]
    if args.ids:
        by_id = {item["source_id"]: item for item in sources}
        unknown = set(args.ids) - by_id.keys()
        if unknown:
            parser.error("unknown source IDs: " + ", ".join(sorted(unknown)))
        sources = [by_id[source_id] for source_id in args.ids]

    raw_root = ROOT / "data/raw/commerce_knowledge"
    processed_root = ROOT / "data/processed/commerce_knowledge"
    raw_root.mkdir(parents=True, exist_ok=True)
    files = []
    for source in sources:
        if source.get("local_path"):
            local_path = (ROOT / source["local_path"]).resolve()
            if ROOT not in local_path.parents:
                raise ValueError(f"Local source escapes repository root: {source['local_path']}")
            content = local_path.read_bytes()
            content_type = "application/pdf" if content.startswith(b"%PDF-") else ""
            if content_type != "application/pdf":
                raise ValueError(f"Local policy is not a PDF: {source['local_path']}")
            suffix = ".pdf"
            path = local_path
        else:
            content, content_type = download(source["url"])
            suffix = ".pdf" if content_type == "application/pdf" else ".html"
            path = raw_root / f"{source['source_id']}{suffix}"
            path.write_bytes(content)
        digest = hashlib.sha256(content).hexdigest()
        source["content_sha256"] = digest
        source["last_fetched_on"] = date.today().isoformat()
        source["ingestion_status"] = "downloaded_not_ingested"
        source["ingested_format"] = suffix.removeprefix(".").upper()
        files.append((source, path, digest))
        print(f"downloaded {source['source_id']} format={source['ingested_format']} sha256={digest} bytes={len(content)}")

    if args.download_only:
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return 0

    embedding = EmbeddingService()
    ingestor = Ingestion(embedding, chunking_strategy="sentence", extract_tables=True)
    documents = DocumentRepository()
    chunks = DocumentChunkRepository()
    parsed = ProcessedChunksRepository()
    tables = StructuredDataStore()
    roles = [
        "employee", "finance_analyst", "sustainability_analyst", "procurement",
        "operations", "legal_compliance", "executive", "admin",
    ]
    failures = 0
    try:
        for source, path, digest in files:
            document_id = source["source_id"]
            metadata = {
                "document_id": document_id,
                "company": "Commerce Demo",
                "domain": source["domains"][0],
                "title": source["title"],
                "document_type": source.get("document_type", "platform_operating_guidance"),
                "fiscal_year": None,
                "language": source.get("language", "en"),
                "source_type": source.get("source_type", "public_enterprise_document"),
                "year_or_version": source["published_or_updated"],
                "source_url": source.get("url"),
                "source_sha256": digest,
                "source_publisher": source["publisher"],
                "source_updated": source["published_or_updated"],
                "external_policy_reference": source.get(
                    "external_policy_reference",
                    source.get("evidence_class") == "platform_operating_rule",
                ),
                "synthetic_company_policy": source.get("synthetic_company_policy") is True,
                "external_business_reference": source.get("evidence_class") in {
                    "company_practice_reference", "management_cookbook_reference",
                },
                "external_management_reference": source.get("evidence_class") == "management_cookbook_reference",
                "evidence_class": source.get("evidence_class", "platform_operating_rule"),
                "source_license": source.get("license"),
                "source_rights_url": source.get("rights_url"),
                "source_attribution": source.get("attribution"),
                "knowledge_domains": source["domains"],
                "commerce_reference_active": source.get("retrieval_status") == "active",
                "reference_applicability": source.get("applicability"),
                "source_notes": source.get("notes") if source.get("synthetic_company_policy") is True else None,
                "source_notes_en": source.get("notes_en") if source.get("synthetic_company_policy") is True else None,
                "allowed_roles": roles,
            }
            documents.upsert_document({
                **metadata,
                "format": source["ingested_format"],
                "verification": (
                    f"Synthetic demo policy; not a real company policy; SHA-256 {digest}"
                    if source.get("synthetic_company_policy") is True
                    else f"Approved public operating reference; downloaded SHA-256 {digest}"
                ),
                "storage_path": None,
                "processing_status": "processing",
                "knowledge_base_active": source.get("retrieval_status") == "active",
            })
            try:
                parsed_chunks, extracted_tables = ingestor.ingestion(
                    path, processed_root, document_id=document_id,
                    extra_metadata=metadata, include_tables=True,
                )
                if not parsed_chunks:
                    raise ValueError("No readable page text was extracted")
                tables.save_document_tables(document_id, source["title"], extracted_tables)
                parsed.replace_document(document_id, [
                    {"text": chunk.page_content, "metadata": chunk.metadata}
                    for chunk in parsed_chunks
                ])
                parsed.set_status(document_id, "embedding")
                vectors = embedding.embed_documents([chunk.page_content for chunk in parsed_chunks])
                rows = []
                for index, (chunk, vector) in enumerate(zip(parsed_chunks, vectors, strict=True)):
                    chunk.metadata["embedding_model"] = embedding.model_name
                    chunk.metadata["allowed_roles"] = roles
                    rows.append((path.name, index, chunk.page_content, chunk.metadata, vector))
                chunks.replace_document(document_id, rows)
                parsed.set_status(document_id, "embedded")
                documents.update_processing_status(document_id, "ready")
                source["ingestion_status"] = "indexed"
                print(f"indexed    {document_id}: {len(rows)} chunks")
            except Exception as error:
                documents.update_processing_status(document_id, "failed")
                parsed.set_status(document_id, "failed", str(error))
                source["ingestion_status"] = "failed"
                print(f"failed     {document_id}: {error}", file=sys.stderr)
                failures += 1
    finally:
        chunks.close()
        parsed.close()
        tables.close()
        documents.close()
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
