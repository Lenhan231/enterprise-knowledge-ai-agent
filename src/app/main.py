from pathlib import Path
from contextlib import asynccontextmanager
import hashlib
import json
import logging
import os
import re
import time
import secrets
import uuid
from typing import Annotated, Literal
import jwt

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator
from urllib.parse import quote, urlsplit
from dotenv import load_dotenv

from core.database.document_repository import DocumentRepository
from core.analytics.commerce_decision_support import COMMERCE_DECISION_PROFILES
from supabase import create_client
from app.security import (
    DOCUMENT_ROLES, ROLE_PERMISSIONS, _current_user, _is_trusted_frontend_origin,
    _require_same_origin,
    _roles_with_permission, auth_scheme, require_permission, require_roles,
)
from app.agents import router as agents_router
from app.upload_test import (
    create_upload_test, get_upload_test_preview, inspect_upload_test,
    list_upload_tests, router as upload_test_router,
)

logger = logging.getLogger(__name__)
@asynccontextmanager
async def _lifespan(application: FastAPI):
    load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
    if os.getenv("RERANKER_PRELOAD") == "1":
        from core.retrieval.reranker import _load_model
        _load_model()
    yield
    runtime = getattr(application.state, "agent_router", None)
    if runtime is not None:
        await runtime.close()


app = FastAPI(title="Commerce Decision Support", lifespan=_lifespan)
app.include_router(upload_test_router)
app.include_router(agents_router)

APP_DIR = Path(__file__).resolve().parent
STATIC_DIR = APP_DIR / "static"
# The demo no longer depends on a seed-company manifest.
CORPUS_COMPANY = os.getenv("COMMERCE_DEMO_COMPANY", "Commerce Demo")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
OCR_LANGUAGES = {"eng", "vie+eng"}


def _storage_client():
    url = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL")
    key = os.getenv("SUPABASE_SECRET_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise HTTPException(503, "SUPABASE_URL and server-only SUPABASE_SECRET_KEY are required for uploads")
    if os.getenv("SUPABASE_DOCUMENT_BUCKET", "enterprise-documents") != "enterprise-documents":
        raise HTTPException(503, "SUPABASE_DOCUMENT_BUCKET must match the private enterprise-documents bucket")
    return create_client(url, key), os.getenv("SUPABASE_DOCUMENT_BUCKET", "enterprise-documents")


def _role_accounts() -> dict[str, tuple[str, str]]:
    accounts = {}
    for role in ("admin", "analyst", "viewer", "sustainability_analyst", "document_processing_owner"):
        username = os.getenv(f"DEMO_{role.upper()}_USERNAME")
        password = os.getenv(f"DEMO_{role.upper()}_PASSWORD")
        if username and password:
            accounts[username] = (password, role)
    # Map the existing demo identities to document groups. Admin can inspect all groups.
    role_map = {"viewer": "employee", "analyst": "finance_analyst", "admin": "admin"}
    uploader_username = os.getenv("DEMO_UPLOADER_USERNAME")
    uploader_password = os.getenv("DEMO_UPLOADER_PASSWORD")
    if uploader_username and uploader_password:
        accounts[uploader_username] = (uploader_password, "document_uploader")
    return {username: (password, role_map.get(role, role)) for username, (password, role) in accounts.items()}


def _issue_token(username: str, role: str) -> str:
    secret = os.getenv("AUTH_SECRET_KEY", "")
    if len(secret) < 32:
        raise HTTPException(503, "AUTH_SECRET_KEY must contain at least 32 characters")
    return jwt.encode({"sub": username, "role": role, "exp": int(time.time()) + 3600}, secret, algorithm="HS256")


def _commerce_reference_metadata(
    knowledge_domains: list[str], source_publisher: str | None, reference_type: str,
    reference_applicability: str | None = None,
    synthetic_company_policy: bool = False,
) -> dict:
    domains = list(dict.fromkeys(value.strip() for value in knowledge_domains if value.strip()))
    known_domains = set(COMMERCE_DECISION_PROFILES)
    if set(domains) - known_domains:
        raise HTTPException(422, "Choose only supported Commerce decision domains")

    reference_type = reference_type.strip()
    supported_types = {
        "management_cookbook_reference", "company_practice_reference",
        "company_policy_reference", "platform_operating_rule",
    }
    if reference_type and reference_type not in supported_types:
        raise HTTPException(422, "Choose a supported Commerce reference type")
    publisher = source_publisher.strip() if source_publisher else ""
    applicability = reference_applicability.strip() if reference_applicability else ""
    if bool(domains) != bool(reference_type):
        raise HTTPException(422, "Commerce references require both a type and at least one decision domain")
    if reference_type and not publisher:
        raise HTTPException(422, "Commerce references require the source publisher")
    if reference_type and not applicability:
        raise HTTPException(422, "Commerce references require an applicability scope")
    if synthetic_company_policy:
        if reference_type != "company_policy_reference":
            raise HTTPException(422, "Synthetic Commerce Demo documents must be classified as company policies")
        if publisher != "Commerce Demo (fictional organization)":
            raise HTTPException(422, "Synthetic policies must use the Commerce Demo fictional publisher")
        if not any(term in applicability.casefold() for term in ("fictional", "giả lập", "demo")):
            raise HTTPException(422, "Synthetic policy scope must explicitly identify the fictional demo")

    evidence_class = reference_type or None
    return {
        "knowledge_domains": domains,
        "source_publisher": publisher or None,
        "reference_applicability": applicability or None,
        "evidence_class": evidence_class,
        "external_reference_type": reference_type or None,
        "external_policy_reference": reference_type == "platform_operating_rule",
        "external_business_reference": reference_type == "company_practice_reference" or (
            reference_type == "company_policy_reference" and not synthetic_company_policy
        ),
        "synthetic_company_policy": synthetic_company_policy,
        "commerce_reference_active": bool(domains),
    }




class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=200)


class KnowledgeBaseStatusRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    active: bool


class DocumentAccessRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    allowed_roles: list[str] = Field(min_length=1, max_length=len(DOCUMENT_ROLES))

    @field_validator("allowed_roles")
    @classmethod
    def validate_allowed_roles(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)) or set(value) - DOCUMENT_ROLES:
            raise ValueError("Choose each valid document role at most once")
        return value


@app.get("/", include_in_schema=False)
def home():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/auth/login")
def login(request: Request, payload: LoginRequest):
    accounts = _role_accounts()
    account = accounts.get(payload.username)
    if account is None or not secrets.compare_digest(account[0], payload.password):
        raise HTTPException(401, "Invalid username or password")
    response = JSONResponse({"username": payload.username, "role": account[1], "expires_in": 3600})
    secure_cookie = os.getenv("AUTH_COOKIE_SECURE", "false").lower() == "true" \
        or _is_trusted_frontend_origin(request.headers.get("origin"))
    response.set_cookie("enterprise_session", _issue_token(payload.username, account[1]), httponly=True, secure=secure_cookie, samesite="lax", max_age=3600, path="/")
    return response


@app.get("/api/auth/me")
def who_am_i(user: dict = Depends(require_roles(*ROLE_PERMISSIONS.keys()))):
    return {"username": user["sub"], "role": user["role"]}


@app.post("/api/auth/logout")
def logout():
    response = JSONResponse({"status": "signed_out"})
    response.delete_cookie("enterprise_session", path="/")
    return response


@app.get("/api/dashboard")
def dashboard_data(user: dict = Depends(require_permission("view_corpus"))):
    repository = None
    try:
        repository = DocumentRepository()
        return repository.corpus_dashboard(
            user["role"], user["sub"],
        )
    except Exception as error:
        logger.exception("Could not load the enterprise document overview")
        raise HTTPException(
            status_code=503,
            detail="The enterprise knowledge database is unavailable. Check DATABASE_URL and migrations.",
        ) from error
    finally:
        if repository is not None:
            repository.close()


@app.get("/api/documents/upload-capability")
def upload_capability(user: dict = Depends(require_permission("view_corpus"))):
    return {"can_upload": "upload_documents" in ROLE_PERMISSIONS[user["role"]]}


@app.get("/api/documents/roles")
def document_roles(user: dict = Depends(require_permission("classify_documents"))):
    return {"roles": sorted(DOCUMENT_ROLES)}


@app.get("/api/admin/knowledge-documents")
def admin_knowledge_documents(user: dict = Depends(require_permission("list_processing_documents"))):
    repository = None
    try:
        repository = DocumentRepository()
        return {"documents": repository.list_knowledge_documents()}
    except Exception as error:
        logger.exception("Could not list knowledge-base documents")
        raise HTTPException(503, "Knowledge-base document management is unavailable") from error
    finally:
        if repository is not None:
            repository.close()


