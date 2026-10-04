from pathlib import Path
import hashlib
import json
import logging
import os
import math
import re
import time
import secrets
import uuid
from typing import Annotated, Literal
import jwt
from jwt import InvalidTokenError

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic import ValidationError
from urllib.parse import quote, urlsplit
from openai import RateLimitError

from core.database.document_repository import DocumentRepository
from core.database.agent_run_repository import AgentRunRepository
from core.agents.dashboard_agent import DashboardAgent
from core.agents.hybrid_agent import HybridAgent
from core.agents.intent_classifier import IntentClassifier
from core.agents.knowledge_agent import KnowledgeAgent
from core.agents.report_agent import ReportAgent
from core.agents.router import AgentRouter
from core.agents.sql_analytics_agent import SQLAnalyticsAgent
from core.models.agents import AgentRequest
from core.rag.rag_service import extract_source_ids
from core.analytics.metric_ontology import METRIC_ONTOLOGY
from core.analytics.business_metric_catalog import (
    BUSINESS_DECISION_PROFILES,
    BUSINESS_METRIC_CATALOG,
    BUSINESS_METRIC_DECISION_PROFILE,
    SUPPORTED_BUSINESS_DECISION_DOMAINS,
)
from core.analytics.commerce_decision_support import COMMERCE_DECISION_PROFILES
from supabase import create_client

logger = logging.getLogger(__name__)
app = FastAPI(title="Commerce Decision Support")

APP_DIR = Path(__file__).resolve().parent
STATIC_DIR = APP_DIR / "static"
# The demo no longer depends on a seed-company manifest.
CORPUS_COMPANY = os.getenv("COMMERCE_DEMO_COMPANY", "Commerce Demo")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
auth_scheme = HTTPBearer(auto_error=False)
DOCUMENT_ROLES = {"employee", "finance_analyst", "sustainability_analyst", "procurement", "operations", "legal_compliance", "executive", "admin"}
ROLE_PERMISSIONS = {
    "employee": {"view_corpus", "ask_documents"},
    "finance_analyst": {"view_corpus", "ask_documents", "view_analytics"},
    "sustainability_analyst": {"view_corpus", "ask_documents", "view_analytics"},
    "procurement": {"view_corpus", "ask_documents"},
    "operations": {"view_corpus", "ask_documents", "view_analytics"},
    "legal_compliance": {"view_corpus", "ask_documents"},
    "executive": {"view_corpus", "ask_documents", "view_analytics"},
    "admin": {"view_corpus", "ask_documents", "view_analytics", "upload_documents", "classify_documents", "review_metrics", "manage_metrics", "manage_access", "manage_knowledge", "view_agent_monitoring", "run_ocr_tests", "review_ocr_tests"},
    "document_uploader": {"view_corpus", "upload_documents", "classify_documents"},
    "tester": {"run_ocr_tests", "review_ocr_tests"},
}


def _roles_with_permission(permission: str) -> tuple[str, ...]:
    return tuple(role for role, permissions in ROLE_PERMISSIONS.items() if permission in permissions)


def require_permission(permission: str):
    roles = _roles_with_permission(permission)
    if not roles:
        raise ValueError(f"No application role grants permission: {permission}")
    return require_roles(*roles)


def _referenced_citation_ids(answer: str) -> set[str]:
    return set(extract_source_ids(answer))


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
    for role in ("admin", "analyst", "viewer", "sustainability_analyst", "tester"):
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


def _current_user(request: Request | WebSocket, credentials: HTTPAuthorizationCredentials | None) -> dict:
    token = credentials.credentials if credentials and credentials.scheme.lower() == "bearer" else None
    token = token or request.cookies.get("enterprise_session")
    if not token:
        raise HTTPException(401, "Sign in to continue")
    secret = os.getenv("AUTH_SECRET_KEY", "")
    if len(secret) < 32:
        raise HTTPException(401, "Invalid or expired session")
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"])
    except InvalidTokenError:
        raise HTTPException(401, "Invalid or expired session") from None
    if payload.get("role") not in DOCUMENT_ROLES | {"document_uploader", "tester"}:
        raise HTTPException(401, "Invalid or expired session")
    return payload


def require_roles(*roles: str):
    def dependency(request: Request, credentials: HTTPAuthorizationCredentials | None = Depends(auth_scheme)):
        user = _current_user(request, credentials)
        if user["role"] not in roles:
            raise HTTPException(403, "Your role cannot access this feature")
        return user
    return dependency


def _require_same_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if origin and origin.rstrip("/") != str(request.base_url).rstrip("/"):
        raise HTTPException(403, "Cross-origin uploads are not allowed")


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
        "company_practice_reference", "company_policy_reference", "platform_operating_rule",
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
    }


class AskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(default="", min_length=3, max_length=1000)
    retrieval_method: Literal["dense", "bm25", "hybrid", "parent"] = "hybrid"
    business_decision_domain: str | None = None
    decision_suggestions: bool = False

    @field_validator("business_decision_domain")
    @classmethod
    def known_business_decision_domain(cls, value: str | None) -> str | None:
        if value is not None and value not in COMMERCE_DECISION_PROFILES:
            raise ValueError("Choose one of the available business decision domains")
        return value

    @model_validator(mode="after")
    def require_question_or_decision_mode(self):
        if not self.question.strip() and not self.decision_suggestions:
            raise ValueError("Enter a question or request conditional decision suggestions")
        if self.decision_suggestions and not self.business_decision_domain:
            raise ValueError("Choose a decision domain before requesting suggestions")
        return self


class BusinessMetricExtractionReplayRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision_domain: str
    metric_name: str

    @field_validator("decision_domain")
    @classmethod
    def known_business_decision_domain(cls, value: str) -> str:
        if value not in SUPPORTED_BUSINESS_DECISION_DOMAINS:
            raise ValueError("Choose a supported business decision domain")
        return value

    @model_validator(mode="after")
    def metric_belongs_to_decision_domain(self):
        if (self.metric_name not in BUSINESS_DECISION_PROFILES[self.decision_domain]["primary_metrics"]
                or BUSINESS_METRIC_DECISION_PROFILE.get(self.metric_name) != self.decision_domain):
            raise ValueError("Choose a primary metric that belongs to the selected domain")
        return self


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=200)


class KnowledgeBaseStatusRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    active: bool


class CandidateReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["verified", "rejected"]
    normalized_value: str | int | float | None = None
    unit: str | None = Field(default=None, max_length=40)

    @field_validator("normalized_value")
    @classmethod
    def finite_metric_value(cls, value):
        if value is not None and isinstance(value, (float, int)) and not math.isfinite(value):
            raise ValueError("Metric value must be finite")
        return value

    @field_validator("unit")
    @classmethod
    def nonblank_unit(cls, value):
        if value is not None and not value.strip():
            raise ValueError("Unit cannot be blank")
        return value.strip() if value is not None else None

    @field_validator("normalized_value", mode="before")
    @classmethod
    def parse_reviewed_metric_value(cls, value):
        if value is None:
            return value
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            raise ValueError("Send reviewed values as text so thousands and decimal separators stay unambiguous")
        if not isinstance(value, str):
            raise ValueError("Metric value must be a number")
        text = value.strip()
        if not text:
            raise ValueError("Metric value is required")
        grouped_vi = re.fullmatch(r"[+-]?\d{1,3}(?:\.\d{3})+(?:,\d+)?", text)
        plain_vi = re.fullmatch(r"[+-]?\d+(?:,\d+)?", text)
        plain_dot_decimal = re.fullmatch(r"[+-]?\d+\.\d+", text)
        if grouped_vi:
            canonical = text.replace(".", "").replace(",", ".")
        elif plain_vi:
            canonical = text.replace(",", ".")
        elif plain_dot_decimal:
            canonical = text
        else:
            raise ValueError("Use Vietnamese number format: . for thousands and , for decimals (for example 11.236,5)")
        try:
            from decimal import Decimal, InvalidOperation

            parsed = Decimal(canonical)
            if not parsed.is_finite():
                raise ValueError("Metric value must be finite")
            return int(parsed) if parsed == parsed.to_integral_value() else float(parsed)
        except ValueError as error:
            raise ValueError("Metric value must be finite") from error
        except InvalidOperation as error:
            raise ValueError("Metric value must be finite") from error


class ManualMetricRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    metric_name: str
    fiscal_year: int = Field(ge=1900, le=2100)
    metric_value: str = Field(min_length=1, max_length=40)
    unit: str = Field(min_length=1, max_length=40)
    source_reference: str | None = Field(default=None, max_length=1000)
    source_note: str = Field(min_length=12, max_length=2000)
    allowed_roles: list[str] = Field(min_length=1)

    @field_validator("metric_name")
    @classmethod
    def canonical_metric(cls, value: str) -> str:
        if value not in METRIC_ONTOLOGY:
            raise ValueError("Choose a metric from the canonical metric catalog")
        return value

    @field_validator("unit", "source_note", "source_reference")
    @classmethod
    def trim_text(cls, value: str | None) -> str | None:
        value = value.strip() if value is not None else None
        return value or None

    @field_validator("unit", "source_note")
    @classmethod
    def required_text(cls, value: str | None) -> str:
        if not value:
            raise ValueError("This field cannot be blank")
        return value

    @field_validator("allowed_roles")
    @classmethod
    def known_roles(cls, value: list[str]) -> list[str]:
        roles = sorted(set(value))
        if not roles or set(roles) - DOCUMENT_ROLES - {"document_uploader"}:
            raise ValueError("Select one or more known roles")
        return roles

    @field_validator("metric_value")
    @classmethod
    def valid_value(cls, value: str) -> str:
        parsed = CandidateReviewRequest(
            status="verified", normalized_value=value, unit="validation",
        ).normalized_value
        return str(parsed)


class BusinessMetricCandidateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    metric_name: str
    fiscal_year: int = Field(ge=1900, le=2100)
    metric_value: str = Field(min_length=1, max_length=40)
    unit: str = Field(min_length=1, max_length=40)
    scope: str = Field(min_length=8, max_length=500)
    source_document_id: str = Field(min_length=3, max_length=120)
    page_number: int = Field(gt=0, le=10000)
    source_quote: str = Field(min_length=12, max_length=3000)
    source_url: str = Field(min_length=8, max_length=1000)
    allowed_roles: list[str] = Field(min_length=1)

    @field_validator("metric_name")
    @classmethod
    def known_business_metric(cls, value: str) -> str:
        if (value not in BUSINESS_METRIC_CATALOG
                or BUSINESS_METRIC_CATALOG[value]["domain"] not in SUPPORTED_BUSINESS_DECISION_DOMAINS):
            raise ValueError("Choose a metric from a supported business decision domain")
        return value

    @field_validator("metric_value")
    @classmethod
    def valid_metric_value(cls, value: str) -> str:
        parsed = CandidateReviewRequest(status="verified", normalized_value=value, unit="validation").normalized_value
        return str(parsed)

    @field_validator("unit", "scope", "source_document_id", "source_quote", "source_url")
    @classmethod
    def trim_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("This field cannot be blank")
        return value

    @field_validator("source_url")
    @classmethod
    def https_source_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("Source URL must use HTTPS")
        return value

    @field_validator("allowed_roles")
    @classmethod
    def known_business_roles(cls, value: list[str]) -> list[str]:
        roles = sorted(set(value))
        if not roles or set(roles) - DOCUMENT_ROLES:
            raise ValueError("Select one or more known roles")
        return roles


@app.get("/", include_in_schema=False)
def home():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/auth/login")
def login(request: LoginRequest):
    accounts = _role_accounts()
    account = accounts.get(request.username)
    if account is None or not secrets.compare_digest(account[0], request.password):
        raise HTTPException(401, "Invalid username or password")
    response = JSONResponse({"username": request.username, "role": account[1], "expires_in": 3600})
    response.set_cookie("enterprise_session", _issue_token(request.username, account[1]), httponly=True, secure=os.getenv("AUTH_COOKIE_SECURE", "false").lower() == "true", samesite="lax", max_age=3600, path="/")
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
            user["role"], user["sub"], company=CORPUS_COMPANY,
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


_COMMERCE_DASHBOARD_KEYS_BY_DOMAIN = {
    "inventory_allocation": ("inventory_by_year", "inventory_year_end_by_category"),
    "promotion_planning": ("promotions_by_year",),
    "nationwide_logistics": ("logistics_by_year_region",),
}


