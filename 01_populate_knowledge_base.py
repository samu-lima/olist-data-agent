# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "5"
# ///
# DBTITLE 1,Upgrade Databricks SDK
# Upgrade Databricks SDK to get w.postgres API for Lakebase
import importlib.metadata as md
import subprocess, sys

try:
    before = md.version("databricks-sdk")
except md.PackageNotFoundError:
    before = None

subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "databricks-sdk>=0.118.0"])

after = md.version("databricks-sdk")
print(f"databricks-sdk: {before} -> {after}  (changed={before != after})")

if before != after:
    print("Version changed — restarting Python to load the new SDK...")
    dbutils.library.restartPython()

# COMMAND ----------

from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

endpoint_name = "projects/olist-agent/branches/production/endpoints/primary"

ep = w.postgres.get_endpoint(name=endpoint_name)
print(f"Endpoint host: {ep.status.hosts.host}")
print(f"Endpoint state: {ep.status.current_state}")

# COMMAND ----------

from databricks.sdk import WorkspaceClient
import requests

w = WorkspaceClient()

# Get project ID and branch ID from the endpoint name
project_id = "olist-agent"
branch_id = "production"

# Get the Data API configuration
try:
    data_api = w.postgres.get_data_api(parent=f"projects/{project_id}/branches/{branch_id}")
    data_api_url = data_api.status.url
except Exception as e:
    print(f"Error getting Data API config: {e}")
    print("Make sure Data API is enabled for this Lakebase project.")
    raise

# Get OAuth token
token = w.config.token

# Query the knowledge_base table via Data API
headers = {
    "Authorization": f"Bearer {token}",
    "Accept": "application/json"
}

response = requests.get(
    f"{data_api_url}/public/knowledge_base",
    headers=headers
)

if response.status_code == 200:
    result = response.json()
    display(result)
else:
    print(f"Error: {response.status_code}")
    print(response.text)

# COMMAND ----------