def _synthetic_policy_file_response(document_id: str) -> Response:
    """Resolve a synthetic policy PDF only through the checked-in corpus manifest."""
    root = Path(__file__).resolve().parents[2]
    manifest_path = root / "data/commerce_knowledge/manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        logger.exception("Could not read the Commerce knowledge manifest")
        raise HTTPException(503, "Commerce policy sources are unavailable") from error

    source = next((item for item in manifest.get("sources", [])
                   if item.get("source_id") == document_id
                   and item.get("synthetic_company_policy") is True), None)
    if source is None or not source.get("local_path"):
        raise HTTPException(404, "Synthetic policy PDF not found")

    policy_root = (root / "data/commerce_knowledge/synthetic_policies").resolve()
    file_path = (root / source["local_path"]).resolve()
    if policy_root not in file_path.parents or file_path.suffix.lower() != ".pdf":
        raise HTTPException(404, "Synthetic policy PDF not found")
    if not file_path.is_file():
        raise HTTPException(404, "Synthetic policy PDF not found")

    return FileResponse(
        file_path,
        media_type="application/pdf",
        filename=file_path.name,
        content_disposition_type="inline",
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )


@app.get("/api/admin/knowledge-documents/{document_id}/source")
def open_synthetic_policy_source(
    document_id: str,
    user: dict = Depends(require_permission("manage_knowledge")),
):
    """Open only synthetic policy PDFs explicitly registered by the local manifest."""
    return _synthetic_policy_file_response(document_id)


@app.patch("/api/admin/knowledge-documents/{document_id}")
def set_knowledge_document_status(
    document_id: str,
    request: KnowledgeBaseStatusRequest,
    http_request: Request,
    user: dict = Depends(require_permission("manage_knowledge")),
):
    _require_same_origin(http_request)
    repository = None
    try:
        repository = DocumentRepository()
        if not repository.set_knowledge_base_active(document_id, request.active):
            raise HTTPException(404, "Knowledge document not found")
        return {"document_id": document_id, "active": request.active}
    except HTTPException:
        raise
    except Exception as error:
        logger.exception("Could not update knowledge-base document %s", document_id)
        raise HTTPException(503, "Knowledge-base document could not be updated") from error
    finally:
        if repository is not None:
            repository.close()


@app.patch("/api/admin/knowledge-documents/{document_id}/access")
def set_knowledge_document_access(
    document_id: str,
    request: DocumentAccessRequest,
    http_request: Request,
    user: dict = Depends(require_permission("manage_knowledge")),
):
    _require_same_origin(http_request)
    repository = None
    try:
        repository = DocumentRepository()
        if not repository.set_document_allowed_roles(document_id, request.allowed_roles):
            raise HTTPException(404, "Knowledge document not found")
        return {"document_id": document_id, "allowed_roles": request.allowed_roles}
    except HTTPException:
        raise
    except Exception as error:
        logger.exception("Could not update document access for %s", document_id)
        raise HTTPException(503, "Document access could not be updated") from error
    finally:
        if repository is not None:
            repository.close()