@app.get("/api/commerce/dashboard")
def commerce_dashboard_data(
    domain: Literal["inventory_allocation", "promotion_planning", "nationwide_logistics"] | None = None,
    detail: Literal["campaigns"] | None = None,
    user: dict = Depends(require_permission("view_analytics")),
):
    if detail and domain != "promotion_planning":
        raise HTTPException(422, "Campaign details are only available for promotion planning.")
    repository = None
    try:
        repository = DocumentRepository()
        keys = ("promotions_by_campaign",) if detail == "campaigns" else _COMMERCE_DASHBOARD_KEYS_BY_DOMAIN.get(domain) if domain else None
        return repository.commerce_dashboard(keys)
    except Exception as error:
        logger.exception("Could not load Commerce analytics")
        raise HTTPException(503, "Commerce analytics are unavailable; check the Commerce schema migration.") from error
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
def admin_knowledge_documents(user: dict = Depends(require_permission("manage_knowledge"))):
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


@app.get("/api/admin/knowledge-documents/{document_id}/source")
def open_synthetic_policy_source(
    document_id: str,
    user: dict = Depends(require_permission("manage_knowledge")),
):
    """Open only synthetic policy PDFs explicitly registered by the local manifest."""
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


@app.post("/api/documents/upload")
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    title: str = Form(...),
    document_type: str = Form(...),
    domain: str = Form(...),
    fiscal_year: int | None = Form(default=None),
    source_url: str | None = Form(default=None),
    business_decision_domain: str = Form(default=""),
    knowledge_domains: Annotated[list[str], Form()] = [],
    source_publisher: Annotated[str | None, Form(max_length=200)] = None,
    reference_type: Annotated[str, Form(max_length=40)] = "",
    reference_applicability: Annotated[str | None, Form(max_length=1000)] = None,
    synthetic_company_policy: Annotated[bool, Form()] = False,
    allowed_roles: list[str] = Form(default=[]),
    user: dict = Depends(require_permission("upload_documents")),
):
    """Keep original bytes in private Storage; persist parsed evidence in PostgreSQL."""
    _require_same_origin(request)
    filename = Path((file.filename or "").replace("\\", "/")).name
    extension = Path(filename).suffix.lower()
    from core.document_processing.processors.document_processor import DocumentProcessor
    if not filename or extension not in DocumentProcessor.SUPPORTED:
        raise HTTPException(415, "Supported formats: PDF, DOCX, PPTX, XLSX, TXT, MD, PNG, JPG, TIF")
    if not title.strip() or not document_type.strip() or not domain.strip():
        raise HTTPException(422, "Title, document type, and domain are required")
    business_decision_domain = business_decision_domain.strip() if business_decision_domain else None
    if not business_decision_domain:
        business_decision_domain = None
    if business_decision_domain and business_decision_domain not in SUPPORTED_BUSINESS_DECISION_DOMAINS:
        raise HTTPException(422, "Choose a supported business decision domain")
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
                    ".txt": "text/plain", ".md": "text/markdown", ".png": "image/png",
                    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".tif": "image/tiff", ".tiff": "image/tiff"}[extension]
    source_hash = hashlib.sha256(content).hexdigest()
    storage, bucket = _storage_client()
    repository = None
    uploaded = False
    registered = False
    parsed_chunks_saved = False
    business_metric_candidates_saved = 0
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
        from core.document_processing.processors.document_processor import DocumentProcessor
        from core.embeddings.embedding_service import EmbeddingService
        from core.database.document_chunks_repository import DocumentChunkRepository
        from core.database.processed_chunks_repository import ProcessedChunksRepository
        from core.database.structured_store import StructuredDataStore
        from core.analytics.metric_candidates import candidates as extract_metric_candidates

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
            "chunking_strategy": os.getenv("DOCUMENT_CHUNKING_STRATEGY", "sentence"),
            "paddle_layout": os.getenv("DOCUMENT_PADDLE_LAYOUT", "false").strip().lower() == "true",
            "paddle_formula_recognition": os.getenv(
                "DOCUMENT_PADDLE_FORMULA_RECOGNITION", "false",
            ).strip().lower() == "true",
            "vision_captioning": os.getenv("DOCUMENT_VISION_CAPTIONS", "false").strip().lower() == "true",
        })
        try:
            processed = processor.process(filename, content, metadata)
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
        parsed_repository = ProcessedChunksRepository()
        try:
            parsed_repository.replace_document(document_id, chunks)
            parsed_chunks_saved = True
            structured_store = StructuredDataStore()
            try:
                structured_store.save_document_tables(document_id, title.strip(), processed["tables"])
            finally:
                structured_store.close()
        finally:
            parsed_repository.close()

        embedding_service = EmbeddingService()
        from core.utils.token_counter import TokenCounter

        token_counter = TokenCounter(embedding_service.model_name)
        bounded_chunks = []
        for chunk in chunks:
            for text in token_counter.split_text(
                chunk["text"],
                max_sequence_tokens=embedding_service.max_sequence_length,
            ):
                chunk_metadata = dict(chunk["metadata"])
                chunk_metadata.update({
                    "chunk_index": len(bounded_chunks),
                    "token_count": token_counter.count(text),
                    "actual_char_count": len(text),
                })
                bounded_chunks.append({"text": text, "metadata": chunk_metadata})
        chunks = bounded_chunks
        business_metric_candidates = []
        business_chunks = []
        business_extraction_run = None
        business_extraction_error = None
        business_extraction_run_id = None
        candidate_chunks = chunks
        candidate_tables = processed.get("tables", [])
        text_evidence_page_numbers = set()
        if fiscal_year and extension == ".pdf" and not is_commerce_reference:
            from core.analytics.financial_extraction import select_financial_pages

            selected = select_financial_pages(chunks, candidate_tables)
            selected_page_numbers = {page["page_number"] for page in selected}
            text_evidence_page_numbers = {
                page["page_number"] for page in selected
                if page["selection_signals"]["summary_area_with_metric"]
            }
            candidate_chunks = [
                chunk for chunk in chunks
                if int(chunk["metadata"].get("page_number") or 0) in selected_page_numbers
            ]
            candidate_tables = [
                table for table in candidate_tables
                if int(table.get("page_number") or 0) in selected_page_numbers
            ]
        metric_candidates = extract_metric_candidates(
            [{"metadata": chunk["metadata"], "text": chunk["text"]} for chunk in candidate_chunks],
            {**metadata, "rbac": {"allowed_roles": allowed_roles}}, candidate_tables,
            text_evidence_page_numbers=text_evidence_page_numbers or None,
        ) if fiscal_year and not is_commerce_reference else []
        if extension == ".pdf":
            llm_provider = None
            if not is_commerce_reference and (business_decision_domain or fiscal_year):
                try:
                    from core.llm.groq_provider import GroqProvider

                    llm_provider = GroqProvider()
                except Exception:
                    logger.exception("Could not initialize extraction provider for %s", document_id)
            if not is_commerce_reference and business_decision_domain and llm_provider is not None:
                try:
                    from core.analytics.business_metric_extraction import (
                        build_business_metric_extraction_run,
                        extract_business_metric_candidates,
                    )

                    business_metric_candidates, business_chunks = extract_business_metric_candidates(
                        chunks, processed.get("tables", []),
                        {**metadata, "document_id": document_id,
                         "business_decision_domain": business_decision_domain,
                         "rbac": {"allowed_roles": allowed_roles}},
                        llm_provider,
                    )
                    business_extraction_run = build_business_metric_extraction_run(
                        chunks, business_chunks, business_metric_candidates,
                        {**metadata, "business_decision_domain": business_decision_domain}, llm_provider,
                    )
                    logger.info(
                        "Business metric extraction document=%s decision_domain=%s selected_evidence_chunks=%s candidates=%s",
                        document_id, business_decision_domain,
                        [(page.get("page_number"), [chunk.get("chunk_index") for chunk in page.get("chunks", [])])
                         for page in business_chunks],
                        len(business_metric_candidates),
                    )
                except Exception:
                    business_extraction_error = "extraction_exception"
                    logger.exception("Business metric extraction failed for %s", document_id)
            elif not is_commerce_reference and business_decision_domain:
                business_extraction_error = "provider_unavailable"
            if fiscal_year and not is_commerce_reference:
                try:
                    from core.analytics.financial_extraction import (
                        extract_financial_candidates, merge_candidate_sources,
                    )

                    llm_candidates, selected_pages = extract_financial_candidates(
                        chunks, processed.get("tables", []),
                        {**metadata, "rbac": {"allowed_roles": allowed_roles}},
                        llm_provider,
                    )
                    metric_candidates = merge_candidate_sources(metric_candidates, llm_candidates)
                    logger.info(
                        "Financial page extraction document=%s selected_pages=%s candidates=%s",
                        document_id, [page["page_number"] for page in selected_pages],
                        len(llm_candidates),
                    )
                except Exception:
                    logger.exception("Financial LLM extraction failed for %s; retaining parser candidates", document_id)
            if llm_provider is not None:
                try:
                    llm_provider.close()
                except Exception:
                    logger.exception("Failed to close extraction provider for %s", document_id)
        elif business_decision_domain and not is_commerce_reference:
            business_extraction_error = "unsupported_format"
        if not is_commerce_reference:
            repository.save_metric_candidates(document_id, metric_candidates)
        parsed_repository = ProcessedChunksRepository()
        parsed_repository.set_status(document_id, "embedding")
        parsed_repository.close()
        vectors = embedding_service.embed_documents([chunk["text"] for chunk in chunks])
        for chunk in chunks:
            chunk["metadata"]["embedding_model"] = embedding_service.model_name
        chunk_repository = DocumentChunkRepository()
        try:
            chunk_repository.replace_document(document_id, [
                (filename, index, chunk["text"],
                 {**chunk["metadata"], "document_id": document_id, "allowed_roles": allowed_roles}, vector)
                for index, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True))
            ])
        finally:
            chunk_repository.close()
        if business_metric_candidates:
            business_metric_candidates_saved = repository.save_business_metric_candidates(
                business_metric_candidates, entered_by="parser",
            )
        if business_decision_domain and not is_commerce_reference:
            from core.analytics.business_metric_extraction import build_business_metric_extraction_run

            if business_extraction_run is None:
                business_extraction_run = build_business_metric_extraction_run(
                    chunks, business_chunks, business_metric_candidates,
                    {**metadata, "business_decision_domain": business_decision_domain},
                    llm_provider if extension == ".pdf" else None,
                    execution_error=business_extraction_error or "extraction_exception",
                )
            business_extraction_run_id = repository.save_business_metric_extraction_run(
                business_extraction_run,
            )
        parsed_repository = ProcessedChunksRepository()
        try:
            parsed_repository.set_status(document_id, "embedded")
        finally:
            parsed_repository.close()
        repository.update_processing_status(document_id, "ready")
        return {
            "document_id": document_id, "storage_path": storage_path,
            "processing_status": "ready", "searchable": True, "sha256": source_hash,
            "page_count": page_count, "parser_chunk_count": len(parser_chunks),
            "indexed_chunk_count": len(chunks), "ocr_chunk_count": ocr_chunk_count,
            "table_count": len(processed.get("tables", [])),
            "business_metric_candidates": business_metric_candidates_saved,
            "business_metric_extraction_run_id": business_extraction_run_id,
        }
    except HTTPException:
        if registered and repository is not None:
            try:
                repository.update_processing_status(document_id, "failed")
                if parsed_chunks_saved:
                    from core.database.processed_chunks_repository import ProcessedChunksRepository

                    parsed_repository = ProcessedChunksRepository()
                    try:
                        parsed_repository.set_status(document_id, "failed", "Upload processing did not complete")
                    finally:
                        parsed_repository.close()
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
                if parsed_chunks_saved:
                    from core.database.processed_chunks_repository import ProcessedChunksRepository

                    parsed_repository = ProcessedChunksRepository()
                    try:
                        parsed_repository.set_status(document_id, "failed", str(error))
                    finally:
                        parsed_repository.close()
            except Exception:
                logger.exception("Failed to record failed status for %s", document_id)
        logger.exception("Upload or processing failed for %s", document_id)
        raise HTTPException(503, "Upload or processing failed; see document status and app logs") from error
    finally:
        if repository is not None:
            repository.close()


