# Databricks notebook source
# MAGIC %md
# MAGIC # Service Principal Authentication
# MAGIC
# MAGIC Sets up OAuth client-credentials authentication for the Service Principal
# MAGIC used to access the Lakebase Data API — avoiding the project owner account,
# MAGIC which the Data API's `authenticator` role cannot assume (elevated privileges
# MAGIC can't be delegated).

# COMMAND ----------

import requests

CLIENT_ID = "<APPLICATION_ID_UUID>"
CLIENT_SECRET = "<CLIENT_SECRET>"
WORKSPACE_URL = "https://dbc-cefde690-e45c.cloud.databricks.com"

token_response = requests.post(
    f"{WORKSPACE_URL}/oidc/v1/token",
    auth=(CLIENT_ID, CLIENT_SECRET),
    data={"grant_type": "client_credentials", "scope": "all-apis"}
)
sp_token = token_response.json()["access_token"]
print("Token gerado com sucesso" if sp_token else "Falha ao gerar token")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Test Data API connection

# COMMAND ----------

API_URL = "https://ep-twilight-snow-d88q9n3x.database.us-east-2.cloud.databricks.com/api/2.0/workspace/7474644702297592/rest/agent_knowledge_base/public/knowledge_base"

response = requests.get(
    API_URL,
    headers={"Authorization": f"Bearer {sp_token}"}
)
print(response.status_code)
print(response.json())