@app.post("/api/documents/parser-handoff")
@app.post("/api/documents/upload")
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    title: str = Form(...),
    document_type: str = Form(...),
    domain: str = Form(...),
    fiscal_year: int | None = Form(default=None),
    source_url: str | None = Form(default=None),
    knowledge_domains: Annotated[list[str], Form()] = [],
    source_publisher: Annotated[str | None, Form(max_length=200)] = None,
    reference_type: Annotated[str, Form(max_length=40)] = "",
    reference_applicability: Annotated[str | None, Form(max_length=1000)] = None,
    synthetic_company_policy: Annotated[bool, Form()] = False,
    allowed_roles: list[str] = Form(default=[]),
    ocr_language: str = Form(default="vie+eng"),
    user: dict = Depends(require_permission("upload_documents")),
):
    """Keep original bytes in private Storage; persist parsed evidence in PostgreSQL."""
    _require_same_origin(request)
    parser_handoff = request.url.path == "/api/documents/parser-handoff"
    filename = Path((file.filename or "").replace("\\", "/")).name
    extension = Path(filename).suffix.lower()
    from document_processing.document_processor import DocumentProcessor, SUPPORTED_FORMATS
    if not filename or extension not in SUPPORTED_FORMATS:
        raise HTTPException(415, "Supported formats: PDF, DOCX, PPTX, XLSX, CSV, TXT, MD, PNG, JPG, TIF")
    if not title.strip() or not document_type.strip() or not domain.strip():
        raise HTTPException(422, "Title, document type, and domain are required")
    if ocr_language not in OCR_LANGUAGES:
        raise HTTPException(422, "OCR language must be eng or vie+eng")
    # HTTP requests always receive a validated role from the auth dependency;
    # direct handler calls in unit tests omit it because they bypass dependencies.
    if synthetic_company_policy and user.get("role") not in (None, "admin"):
        raise HTTPException(403, "Only an admin can register a synthetic Commerce Demo policy")
    reference_metadata = _commerce_reference_metadata(
        knowledge_domains, source_publisher, reference_type, reference_applicability,
        synthetic_company_policy,
    )
    is_commerce_reference = bool(reference_metadata["knowledge_domains"])
    if not isinstance(source_url, str):
        source_url = None
    if source_url:
        parsed_source_url = urlsplit(source_url.strip())
        if parsed_source_url.scheme != "https" or not parsed_source_url.netloc:
            raise HTTPException(422, "Source URL must use HTTPS")
        source_url = source_url.strip()
    if not allowed_roles or set(allowed_roles) - DOCUMENT_ROLES:
        raise HTTPException(422, "Select one or more valid access roles")
    content = await file.read(50 * 1024 * 1024 + 1)
    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(413, "Maximum file size is 50 MiB")
    signatures = {".pdf": content.startswith(b"%PDF-"), ".png": content.startswith(b"\x89PNG\r\n\x1a\n"),
                  ".jpg": content.startswith(b"\xff\xd8\xff"), ".jpeg": content.startswith(b"\xff\xd8\xff"),
                  ".tif": content.startswith((b"II*\x00", b"MM\x00*")), ".tiff": content.startswith((b"II*\x00", b"MM\x00*"))}
    if extension in signatures and not signatures[extension]:
        raise HTTPException(415, "File content does not match its extension")

    document_id = f"UPLOAD-{uuid.uuid4().hex}"
    storage_path = f"{document_id}/{filename}"
    content_type = {".pdf": "application/pdf", ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    ".csv": "text/csv",
                    ".txt": "text/plain", ".md": "text/markdown", ".png": "image/png",
                    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".tif": "image/tiff", ".tiff": "image/tiff"}[extension]
    source_hash = hashlib.sha256(content).hexdigest()
    storage, bucket = _storage_client()
    repository = None
    uploaded = False
    registered = False
    try:
        storage.storage.from_(bucket).upload(
            storage_path, content,
            {"content-type": content_type, "upsert": "false"},
        )
        uploaded = True
        try:
            check = DocumentRepository()
        except Exception:
            storage.storage.from_(bucket).remove([storage_path])
            raise
        else:
            check.close()
        repository = DocumentRepository()
        repository.register_upload({
            "document_id": document_id,
            "domain": domain,
            "title": title.strip(),
            "year_or_version": str(fiscal_year) if fiscal_year else None,
            "format": extension[1:].upper(),
            "source_url": source_url,
            "verification": f"User upload SHA-256 {source_hash}",
            "document_type": document_type,
            "fiscal_year": str(fiscal_year) if fiscal_year else None,
            "company": CORPUS_COMPANY,
            "source_type": "user_upload",
            "allowed_roles": allowed_roles,
            "storage_path": storage_path,
            "uploaded_by": user["sub"],
            "processing_status": "uploaded",
        })
        registered = True
        repository.update_processing_status(document_id, "processing")
        from document_processing.document_processor import DocumentProcessor
        from core.database.parser_chunks_repository import ParserChunksRepository
        from core.database.structured_store import StructuredDataStore

        metadata = {
            "document_id": document_id,
            "company": CORPUS_COMPANY,
            "domain": domain,
            "title": title.strip(),
            "document_type": document_type,
            "fiscal_year": fiscal_year,
            "source_url": source_url,
            "source_type": "user_upload",
            "allowed_roles": allowed_roles,
            **reference_metadata,
        }
        if synthetic_company_policy:
            metadata["source_type"] = "synthetic_demo_policy"
        processor = DocumentProcessor({
            "parser_engine": "docling",
            "chunking_strategy": os.getenv("DOCUMENT_CHUNKING_STRATEGY", "sentence"),
            "paddle_layout": os.getenv("DOCUMENT_PADDLE_LAYOUT", "false").strip().lower() == "true",
            "paddle_chart_recognition": os.getenv(
                "DOCUMENT_PADDLE_CHART_RECOGNITION", "false",
            ).strip().lower() == "true",
            "paddle_formula_recognition": os.getenv(
                "DOCUMENT_PADDLE_FORMULA_RECOGNITION", "false",
            ).strip().lower() == "true",
            "vision_captioning": os.getenv("DOCUMENT_VISION_CAPTIONS", "false").strip().lower() == "true",
            "ocr_language": ocr_language,
        })
        try:
            from core.chunking.processor import ChunkingProcessor
            from core.database.document_processing_outputs_repository import (
                DocumentProcessingOutputsRepository,
            )

            parsed = processor.process(filename, content, metadata)
            outputs_repository = DocumentProcessingOutputsRepository()
            try:
                outputs_repository.replace_document(document_id, parsed)
            finally:
                outputs_repository.close()
            processed = ChunkingProcessor(processor.config).process(parsed)
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        parser_chunks = processed["chunks"]
        chunks = parser_chunks
        if not chunks:
            raise ValueError("No text could be extracted; check OCR availability or the source file")
        page_count = next((
            int(chunk["metadata"]["page_count"])
            for chunk in parser_chunks
            if chunk.get("metadata", {}).get("page_count") is not None
        ), 1 if extension in {".png", ".jpg", ".jpeg", ".tif", ".tiff"} else None)
        ocr_chunk_count = sum(
            bool(chunk.get("metadata", {}).get("ocr"))
            or bool(chunk.get("metadata", {}).get("ocr_model"))
            or chunk.get("metadata", {}).get("text_extraction_method") in {"tesseract", "pymupdf+tesseract"}
            for chunk in parser_chunks
        )
        for chunk in chunks:
            chunk["metadata"].pop("title", None)
            chunk["metadata"].pop("author", None)
        parsed_repository = ParserChunksRepository()
        try:
            parsed_repository.replace_document(document_id, chunks)
            structured_store = StructuredDataStore()
            try:
                structured_store.save_document_tables(document_id, title.strip(), processed["tables"])
            finally:
                structured_store.close()
        finally:
            parsed_repository.close()

        if parser_handoff:
            repository.update_processing_status(document_id, "parsed")
            return {
                "document_id": document_id, "storage_path": storage_path,
                "processing_status": "parsed", "searchable": False,
                "sha256": source_hash, "page_count": page_count,
                "parser_chunk_count": len(parser_chunks), "indexed_chunk_count": 0,
                "ocr_chunk_count": ocr_chunk_count,
                "table_count": len(processed.get("tables", [])),
            }

        from core.embeddings.embedding_service import EmbeddingService
        from core.database.document_chunks_repository import DocumentChunkRepository
        embedding_service = EmbeddingService()
        from core.tokenization.token_counter import TokenCounter
        from core.tokenization.embedding_chunker import build_embedding_chunks

        token_counter = TokenCounter(embedding_service.model_name)
        chunks = build_embedding_chunks(
            chunks,
            token_counter,
            embedding_service.max_sequence_length,
            embedding_service.model_name,
        )
        vectors = embedding_service.embed_documents([chunk["text"] for chunk in chunks])
        chunk_repository = DocumentChunkRepository()
        try:
            chunk_repository.replace_document(document_id, [
                (filename, index, chunk["text"],
                 {**chunk["metadata"], "document_id": document_id, "allowed_roles": allowed_roles}, vector)
                for index, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True))
            ])
        finally:
            chunk_repository.close()
        repository.update_processing_status(document_id, "ready")
        return {
            "document_id": document_id, "storage_path": storage_path,
            "processing_status": "ready", "searchable": True, "sha256": source_hash,
            "page_count": page_count, "parser_chunk_count": len(parser_chunks),
            "indexed_chunk_count": len(chunks), "ocr_chunk_count": ocr_chunk_count,
            "table_count": len(processed.get("tables", [])),
        }
    except HTTPException:
        if registered and repository is not None:
            try:
                repository.update_processing_status(document_id, "failed")
            except Exception:
                logger.exception("Failed to record rejected upload %s", document_id)
        raise
    except Exception as error:
        if uploaded and not registered:
            try:
                storage.storage.from_(bucket).remove([storage_path])
            except Exception:
                logger.exception("Failed cleaning unregistered storage upload %s", document_id)
        elif repository is not None:
            try:
                repository.update_processing_status(document_id, "failed")
            except Exception:
                logger.exception("Failed to record failed status for %s", document_id)
        logger.exception("Upload or processing failed for %s", document_id)
        raise HTTPException(503, "Upload or processing failed; see document status and app logs") from error
    finally:
        if repository is not None:
            repository.close()