@app.post("/api/ocr-tests")
async def create_ocr_test(
    request: Request,
    file: UploadFile = File(...),
    tesseract_psm: int = Form(default=11),
    tesseract_table_psm: int = Form(default=3),
    render_scale: float = Form(default=1.5),
    table_render_scale: float = Form(default=2.5),
    user: dict = Depends(require_permission("run_ocr_tests")),
):
    """Run the upload PDF parser and save inspectable output outside the corpus."""
    _require_same_origin(request)
    filename = Path((file.filename or "").replace("\\", "/")).name
    if Path(filename).suffix.lower() != ".pdf":
        raise HTTPException(415, "OCR Lab accepts PDF files only")
    if tesseract_psm not in {3, 6, 11, 12} or tesseract_table_psm not in {3, 4, 6, 11, 12}:
        raise HTTPException(422, "Unsupported Tesseract page segmentation mode")
    if render_scale not in {1.5, 2.5, 3.5} or table_render_scale not in {1.5, 2.5, 3.5}:
        raise HTTPException(422, "Render scale must be 1.5, 2.5, or 3.5")
    content = await file.read(20 * 1024 * 1024 + 1)
    if len(content) > 20 * 1024 * 1024:
        raise HTTPException(413, "OCR test PDF exceeds the 20 MiB limit")
    if b"%PDF-" not in content[:1024]:
        raise HTTPException(415, "The uploaded file is not a PDF")

    import fitz
    import hashlib
    import subprocess
    import uuid

    try:
        source = fitz.open(stream=content, filetype="pdf")
        page_count = len(source)
        if not 1 <= page_count <= 50:
            source.close()
            raise HTTPException(422, "OCR Lab accepts PDFs with 1-50 pages")
        page_previews = []
        for page in source:
            scale = min(120 / 72, 1800 / page.rect.width, 2400 / page.rect.height)
            page_previews.append(page.get_pixmap(
                matrix=fitz.Matrix(scale, scale), alpha=False,
            ).tobytes("png"))
        source.close()
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(422, "Could not open the uploaded PDF") from error

    config = {
        "chunking_strategy": os.getenv("DOCUMENT_CHUNKING_STRATEGY", "sentence"),
        "paddle_layout": os.getenv("DOCUMENT_PADDLE_LAYOUT", "false").strip().lower() == "true",
        "paddle_formula_recognition": os.getenv("DOCUMENT_PADDLE_FORMULA_RECOGNITION", "false").strip().lower() == "true",
        "vision_captioning": False,
        "tesseract_psm": tesseract_psm,
        "tesseract_table_psm": tesseract_table_psm,
        "ocr_render_scale": render_scale,
        "ocr_table_render_scale": table_render_scale,
    }
    run_id = uuid.uuid4()
    source_sha256 = hashlib.sha256(content).hexdigest()
    from core.document_processing.processors.document_processor import DocumentProcessor
    try:
        parsed = DocumentProcessor(config).process(
            filename, content, {"source_type": "ocr_test", "source_sha256": source_sha256},
        )
    except (ValueError, RuntimeError) as error:
        raise HTTPException(422, f"OCR processing failed: {error}") from error
    try:
        tesseract_version = subprocess.run(
            ["tesseract", "--version"], capture_output=True, check=True,
            text=True, timeout=10,
        ).stdout.splitlines()[0]
    except (OSError, subprocess.SubprocessError, IndexError):
        tesseract_version = None
    runtime_info = {"pymupdf": fitz.VersionBind, "tesseract": tesseract_version}

    from core.database.ocr_test_repository import OcrTestRepository
    repository = OcrTestRepository()
    try:
        repository.save_run(
            run_id, source_filename=filename, source_sha256=source_sha256,
            uploaded_by=user["sub"], processor_config=config, runtime_info=runtime_info,
            page_previews=page_previews, chunks=parsed["chunks"], tables=parsed["tables"],
        )
    except Exception as error:
        logger.exception("Could not persist OCR test run %s", run_id)
        raise HTTPException(503, "OCR completed, but its test output could not be saved") from error
    finally:
        repository.close()
    return {
        "run_id": str(run_id), "source_filename": filename,
        "source_sha256": source_sha256, "page_count": page_count,
        "chunk_count": len(parsed["chunks"]), "table_count": len(parsed["tables"]),
        "processor_config": config, "runtime_info": runtime_info,
    }


