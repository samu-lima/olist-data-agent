# Olist Data Agent

A natural-language agent that answers questions about the Olist Lakehouse Pipeline (Project 1) — combining SQL generation over the Gold layer with semantic search over the project's own documentation. Built on Databricks Free Edition, LangGraph, Lakebase Postgres (pgvector), and Langfuse.

Repository: https://github.com/samu-lima/olist-data-agent
Related project: https://github.com/samu-lima/olist-lakehouse-pipeline

## Overview

This project extends the Olist Lakehouse Pipeline with a conversational layer — instead of writing SQL or digging through documentation, a user can ask questions like "which state had the highest late delivery rate?" or "why were there duplicate records in order_reviews?" and get a synthesized answer grounded in real data and real project history.

Built to demonstrate applied AI engineering on top of a real data platform: agent orchestration (LangGraph), retrieval-augmented generation (pgvector), observability (Langfuse), and evaluation (RAG eval with LLM-as-judge) — not toy examples, but a system that surfaced and fixed a real hallucination bug during development.

## Architecture

```
User question
      │
      ▼
LangGraph router ── classifies into: sql / vector / both
      │
      ├──► SQL path ──────► Gold layer (Unity Catalog, Project 1)
      │                     via Databricks SQL Statement Execution API
      │
      └──► Vector path ───► knowledge_base (pgvector, Lakebase Postgres)
                             via a Postgres RPC function, called through
                             the Lakebase Data API
      │
      ▼
Synthesizer ── combines whatever was retrieved into one final answer
      │
      ▼
Answer
```

- **Router**: an LLM classifies the question and decides which path(s) to run
- **SQL path**: an LLM generates a read-only SQL query against a fixed, documented schema of the 4 Gold tables, validated before execution, then run for real against Unity Catalog
- **Vector path**: the question is embedded and compared (cosine distance) against pre-embedded chunks of Project 1's documentation
- **Synthesizer**: combines both results (when applicable) into a natural-language answer, instructed not to state anything unsupported by the retrieved context

## Tech Stack

- **Platform**: Databricks Free Edition
- **Orchestration**: LangGraph (`StateGraph`, typed state, conditional + parallel edges)
- **Vector store**: Lakebase Postgres (Autoscaling) + pgvector extension
- **Data access**: Lakebase Data API (REST/PostgREST) for the vector store; Databricks SQL Statement Execution API for the Gold layer
- **Models** (Databricks AI Gateway, pay-per-token): `gpt-oss-120b` for routing/SQL generation/synthesis/judging, `qwen3-embedding-0-6b` (1024 dimensions) for embeddings
- **Observability**: Langfuse Cloud (`@observe` decorators on every node)
- **Evaluation**: custom RAG eval — semantic similarity (cosine, embedding-based) + LLM-as-judge (correctness, completeness, hallucination check)
- **Auth**: Databricks Service Principal (OAuth client-credentials), credentials stored in Databricks Secrets

## Why a Service Principal, not the project owner account

The Lakebase Data API's `authenticator` role cannot assume identities with elevated privileges — meaning the project owner account (used to create the Lakebase project) structurally cannot authenticate against the Data API. A Service Principal was created specifically for this purpose, granted the minimum required permissions (via `databricks_create_role` on Postgres, and `USE CATALOG` / `USE SCHEMA` / `SELECT` on Unity Catalog), and used for all agent operations. This also reflects real-world practice: application identities shouldn't carry the elevated privileges of whoever administers the infrastructure.

## Project Structure

```
├── setup/
│   ├── 01_pgvector.sql                 # pgvector extension + knowledge_base table
│   └── 02_service_principal_auth.py    # OAuth client-credentials auth, via Databricks Secrets
├── 01_populate_knowledge_base.py       # Chunks Project 1's README, embeds and stores them
├── 02_agent_orchestration.py           # SQL path, vector path, router, synthesizer, LangGraph, Langfuse, RAG eval
└── README.md
```

## Knowledge Base

9 chunks of Project 1's documentation (architecture, data quality findings, Gold layer insights, orchestration) were embedded and stored in `knowledge_base` (Lakebase Postgres, `VECTOR(1024)`). Semantic search is served through a Postgres function:

```sql
CREATE OR REPLACE FUNCTION match_knowledge(query_embedding vector(1024), match_count int DEFAULT 3)
RETURNS TABLE (content text, source text, similarity float)
LANGUAGE sql STABLE
AS $$
  SELECT content, source, 1 - (embedding <=> query_embedding) AS similarity
  FROM knowledge_base
  ORDER BY embedding <=> query_embedding
  LIMIT match_count;
$$;
```

Called via the Data API's RPC endpoint (`POST /rpc/match_knowledge`) — no direct Postgres driver needed from the notebook.

## SQL Path — Guardrails

The SQL path lets an LLM generate queries dynamically, which needs real safeguards:

- **Read-only enforcement**: generated SQL must start with `SELECT`; destructive keywords (`INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `TRUNCATE`, `CREATE`, `GRANT`) are rejected before execution
- **Row limit enforcement**: every non-trivial query must include a `LIMIT` clause, capped at 50 rows
- **Restricted schema visibility**: the LLM only ever sees a fixed, hand-written description of the 4 Gold tables — never the Bronze/Silver layers, so it has no way to reference or hallucinate access to raw data
- **Explicit abstention**: if the schema can't answer the question, the model is instructed to return `NO_ANSWER` instead of fabricating a query — this guardrail was added directly in response to a real hallucination found during evaluation (see below)

## Data Quality / Debugging Findings

| Issue | Root Cause | Decision |
|---|---|---|
| Agent answered "0 sellers have no delivered orders" (correct answer: 125) | `gold.seller_performance` only contains sellers with at least one delivered order — sellers with zero are **absent** from the table, not represented as a row with `total_orders=0`. The LLM had no way to derive the correct count from the available schema. | Added `gold.seller_summary`, a small pre-computed table with total/with-orders/without-orders seller counts. Also added the `NO_ANSWER` guardrail above, as a general safeguard against future schema gaps of this kind — the fix addresses both the specific case and the underlying pattern. |
| `execute_gold_query` crashed with `KeyError: 'data_array'` on queries returning zero rows | The SQL Statement Execution API omits the `data_array` key entirely when a query returns no rows, rather than returning an empty array | Made the result parsing defensive (`.get()` with a default), returning an empty list instead of raising |
| OAuth token (Service Principal, client-credentials flow) expired mid-session, causing `403 Invalid Token` on the Data API | The token has a short lifespan (observed: well under an hour); a SQL Warehouse cold-start delay was enough for it to expire between generation and use | Documented as a known limitation — see "What I'd Do Differently in Production" |
| `psycopg2` crashed the Python kernel on Databricks Serverless compute | `psycopg2` is a C-extension library incompatible with the serverless environment | Avoided direct Postgres drivers entirely; used the Lakebase Data API (REST) instead, which has no driver dependency |

## RAG Evaluation

A 5-question test set, each with a hand-written reference answer, scored on two independent metrics:

- **Semantic similarity**: cosine similarity between the agent's answer and the reference, both embedded via `qwen3-embedding-0-6b`
- **LLM-as-judge**: `gpt-oss-120b` scores the answer 0–10 on correctness, completeness, and absence of hallucination, with a one-sentence justification

| Question | Similarity | Judge score |
|---|---|---|
| Which state had the highest late delivery rate? | 0.840 | 10/10 |
| Why were there duplicate records in order_reviews? | 0.876 | 9/10 |
| What was the total revenue for health_beauty category? | 0.896 | 10/10 |
| How many sellers have no delivered orders yet? | 0.888 | 9/10 (was 0/10 before the fix above) |
| Why were some products marked as uncategorized? | 0.816 | 10/10 |

**Average judge score: 9.6/10** (up from 5.6/10 before the `seller_summary` fix) — the evaluation is what surfaced the hallucination in the first place, not a retrofit to make the numbers look good.

Why both metrics: semantic similarity alone did not catch the seller-count hallucination (0.823 similarity despite a factually wrong answer) — the answer was fluent and well-structured, just wrong. LLM-as-judge caught it because it evaluates factual correctness against the reference, not just phrasing similarity.

## Observability

Every node in the LangGraph (`router`, `sql_path`, `vector_path`, `synthesizer`) and the top-level `agent_run` call are instrumented with Langfuse's `@observe` decorator. Traces show the full execution tree, per-node latency, and input/output — including the parallel execution of `sql_path` and `vector_path` when the router selects `"both"`.

## Security

- Service Principal credentials (Client ID, Client Secret) are stored in Databricks Secrets, never hardcoded — the repository is safe to keep public
- Row-Level Security (RLS) is not enabled on `knowledge_base`: the dataset contains no sensitive third-party information, and access already requires Databricks authentication. This was a conscious decision, not an oversight.

## How to Run

1. Complete the setup for [Project 1](https://github.com/samu-lima/olist-lakehouse-pipeline) first (the Gold layer this agent queries)
2. Create a Lakebase Postgres project (Autoscaling) on Databricks Free Edition
3. Run `setup/01_pgvector.sql` to enable the `vector` extension and create `knowledge_base`
4. Create a Databricks Service Principal, grant it the required Postgres and Unity Catalog permissions (see notebooks for exact grants), and store its credentials in Databricks Secrets
5. Run `setup/02_service_principal_auth.py` to confirm authentication
6. Run `01_populate_knowledge_base.py` to embed and store the knowledge base
7. Set up a free [Langfuse Cloud](https://cloud.langfuse.com) project and store its keys in Databricks Secrets
8. Run `02_agent_orchestration.py` end to end

## What I'd Do Differently in Production

- **Token refresh handling**: the Service Principal's OAuth token has a short lifespan and isn't refreshed mid-session — a production agent would need automatic token renewal, not a token generated once per notebook run
- **Caching**: repeated or similar questions currently re-run the full pipeline (including LLM calls); a semantic cache would reduce cost and latency
- **Automated evaluation in CI**: the RAG evaluation is run manually today; in production it would run automatically on every change to the agent's prompts or schema context, with a minimum score threshold blocking deployment
- **Rate limiting**: no request throttling is implemented; a public-facing agent would need it
- **Row-Level Security**: would be enabled if this ever handled multi-tenant or sensitive data
- **Broader eval set**: 5 questions is enough to prove the methodology and catch a real bug, but a production system would need dozens of cases covering more edge cases

## Author

Samuel Lima — Data Engineer | [LinkedIn](https://www.linkedin.com/in/samu-lima)