@app.post("/api/admin/processing/{document_id}/retry-embedding")
def retry_document_embedding(
    document_id: str,
    request: Request,
    user: dict = Depends(require_permission("manage_knowledge")),
):
    """Embed retained parser output again without rerunning OCR or changing access scope."""
    from core.database.parser_chunks_repository import ParserChunksRepository

    _require_same_origin(request)
    document_repository = None
    parsed_repository = None
    try:
        document_repository = DocumentRepository()
        document = next((item for item in document_repository.list_knowledge_documents()
                         if item["document_id"] == document_id), None)
        if document is None:
            raise HTTPException(404, "Knowledge document not found")
        if document.get("source_type") != "user_upload" or document.get("processing_status") != "failed":
            raise HTTPException(409, "Only failed user uploads can retry embedding")

        parsed_repository = ParserChunksRepository()
        parsed_chunks = parsed_repository.get_document(document_id, company=CORPUS_COMPANY)
        if not parsed_chunks:
            raise HTTPException(409, "No saved parser output is available; upload the source again")

        filename = Path(str((parsed_chunks[0].get("metadata") or {}).get("filename") or "")).name
        if not filename:
            raise HTTPException(409, "The saved parser output has no source filename")
        allowed_roles = list(document.get("allowed_roles") or [])
        if not allowed_roles:
            raise HTTPException(409, "Assign at least one reader role before retrying embedding")

        document_repository.update_processing_status(document_id, "processing")
        from core.embeddings.embedding_service import EmbeddingService
        from core.tokenization.token_counter import TokenCounter
        from core.tokenization.embedding_chunker import build_embedding_chunks
        from core.database.document_chunks_repository import DocumentChunkRepository

        embedding_service = EmbeddingService()
        token_counter = TokenCounter(embedding_service.model_name)
        bounded_chunks = build_embedding_chunks(
            parsed_chunks,
            token_counter,
            embedding_service.max_sequence_length,
            embedding_service.model_name,
        )
        for chunk in bounded_chunks:
            chunk["metadata"].update({
                "document_id": document_id,
                "allowed_roles": allowed_roles,
            })
        if not bounded_chunks:
            raise ValueError("Saved parser output contains no embeddable text")

        vectors = embedding_service.embed_documents([chunk["text"] for chunk in bounded_chunks])
        if len(vectors) != len(bounded_chunks):
            raise ValueError("Embedding provider returned a different number of vectors than passages")
        chunk_repository = DocumentChunkRepository()
        try:
            chunk_repository.replace_document(document_id, [
                (filename, index, chunk["text"], chunk["metadata"], vector)
                for index, (chunk, vector) in enumerate(zip(bounded_chunks, vectors, strict=True))
            ])
        finally:
            chunk_repository.close()

        document_repository.update_processing_status(document_id, "ready")
        return {
            "document_id": document_id,
            "processing_status": "ready",
            "parser_chunk_count": len(parsed_chunks),
            "indexed_chunk_count": len(bounded_chunks),
            "embedding_model": embedding_service.model_name,
        }
    except HTTPException:
        raise
    except Exception as error:
        if document_repository is not None:
            try:
                document_repository.update_processing_status(document_id, "failed")
            except Exception:
                logger.exception("Could not record failed embedding retry for %s", document_id)
        logger.exception("Embedding retry failed for %s", document_id)
        raise HTTPException(503, "Embedding retry failed; the saved OCR and parser output were retained") from error
    finally:
        if parsed_repository is not None:
            parsed_repository.close()
        if document_repository is not None:
            document_repository.close()