@app.get("/api/ocr-tests")
def list_ocr_tests(user: dict = Depends(require_permission("review_ocr_tests"))):
    from core.database.ocr_test_repository import OcrTestRepository

    repository = OcrTestRepository()
    try:
        return {"runs": repository.list_runs()}
    finally:
        repository.close()


@app.get("/api/ocr-tests/{run_id}")
def inspect_ocr_test(
    run_id: uuid.UUID,
    user: dict = Depends(require_permission("review_ocr_tests")),
):
    from core.database.ocr_test_repository import OcrTestRepository

    repository = OcrTestRepository()
    try:
        run = repository.get_run(run_id)
        if run is None:
            raise HTTPException(404, "OCR test run not found")
        return run
    finally:
        repository.close()


@app.get("/api/ocr-tests/{run_id}/pages/{page_number}/preview")
def get_ocr_test_preview(
    run_id: uuid.UUID, page_number: int,
    user: dict = Depends(require_permission("review_ocr_tests")),
):
    from core.database.ocr_test_repository import OcrTestRepository

    repository = OcrTestRepository()
    try:
        preview = repository.get_page_preview(run_id, page_number)
        if preview is None:
            raise HTTPException(404, "OCR test page preview not found")
        return Response(content=preview, media_type="image/png")
    finally:
        repository.close()


@app.get("/api/analytics")
def analytics_data(user: dict = Depends(require_permission("view_analytics"))):
    repository = None
    try:
        repository = DocumentRepository()
        result = repository.corpus_dashboard(
            user["role"], user["sub"], include_analytics=True,
            company=CORPUS_COMPANY,
        )
        return result
    except Exception as error:
        logger.exception("Could not load enterprise analytics")
        raise HTTPException(503, "Analytics database is unavailable") from error
    finally:
        if repository is not None:
            repository.close()


