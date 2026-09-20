"""Dense retrieval contracts; no database, embedding, or generation dependencies.

Chunk IDs identify a chunk only while document_id and chunking/index stay unchanged.
They are not persistent IDs across document revisions or re-chunking.
"""

from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _nonblank(value: str) -> str:
    if not value.strip():
        raise ValueError("must not be empty or whitespace-only")
    return value


def _metadata_document_id(metadata: dict[str, Any]) -> str:
    document_id = metadata.get("document_id")
    if not isinstance(document_id, str) or not document_id.strip():
        raise ValueError("metadata.document_id must be a non-empty string")
    return document_id


def make_chunk_id(document_id: str, chunk_index: int) -> str:
    """Build a transitional ID, stable only for unchanged document ID and index."""
    if not isinstance(document_id, str) or not document_id.strip():
        raise ValueError("document_id must be a non-empty string")
    if isinstance(chunk_index, bool) or not isinstance(chunk_index, int) or chunk_index < 0:
        raise ValueError("chunk_index must be a non-negative integer")
    return f"{document_id}::chunk::{chunk_index}"


class RetrievalRequest(ContractModel):
    query: str
    top_k: int = Field(default=5, ge=1, le=100, strict=True)

    _validate_query = field_validator("query")(_nonblank)


class SourceLocation(ContractModel):
    chunk_index: int = Field(ge=0, strict=True)
    page_number: int | None = None
    section_title: str | None = None


class RetrievedChunk(ContractModel):
    """Internal repository result, separate from the ranked public contract.

    The repository normalizes NULL metadata to {}, but missing document_id
    still fails validation here.
    """

    document_name: str
    chunk_index: int = Field(ge=0, strict=True)
    content: str
    metadata: dict[str, Any]
    similarity_score: float = Field(allow_inf_nan=False)

    @field_validator("metadata")
    @classmethod
    def validate_document_id(cls, value: dict[str, Any]) -> dict[str, Any]:
        _metadata_document_id(value)
        return value

    @property
    def document_id(self) -> str:
        return _metadata_document_id(self.metadata)


class RankedChunk(ContractModel):
    """Public result. The service supplies rank and source=document_name.

    document_id must match ingested metadata; neither filenames nor new UUIDs
    are substitutes. Use make_chunk_id(document_id, location.chunk_index).
    """

    rank: int = Field(ge=1, strict=True)
    chunk_id: str
    document_id: str
    text: str
    score: float = Field(allow_inf_nan=False)
    source: str
    location: SourceLocation
    metadata: dict[str, Any]
    retrieval_method: Literal["dense"] = "dense"

    _validate_document_id = field_validator("document_id")(_nonblank)

    @field_validator("metadata")
    @classmethod
    def validate_document_id(cls, value: dict[str, Any]) -> dict[str, Any]:
        _metadata_document_id(value)
        return value

    @model_validator(mode="after")
    def validate_identity(self) -> Self:
        if self.document_id != _metadata_document_id(self.metadata):
            raise ValueError("document_id must match metadata.document_id")
        if self.chunk_id != make_chunk_id(self.document_id, self.location.chunk_index):
            raise ValueError("chunk_id must match document_id and location.chunk_index")
        return self


class RetrievalResponse(ContractModel):
    query: str
    method: Literal["dense"] = "dense"
    latency_ms: float = Field(ge=0, allow_inf_nan=False)
    results: list[RankedChunk]

    _validate_query = field_validator("query")(_nonblank)