@app.get("/api/admin/processing/{document_id}/chunks")
def inspect_processed_chunks(
    document_id: str, offset: int = 0, limit: int = 25,
    stage: Literal["parser", "indexed"] = "parser",
    source_chunk_id: int | None = None,
    user: dict = Depends(require_permission("process_documents")),
):
    from core.database.parser_chunks_repository import ParserChunksRepository

    repository = None
    try:
        chunks = []
        if stage == "parser":
            repository = ParserChunksRepository()
            chunks = repository.get_document(
                document_id, limit=limit, offset=offset, company=CORPUS_COMPANY,
            )
        actual_stage = stage
        if not chunks:
            from core.database.document_chunks_repository import DocumentChunkRepository

            indexed_repository = DocumentChunkRepository()
            try:
                if source_chunk_id is not None:
                    chunk = indexed_repository.get_document_chunk(
                        source_chunk_id, document_id, company=CORPUS_COMPANY,
                    )
                    chunks = [chunk] if chunk else []
                else:
                    chunks = indexed_repository.get_document_chunks(
                        document_id, limit=limit, offset=offset, company=CORPUS_COMPANY,
                    )
            finally:
                indexed_repository.close()
            actual_stage = "indexed"
        if not chunks:
            raise HTTPException(404, "No parsed or indexed chunks found for this corpus document")
        return {"document_id": document_id, "offset": offset, "limit": limit,
                "stage": actual_stage, "chunks": chunks}
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    finally:
        if repository is not None:
            repository.close()