@app.get("/api/metrics/catalog")
def metric_catalog(user: dict = Depends(require_permission("view_analytics"))):
    return [{"metric_name": name, **definition}
            for name, definition in METRIC_ONTOLOGY.items()]


@app.get("/api/business-metrics/catalog")
def business_metric_catalog(user: dict = Depends(require_permission("view_analytics"))):
    return [{
        "metric_name": name,
        **definition,
        "decision_priority": "primary" if name in BUSINESS_METRIC_DECISION_PROFILE else "supporting",
        "decision_profile": BUSINESS_METRIC_DECISION_PROFILE.get(name),
        "decision_profile_label": BUSINESS_DECISION_PROFILES[
            BUSINESS_METRIC_DECISION_PROFILE[name]
        ]["label"] if name in BUSINESS_METRIC_DECISION_PROFILE else None,
    } for name, definition in BUSINESS_METRIC_CATALOG.items()
            if definition["domain"] in SUPPORTED_BUSINESS_DECISION_DOMAINS]


@app.post("/api/business-metrics/candidates")
def create_business_metric_candidate(
    request: BusinessMetricCandidateRequest,
    user: dict = Depends(require_permission("manage_metrics")),
):
    repository = None
    try:
        repository = DocumentRepository()
        candidate_id = repository.create_business_metric_candidate(
            company=CORPUS_COMPANY,
            metric={"name": request.metric_name, **BUSINESS_METRIC_CATALOG[request.metric_name]},
            fiscal_year=request.fiscal_year,
            metric_value=float(request.metric_value), unit=request.unit, scope=request.scope,
            source_document_id=request.source_document_id, page_number=request.page_number,
            source_quote=request.source_quote, source_url=request.source_url,
            allowed_roles=request.allowed_roles, entered_by=user["sub"],
            extraction_method="manual", extractor_version="manual-v1",
        )
        return {"id": candidate_id, "status": "needs_review"}
    except (TypeError, ValueError) as error:
        raise HTTPException(422, str(error)) from error
    except Exception as error:
        logger.exception("Could not save business metric evidence")
        raise HTTPException(503, "Could not save business metric evidence") from error
    finally:
        if repository is not None:
            repository.close()


@app.post("/api/business-metrics/{metric_id}/review")
def review_business_metric(
    metric_id: int, request: CandidateReviewRequest,
    user: dict = Depends(require_permission("review_metrics")),
):
    repository = None
    try:
        repository = DocumentRepository()
        updated = repository.review_business_metric(
            metric_id, request.status, request.normalized_value, request.unit,
            user["sub"], CORPUS_COMPANY,
        )
        if not updated:
            raise HTTPException(404, "Business metric not found or already reviewed")
        return {"id": metric_id, "status": request.status}
    except HTTPException:
        raise
    except (TypeError, ValueError) as error:
        raise HTTPException(422, str(error)) from error
    except Exception as error:
        logger.exception("Could not review business metric %s", metric_id)
        raise HTTPException(503, "Could not save business metric review") from error
    finally:
        if repository is not None:
            repository.close()


@app.post("/api/metrics/manual")
def create_manual_metric(
    request: ManualMetricRequest,
    user: dict = Depends(require_permission("manage_metrics")),
):
    repository = None
    try:
        repository = DocumentRepository()
        candidate_id = repository.create_manual_metric_candidate(
            company=CORPUS_COMPANY,
            metric_name=request.metric_name,
            metric_label=METRIC_ONTOLOGY[request.metric_name]["label"],
            metric_value=request.metric_value,
            fiscal_year=request.fiscal_year,
            unit=request.unit,
            source_reference=request.source_reference,
            source_note=request.source_note,
            allowed_roles=request.allowed_roles,
        )
        return {"id": candidate_id, "status": "needs_review"}
    except (TypeError, ValueError) as error:
        raise HTTPException(422, str(error)) from error
    except Exception as error:
        logger.exception("Could not save manual metric candidate")
        raise HTTPException(503, "Could not save manual metric") from error
    finally:
        if repository is not None:
            repository.close()


@app.get("/api/admin/processing/{document_id}/chunks")
def inspect_processed_chunks(
    document_id: str, offset: int = 0, limit: int = 25,
    stage: Literal["parser", "indexed"] = "parser",
    source_chunk_id: int | None = None,
    user: dict = Depends(require_permission("review_metrics")),
):
    from core.database.processed_chunks_repository import ProcessedChunksRepository

    repository = None
    try:
        chunks = []
        if stage == "parser":
            repository = ProcessedChunksRepository()
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


@app.get("/api/admin/processing/{document_id}/business-metric-extraction-runs")
def inspect_business_metric_extraction_runs(
    document_id: str,
    user: dict = Depends(require_permission("review_metrics")),
):
    repository = None
    try:
        repository = DocumentRepository()
        return {
            "document_id": document_id,
            "runs": repository.business_metric_extraction_runs(document_id, CORPUS_COMPANY),
        }
    except Exception as error:
        logger.exception("Could not load business metric extraction runs for %s", document_id)
        raise HTTPException(503, "Business metric extraction history is unavailable") from error
    finally:
        if repository is not None:
            repository.close()


