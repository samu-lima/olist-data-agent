# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "5"
# ///
# MAGIC %md
# MAGIC # Populate Knowledge Base
# MAGIC
# MAGIC Chunks project documentation (README, Data Quality Findings, Gold Layer 
# MAGIC insights) into embeddings, stored in the `knowledge_base` table for 
# MAGIC semantic search by the agent.

# COMMAND ----------

# DBTITLE 1,Upgrade Databricks SDK
# MAGIC %run ./setup/02_service_principal_auth

# COMMAND ----------

knowledge_chunks = [
    {
        "content": "The Olist Lakehouse Pipeline uses a Bronze/Silver/Gold architecture on Databricks Free Edition. Bronze ingests raw data via Auto Loader with no transformations. Silver applies type casting, deduplication, and business rule validation. Gold contains business-ready aggregated tables.",
        "source": "README.md#architecture"
    },
    {
        "content": "order_reviews had a CSV parsing issue: embedded commas/quotes in free-text comments shifted columns, causing 1,070 false 'orphaned' order_id references. Fixed by re-ingesting with multiLine/quote/escape options.",
        "source": "README.md#data-quality-findings"
    },
    {
        "content": "814 duplicate review_id records were found in order_reviews after the parsing fix. Resolved by keeping the most recent record per review_id, based on review_answer_timestamp.",
        "source": "README.md#data-quality-findings"
    },
    {
        "content": "610 of 32,951 products (1.85%) were missing a category, correlated 1:1 with missing product_photos_qty, suggesting incomplete product registration. Resolved with a fallback to 'uncategorized' in the Silver layer.",
        "source": "README.md#data-quality-findings"
    },
    {
        "content": "2 categories (pc_gamer, portateis_cozinha_e_preparadores_de_alimentos) were present in products but missing from the translation table, affecting 13 products. Same 'uncategorized' fallback applied — 623 total products marked uncategorized.",
        "source": "README.md#data-quality-findings"
    },
    {
        "content": "gold.seller_performance shows revenue, average review score, and average delivery time per seller, based on delivered orders only. 2,970 of 3,095 sellers (96%) have at least one delivered order; the remaining 125 have no completed delivery yet.",
        "source": "README.md#gold-layer"
    },
    {
        "content": "gold.sales_by_category_month shows monthly revenue and order volume by category, 1,264 rows total. Top categories by all-time revenue: health_beauty (R$1,233,131.72), watches_gifts (R$1,166,176.98), bed_bath_table (R$1,023,434.76).",
        "source": "README.md#gold-layer"
    },
    {
        "content": "gold.delivery_delay_analysis covers 96,470 delivered orders. 91.9% delivered on time (avg 13.7 days ahead), 8.1% delivered late (avg 8.9 days behind). Late delivery rate is highest in Northeast/North Brazilian states: AL (23.9%), MA (19.7%), PI (16.0%), CE (15.3%) — 2-3x the national average.",
        "source": "README.md#gold-layer"
    },
    {
        "content": "The pipeline is orchestrated via Databricks Jobs with sequential task dependencies (bronze_ingestion → silver_cleaning → gold_marts), running directly from the GitHub repository. Includes retries and email alerting on failure. Daily schedule configured but left paused since the dataset is static.",
        "source": "README.md#orchestration"
    },
]

# COMMAND ----------

from openai import OpenAI
import requests

embed_client = OpenAI(
    api_key=sp_token,
    base_url=f"{WORKSPACE_URL}/ai-gateway/mlflow/v1"
)

API_URL = "https://ep-twilight-snow-d88q9n3x.database.us-east-2.cloud.databricks.com/api/2.0/workspace/7474644702297592/rest/agent_knowledge_base/public/knowledge_base"

for chunk in knowledge_chunks:
    embedding_response = embed_client.embeddings.create(
        model="system.ai.qwen3-embedding-0-6b",
        input=chunk["content"]
    )
    embedding_vector = embedding_response.data[0].embedding

    insert_response = requests.post(
        API_URL,
        headers={"Authorization": f"Bearer {sp_token}", "Content-Type": "application/json"},
        json={
            "content": chunk["content"],
            "source": chunk["source"],
            "embedding": embedding_vector
        }
    )
    print(f"{chunk['source']}: {insert_response.status_code}")

# COMMAND ----------

response = requests.get(API_URL, headers={"Authorization": f"Bearer {sp_token}"})
print(f"Total de registros: {len(response.json())}")

# COMMAND ----------

