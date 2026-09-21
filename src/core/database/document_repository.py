# src/core/database/documents_repository.py
import os

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row

load_dotenv()


class DocumentRepository:
    def __init__(self) -> None:
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            raise ValueError("DATABASE_URL is not set")

        self.conn = psycopg.connect(database_url, row_factory=dict_row)

    def list_documents(self) -> list[dict]:
        with self.conn.cursor() as cursor:
            cursor.execute("""SELECT document_id, 
                                    domain, 
                                    title, 
                                    year_or_version,
                                    format,
                                    ingestion_format,
                                    official_url,
                                    verification,
                                    rag_value,
                                    document_type,
                                    fiscal_year
                                    FROM documents
                                    ORDER by document_id""")
            return cursor.fetchall()

    def close(self) -> None:
        self.conn.close()

