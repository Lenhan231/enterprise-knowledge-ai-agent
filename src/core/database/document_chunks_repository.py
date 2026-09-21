import os

import psycopg
from dotenv import load_dotenv
from psycopg.types.json import Jsonb
from pgvector.psycopg import register_vector
import numpy as np

from core.retrieval.retrieval import RetrievedChunk

load_dotenv()


class DocumentChunkRepository:
    def __init__(self):
        DATABASE_URL = os.getenv("DATABASE_URL")
        if DATABASE_URL is None:
            raise ValueError("DATABASE_URL is not set")
        self.DATABASE_URL = DATABASE_URL
        self.conn = psycopg.connect(self.DATABASE_URL)
        register_vector(self.conn)
        

    def insert_chunk(
        self,
        document_name:str,
        chunk_index:int,
        content:str,
        metadata:dict,
        embedding:list[float]
    ):
        """
        Save a semantic chunk and its embedding to Supabase PostgreSQL.

        Args:
            document_name: Name of the source document.
            chunk_index: Position of the chunk within the document.
            content: Text content of the chunk.
            metadata: Additional chunk metadata stored as JSON.
            embedding: Vector representation of the chunk content.
        """
    
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO document_chunks (
                    document_name,
                    chunk_index,
                    content,
                    metadata,
                    embedding
                )
                VALUES (%s, %s, %s, %s, %s)
                """,(
                    document_name,
                    chunk_index,
                    content,
                    Jsonb(metadata),
                    embedding
                )
            )
            self.conn.commit()

    def replace_document(self, document_name: str, chunks: list[tuple]) -> None:
        """Atomically replace all chunks belonging to one source document."""
        with self.conn.transaction(), self.conn.cursor() as cur:
            cur.execute(
                "DELETE FROM document_chunks WHERE document_name = %s",
                (document_name,),
            )
            cur.executemany(
                """
                INSERT INTO document_chunks (
                    document_name, chunk_index, content, metadata, embedding
                )
                VALUES (%s, %s, %s, %s, %s)
                """,
                [
                    (name, index, content, Jsonb(metadata), embedding)
                    for name, index, content, metadata, embedding in chunks
                ],
            )

    def close(self) -> None:
        self.conn.close()

    def similarity_search(
        self, query_embedding: list[float], limit: int
    ) -> list[RetrievedChunk]:
        """Return full chunks ordered by descending cosine similarity.

        Map database rows at this boundary. Missing metadata.document_id raises
        a validation error, including when SQL NULL metadata becomes {}.
        """
        query_vector = np.array(query_embedding, dtype=np.float32)
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT  document_name,
                        chunk_index,
                        content,
                        metadata,
                        1 - (embedding <=> %s) AS similarity_score
                FROM document_chunks 
                ORDER BY embedding <=> %s ASC, id ASC
                LIMIT %s;
                """,(query_vector, query_vector, limit),
            )
            return [
                RetrievedChunk(
                    document_name=document_name,
                    chunk_index=chunk_index,
                    content=content,
                    metadata={} if metadata is None else metadata,
                    similarity_score=similarity_score,
                )
                for document_name, chunk_index, content, metadata, similarity_score
                in cur.fetchall()
            ]
