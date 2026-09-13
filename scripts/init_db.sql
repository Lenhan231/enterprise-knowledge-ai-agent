-- Initialize pgvector extension and basic tables
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS documents (
  id SERIAL PRIMARY KEY,
  filename TEXT,
  content TEXT,
  metadata JSONB
);