@app.post("/api/admin/processing/{document_id}/business-metric-extraction-runs")
def rerun_business_metric_extraction(
    document_id: str,
    request: BusinessMetricExtractionReplayRequest,
    http_request: Request,
    user: dict = Depends(require_permission("manage_metrics")),
):
    _require_same_origin(http_request)
    repository = None
    provider = None
    try:
        repository = DocumentRepository()
        document = repository.pdf_for_metric_extraction(document_id, CORPUS_COMPANY)
        if document is None:
            raise HTTPException(404, "Ready stored PDF not found in the active company")

        from core.database.processed_chunks_repository import ProcessedChunksRepository

        parsed_repository = ProcessedChunksRepository()
        try:
            stored_chunks = parsed_repository.get_document(document_id, company=CORPUS_COMPANY)
        finally:
            parsed_repository.close()
        if not stored_chunks:
            raise HTTPException(422, "No saved parser chunks are available to replay")
        chunks = [{
            "text": row["content"],
            "metadata": {**(row.get("metadata") or {}), "chunk_index": row["chunk_index"]},
        } for row in stored_chunks]

        from core.database.structured_store import StructuredDataStore

        store = StructuredDataStore()
        tables = []
        try:
            table_offset = 0
            while True:
                page = store.get_document_tables(
                    document_id, company=CORPUS_COMPANY, table_offset=table_offset,
                    table_limit=50, row_offset=0, row_limit=1,
                )
                tables.extend({
                    "page_number": table["page_number"],
                    "table_index": table["table_index"],
                    "context": (table.get("metadata") or {}).get("table_context", {}),
                } for table in page)
                if len(page) < 50:
                    break
                table_offset += len(page)
        finally:
            store.close()

        extraction_document = {
            **document,
            "business_decision_domain": request.decision_domain,
            "selected_metric_names": [request.metric_name],
            "fiscal_year": document.get("fiscal_year"),
            "rbac": {"allowed_roles": document.get("allowed_roles") or ["admin"]},
        }
        from core.analytics.business_metric_extraction import (
            build_business_metric_extraction_run,
            extract_business_metric_candidates,
        )

        try:
            from core.llm.groq_provider import GroqProvider

            provider = GroqProvider()
        except Exception:
            run = build_business_metric_extraction_run(
                chunks, [], [], extraction_document, None,
                execution_error="provider_unavailable",
            )
            run_id = repository.save_business_metric_extraction_run(run)
            return {
                "run_id": run_id, "status": run["status"], "candidate_count": 0,
                "metric_name": request.metric_name,
                "selected_chunk_count": 0, "input_chunk_count": len(chunks),
            }

        try:
            candidates, page_results = extract_business_metric_candidates(
                chunks, tables, extraction_document, provider,
                metric_names=[request.metric_name],
            )
            if candidates:
                repository.save_business_metric_candidates(candidates, entered_by="parser")
            run = build_business_metric_extraction_run(
                chunks, page_results, candidates, extraction_document, provider,
            )
        except Exception:
            logger.exception("Business metric replay failed for %s", document_id)
            run = build_business_metric_extraction_run(
                chunks, [], [], extraction_document, provider,
                execution_error="extraction_exception",
            )
        run_id = repository.save_business_metric_extraction_run(run)
        return {
            "run_id": run_id,
            "status": run["status"],
            "metric_name": request.metric_name,
            "candidate_count": run["candidate_count"],
            "selected_chunk_count": run["selected_chunk_count"],
            "input_chunk_count": run["input_chunk_count"],
        }
    except HTTPException:
        raise
    except Exception as error:
        logger.exception("Could not replay business metric extraction for %s", document_id)
        raise HTTPException(503, "Could not replay extraction from saved parser chunks") from error
    finally:
        if provider is not None:
            try:
                provider.close()
            except Exception:
                logger.exception("Could not close business metric replay provider")
        if repository is not None:
            repository.close()


@app.get("/api/admin/processing/{document_id}/tables")
def inspect_extracted_tables(
    document_id: str, table_offset: int = 0, table_limit: int = 50,
    row_offset: int = 0, row_limit: int = 100,
    user: dict = Depends(require_permission("review_metrics")),
):
    from core.database.structured_store import StructuredDataStore

    store = StructuredDataStore()
    try:
        tables = store.get_document_tables(
            document_id, company=CORPUS_COMPANY, table_offset=table_offset,
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
            document_id, company=CORPUS_COMPANY,
            role=user["role"], username=user["sub"],
        )
    finally:
        repository.close()
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
    user: dict = Depends(require_permission("review_metrics")),
):
    """Admin review route retained for the processing inspector."""
    return _uploaded_source_response(document_id, user)


@app.post("/api/analytics/candidates/{candidate_id}/review")
def review_candidate(candidate_id: int, request: CandidateReviewRequest, user: dict = Depends(require_permission("review_metrics"))):
    repository = None
    try:
        repository = DocumentRepository()
        if not repository.review_metric_candidate(
            candidate_id, request.status, request.normalized_value, request.unit,
            user["sub"], CORPUS_COMPANY,
        ):
            raise HTTPException(404, "Candidate not found or already reviewed")
        return {"id": candidate_id, "status": request.status}
    except HTTPException:
        raise
    except (TypeError, ValueError) as error:
        raise HTTPException(422, str(error)) from error
    except Exception as error:
        logger.exception("Could not review metric candidate %s", candidate_id)
        raise HTTPException(503, "Could not save metric review") from error
    finally:
        if repository is not None:
            repository.close()


@app.get("/api/admin/access-matrix")
def access_matrix(user: dict = Depends(require_permission("manage_access"))):
    return {
        "current_user": user["sub"],
        "roles": [
            {"role": role, "permissions": sorted(permissions)}
            for role, permissions in ROLE_PERMISSIONS.items()
        ],
    }


@app.get("/api/admin/agent-monitoring")
def agent_monitoring(user: dict = Depends(require_permission("view_agent_monitoring"))):
    repository = None
    try:
        repository = AgentRunRepository()
        return repository.monitoring_snapshot()
    except Exception as error:
        logger.exception("Could not load agent monitoring data")
        raise HTTPException(503, "Agent monitoring data is unavailable. Check the database and migrations.") from error
    finally:
        if repository is not None:
            repository.close()


@app.post("/api/ask")
def ask_documents(request: AskRequest, user: dict = Depends(require_permission("ask_documents"))):
    return _answer_documents(request, user)


