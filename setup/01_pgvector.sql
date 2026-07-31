-- Project 2 — Data-Aware Agent
-- Lakebase Postgres setup: pgvector extension + knowledge base table
-- Project: olist-agent | Branch: production | Database: agent_knowledge_base

-- 1. Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- 2. Knowledge base table — stores chunks of project documentation (README,
-- Data Quality Findings, etc.) as embeddings for semantic search by the agent.
-- Embedding dimension (1024) matches Qwen3 Embedding 0.6B output size.
CREATE TABLE knowledge_base (
    id SERIAL PRIMARY KEY,
    content TEXT NOT NULL,
    source TEXT NOT NULL,
    embedding VECTOR(1024)
);