@app.get("/api/admin/processing/{document_id}/tables")
def inspect_extracted_tables(
    document_id: str, table_offset: int = 0, table_limit: int = 50,
    row_offset: int = 0, row_limit: int = 100,
    user: dict = Depends(require_permission("process_documents")),
):
    from core.database.structured_store import StructuredDataStore

    store = StructuredDataStore()
    try:
        tables = store.get_document_tables(
            document_id, table_offset=table_offset,
            table_limit=table_limit, row_offset=row_offset, row_limit=row_limit,
        )
        if not tables:
            raise HTTPException(404, "No extracted tables found in the active company corpus")
        return {
            "document_id": document_id,
            "table_offset": table_offset,
            "table_limit": table_limit,
            "row_offset": row_offset,
            "row_limit": row_limit,
            "tables": tables,
        }
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    finally:
        store.close()


def _uploaded_source_response(document_id: str, user: dict) -> Response:
    repository = DocumentRepository()
    try:
        source = repository.uploaded_source(
            document_id,
            role=user["role"], username=user["sub"],
        )
        policy = None if source else repository.accessible_synthetic_policy_source(
            document_id, role=user["role"],
        )
    finally:
        repository.close()
    if policy is not None:
        return _synthetic_policy_file_response(document_id)
    if source is None:
        raise HTTPException(404, "Uploaded source not found in the active company corpus")

    storage, bucket = _storage_client()
    try:
        content = storage.storage.from_(bucket).download(source["storage_path"])
    except Exception as error:
        logger.exception("Could not open uploaded source %s", document_id)
        raise HTTPException(502, "The stored source file could not be opened") from error

    extension = str(source["format"] or "").casefold()
    media_type = {
        "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "txt": "text/plain",
        "md": "text/markdown",
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "tif": "image/tiff",
        "tiff": "image/tiff",
    }.get(extension, "application/octet-stream")
    title = re.sub(r"[\r\n/\\]+", " ", str(source["title"] or document_id)).strip()
    filename = quote(f"{title[:120]}.{extension}", safe="")
    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": f"inline; filename*=UTF-8''{filename}",
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@app.get("/api/documents/{document_id}/source")
def open_authorized_uploaded_source(
    document_id: str,
    user: dict = Depends(require_permission("view_corpus")),
):
    """Stream an uploaded source only when its document RBAC allows the caller."""
    return _uploaded_source_response(document_id, user)


@app.get("/api/admin/processing/{document_id}/source")
def open_uploaded_source(
    document_id: str,
    user: dict = Depends(require_permission("process_documents")),
):
    """Processing-owner review route for the source inspector."""
    return _uploaded_source_response(document_id, user)


@app.get("/api/admin/access-matrix")
def access_matrix(user: dict = Depends(require_permission("manage_access"))):
    return {
        "current_user": user["sub"],
        "roles": [
            {"role": role, "permissions": sorted(permissions)}
            for role, permissions in ROLE_PERMISSIONS.items()
        ],
    }