def _answer_documents(request: AskRequest, user: dict) -> dict:
    started = time.perf_counter()
    run_status = "failed"
    error_type = "ServiceError"
    agent_name = "unrouted"
    citation_count = 0
    router = None
    knowledge = analytics = hybrid = report = dashboard = classifier = None
    try:
        knowledge = KnowledgeAgent()
        analytics = SQLAnalyticsAgent()
        hybrid = HybridAgent(knowledge, analytics)
        dashboard = DashboardAgent(analytics=analytics)
        classifier = IntentClassifier()
        report = ReportAgent(knowledge=knowledge, analytics=analytics)
        router = AgentRouter(
            classifier=classifier,
            knowledge_agent=knowledge,
            analytics_agent=analytics,
            hybrid_agent=hybrid,
            dashboard_agent=dashboard,
            report_agent=report,
        )
        agent_result = router.route(AgentRequest(
            question=request.question.strip() or "Generate conditional management actions from available Commerce observations.",
            user_id=user["sub"],
            metadata={
                "role": user["role"],
                "company": CORPUS_COMPANY,
                "retrieval_method": request.retrieval_method,
                "business_decision_domain": request.business_decision_domain,
                "decision_suggestions": request.decision_suggestions,
            },
        ))
        cited_ids = _referenced_citation_ids(agent_result.answer)
        citations = [
            {
                "id": evidence.citation_id,
                "company": evidence.metadata.get("company", "Unknown company"),
                "title": evidence.metadata.get("source_title") or evidence.metadata.get("title") or evidence.source,
                "source_publisher": evidence.metadata.get("source_publisher"),
                "evidence_class": evidence.metadata.get("evidence_class"),
                "reference_applicability": evidence.metadata.get("reference_applicability"),
                "document_id": evidence.metadata.get("document_id"),
                "chunk_index": evidence.metadata.get("chunk_index"),
                "source_chunk_id": evidence.metadata.get("source_chunk_id", evidence.metadata.get("chunk_id")),
                "source_content_hash": evidence.metadata.get("source_content_hash"),
                "page_number": evidence.metadata.get("page_number"),
                "source_url": evidence.metadata.get("source_url"),
                "excerpt": evidence.content[:700] if evidence.content else "",
                "score": evidence.metadata.get("retrieval_score"),
                "retrieval_method": evidence.metadata.get("retrieval_method"),
                "source_type": evidence.source_type,
                "metric_name": evidence.metadata.get("metric_name"),
                "fiscal_year": evidence.metadata.get("fiscal_year"),
                "commerce_domain": evidence.metadata.get("commerce_domain"),
                "commerce_aggregate_key": evidence.metadata.get("commerce_aggregate_key"),
                "commerce_observation_group": evidence.metadata.get("commerce_observation_group"),
                "commerce_observations": evidence.metadata.get("commerce_observations"),
                "source_tables": evidence.metadata.get("source_tables"),
                "sql_query": evidence.metadata.get("sql_query"),
                "sql_generation_provider": evidence.metadata.get("sql_generation_provider"),
                "dataset_note": evidence.metadata.get("dataset_note"),
            }
            for evidence in agent_result.evidence
            if evidence.citation_id in cited_ids
        ]
        agent_name = agent_result.agent
        citation_count = len(citations)
        run_status = "completed"
        error_type = None
        return {
            "answer": agent_result.answer,
            "insufficient_context": agent_result.metadata.get("insufficient_context", False),
            "citation_validation_failed": agent_result.metadata.get("citation_validation_failed", False),
            "citations": citations,
            "agent": agent_result.agent,
            "data": jsonable_encoder(agent_result.data),
            **({"decision_analysis": agent_result.metadata["decision_analysis"]}
               if agent_result.metadata.get("decision_analysis") else {}),
            **({"decision_reference_retrieval_limited": True}
               if agent_result.metadata.get("decision_reference_retrieval_limited") else {}),
            **({"question_sql_fallback": agent_result.metadata["question_sql_fallback"]}
               if agent_result.metadata.get("question_sql_fallback") else {}),
            **({"generation_provider": agent_result.metadata["generation_provider"]}
               if agent_result.metadata.get("generation_provider") else {}),
        }
    except RateLimitError as error:
        agent_name = getattr(router, "last_destination", agent_name)
        run_status = "rate_limited"
        error_type = type(error).__name__
        logger.warning("LLM provider rate limit reached while answering for %s", user["sub"])
        raise HTTPException(429, "The model provider is temporarily rate-limited. Please retry later.") from error
    except Exception as error:
        agent_name = getattr(router, "last_destination", agent_name)
        error_type = type(error).__name__
        logger.exception("Could not answer enterprise question")
        raise HTTPException(
            status_code=503,
            detail="Question answering is unavailable. Check the database, embedding model, and GROQ_API_KEY.",
        ) from error
    finally:
        # ReportAgent shares KnowledgeAgent; close it through the hybrid stack once.
        if report is not None:
            report.close()
        if hybrid is not None:
            hybrid.close()
        else:
            if knowledge is not None:
                knowledge.close()
            if analytics is not None:
                analytics.close()
        if dashboard is not None:
            dashboard.close()
        if classifier is not None:
            classifier.close()
        monitor = None
        try:
            monitor = AgentRunRepository()
            monitor.record_event(
                actor_role=user["role"], agent_name=agent_name,
                retrieval_method=request.retrieval_method, status=run_status,
                elapsed_ms=max(0, round((time.perf_counter() - started) * 1000)),
                citation_count=citation_count, error_type=error_type,
            )
        except Exception:
            logger.warning("Could not persist agent monitoring event", exc_info=True)
        finally:
            if monitor is not None:
                monitor.close()


@app.websocket("/ws/ask")
async def ask_documents_websocket(websocket: WebSocket):
    origin = websocket.headers.get("origin")
    if origin:
        parsed_origin = urlsplit(origin)
        if parsed_origin.scheme not in {"http", "https"} or parsed_origin.netloc.casefold() != websocket.headers.get("host", "").casefold():
            await websocket.close(code=4403)
            return

    try:
        user = _current_user(websocket, None)
    except HTTPException:
        await websocket.close(code=4401)
        return
    if "ask_documents" not in ROLE_PERMISSIONS.get(user["role"], set()):
        await websocket.close(code=4403)
        return

    await websocket.accept()
    try:
        while True:
            try:
                payload = await websocket.receive_json()
            except WebSocketDisconnect:
                break
            try:
                request = AskRequest.model_validate(payload)
            except ValidationError as error:
                await websocket.send_json({"type": "error", "detail": error.errors(include_input=False)})
                continue

            await websocket.send_json({"type": "status", "status": "processing"})
            try:
                result = await run_in_threadpool(_answer_documents, request, user)
                await websocket.send_json({"type": "answer", **result})
            except HTTPException as error:
                await websocket.send_json({"type": "error", "status_code": error.status_code, "detail": error.detail})
            except Exception:
                logger.exception("WebSocket question answering failed for %s", user["sub"])
                await websocket.send_json({
                    "type": "error",
                    "status_code": 503,
                    "detail": "Question answering is unavailable. Check the database, embedding model, and GROQ_API_KEY.",
                })
    except WebSocketDisconnect:
        pass
