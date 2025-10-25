"""
Unified Semantic Memory Lambda Handler
Handles both ADD and QUERY operations using OpenSearch
"""

import os
import json
import hashlib
from typing import List, Dict, Any
from datetime import datetime
from opensearchpy import OpenSearch, RequestsHttpConnection
from requests_aws4auth import AWS4Auth
import boto3
import logging

# ---------- Setup Logging ----------
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ---------- Helper Functions ----------
def generate_embedding(text: str) -> List[float]:
    """Simple deterministic fake embedding — replace with Bedrock/SageMaker later."""
    h = hashlib.md5(text.encode()).hexdigest()
    return [(int(h[i % 32], 16) / 15.0 - 1.0) for i in range(768)]

def get_env_var(name: str) -> str:
    val = os.getenv(name)
    if not val:
        raise EnvironmentError(f"Missing environment variable: {name}")
    return val

# ---------- OpenSearch Adapter ----------
class OpenSearchAdapter:
    def __init__(self, endpoint: str):
        logger.info(f"Connecting to OpenSearch endpoint: {endpoint}")
        service = 'es'
        region = os.getenv("AWS_REGION", "us-east-1")
        credentials = boto3.Session().get_credentials()
        awsauth = AWS4Auth(
            credentials.access_key,
            credentials.secret_key,
            region,
            service,
            session_token=credentials.token
        )

        self.client = OpenSearch(
            hosts=[{"host": endpoint.replace("https://", "").replace("http://", ""), "port": 443}],
            http_auth=awsauth,
            use_ssl=True,
            verify_certs=True,
            connection_class=RequestsHttpConnection
        )
        self.index_name = "semanticmemory"
        self._ensure_index()

    def _ensure_index(self):
        if not self.client.indices.exists(index=self.index_name):
            mapping = {
                "mappings": {
                    "properties": {
                        "id": {"type": "keyword"},
                        "content": {"type": "text"},
                        "embedding": {"type": "dense_vector", "dims": 768},
                        "timestamp": {"type": "date"},
                        "metadata": {"type": "object"},
                        "tags": {"type": "keyword"},
                        "relevance_score": {"type": "float"}
                    }
                }
            }
            self.client.indices.create(index=self.index_name, body=mapping)
            logger.info("✅ Created OpenSearch index: semanticmemory")

    def add_document(self, doc_id: str, document: Dict[str, Any]) -> bool:
        try:
            response = self.client.index(index=self.index_name, id=doc_id, body=document)
            return response.get("result") in ["created", "updated"]
        except Exception as e:
            logger.error(f"OpenSearch add error: {e}")
            return False

    def search_vector(self, vector: List[float], size=10, min_score=0.7):
        try:
            query = {
                "size": size,
                "min_score": min_score,
                "query": {
                    "script_score": {
                        "query": {"match_all": {}},
                        "script": {
                            "source": "cosineSimilarity(params.query_vector, 'embedding') + 1.0",
                            "params": {"query_vector": vector}
                        },
                    }
                },
            }
            response = self.client.search(index=self.index_name, body=query)
            results = []
            for hit in response["hits"]["hits"]:
                doc = hit["_source"]
                doc["relevance_score"] = hit["_score"] - 1.0
                results.append(doc)
            return results
        except Exception as e:
            logger.error(f"Vector search error: {e}")
            return []

    def search_text(self, query_text: str, size=10):
        try:
            query = {
                "size": size,
                "query": {"multi_match": {"query": query_text, "fields": ["content", "tags"]}},
            }
            response = self.client.search(index=self.index_name, body=query)
            results = []
            for hit in response["hits"]["hits"]:
                doc = hit["_source"]
                doc["relevance_score"] = hit["_score"]
                results.append(doc)
            return results
        except Exception as e:
            logger.error(f"Text search error: {e}")
            return []

# ---------- Utility HTTP Responses ----------
def _response(status: int, body: Dict[str, Any]):
    return {"statusCode": status, "body": json.dumps(body), "headers": {"Content-Type": "application/json"}}

def _error(status: int, message: str):
    return _response(status, {"error": message})