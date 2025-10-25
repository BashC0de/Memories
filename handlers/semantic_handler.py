"""
Semantic Memory Lambda
Stores and queries semantic memories in OpenSearch
"""

import json
import os
import sys
import hashlib
from typing import List, Dict, Any
from opensearchpy import OpenSearch, RequestsHttpConnection
from requests_aws4auth import AWS4Auth

# Add shared path
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "shared"))

from utils import (
    setup_logging,
    extract_body,
    extract_query_params,
    create_response,
    create_error_response,
    generate_id,
    current_timestamp,
)
from services.opensearch import OpenSearchAdapter

logger = setup_logging()
class SemanticMemoryHandler:
    def __init__(self, tenant_id: str = None, agent_id: str = "unknown_agent"):
        self.tenant_id = tenant_id or "default_tenant"
        self.agent_id = agent_id or "default_agent"
        endpoint = os.getenv("OPENSEARCH_ENDPOINT")
        if not endpoint:
            raise ValueError("OPENSEARCH_ENDPOINT environment variable is missing")
        self.adapter = OpenSearchAdapter(endpoint)

        logger.info(f"SemanticMemoryHandler initialized | Tenant: {self.tenant_id} | Agent: {self.agent_id}")

# ----------------------------- Embedding Utility -----------------------------
def generate_embedding(text: str) -> List[float]:
    """Simple deterministic embedding generator (placeholder)."""
    hash_obj = hashlib.md5(text.encode())
    return [float(int(hash_obj.hexdigest()[i % 32], 16) / 15.0 - 1.0) for i in range(768)]


# ----------------------------- Main Lambda Handler -----------------------------
def lambda_handler(event, context):
    """
    Handles semantic memory operations.
    - POST → Add new semantic memory
    - GET → Query memories by vector/text similarity
    """
    try:
        http_method = event.get("httpMethod", "").upper()
        opensearch_endpoint = os.getenv("OPENSEARCH_ENDPOINT")
        if not opensearch_endpoint:
            return create_error_response(500, "Missing OPENSEARCH_ENDPOINT environment variable")

        adapter = OpenSearchAdapter(opensearch_endpoint)

        if http_method == "POST":
            return handle_add_memory(event, adapter)

        elif http_method == "GET":
            return handle_query_memory(event, adapter)

        else:
            return create_error_response(405, f"Unsupported method: {http_method}")

    except Exception as e:
        logger.error(f"SemanticMemory error: {e}", exc_info=True)
        return create_error_response(500, "Internal server error")


# ----------------------------- Add Semantic Memory -----------------------------
def handle_add_memory(event, adapter: OpenSearchAdapter):
    """Handles POST requests to store semantic memories."""
    body = extract_body(event)
    content = body.get("content")

    if not content:
        return create_error_response(400, "Missing required field: content")

    # Generate embedding if not provided
    embedding = body.get("embedding") or generate_embedding(content)
    if not isinstance(embedding, list) or len(embedding) != 768:
        return create_error_response(400, "Invalid embedding format")

    metadata = body.get("metadata", {})
    metadata.update({
        "agent_id": body.get("agent_id", "unknown_agent"),
        "tenant_id": body.get("tenant_id", "default_tenant"),
        "source_type": body.get("source_type", "unknown"),
        "source_id": body.get("source_id"),
    })

    memory_id = generate_id("sem")
    document = {
        "id": memory_id,
        "content": content,
        "embedding": embedding,
        "metadata": metadata,
        "tags": body.get("tags", []),
        "timestamp": current_timestamp().isoformat(),
        "version": 1,
        "relevance_score": 0.0,
    }

    success = adapter.add_document(memory_id, document)
    if not success:
        return create_error_response(500, "Failed to store semantic memory")

    logger.info(f"Semantic memory stored: {memory_id} | Tenant: {metadata['tenant_id']}")
    return create_response(201, {"message": "Semantic memory stored successfully", "memory_id": memory_id})


# ----------------------------- Query Semantic Memory -----------------------------
def handle_query_memory(event, adapter: OpenSearchAdapter):
    """Handles GET requests for semantic memory search."""
    params = extract_query_params(event)
    query_text = params.get("query")
    if not query_text:
        return create_error_response(400, "Query parameter is required")

    search_type = params.get("search_type", "vector")
    limit = min(max(int(params.get("limit", 10)), 1), 100)
    min_score = min(max(float(params.get("min_score", 0.7)), 0.0), 1.0)
    tenant_id = params.get("tenant_id")
    agent_id = params.get("agent_id")

    filters = {}
    if tenant_id:
        filters["metadata.tenant_id"] = tenant_id
    if agent_id:
        filters["metadata.agent_id"] = agent_id

    results: List[Dict[str, Any]] = []

    if search_type == "vector":
        embedding = generate_embedding(query_text)
        results = adapter.search_by_vector(vector=embedding, size=limit, min_score=min_score, filters=filters)
    elif search_type == "text":
        results = adapter.search_by_text(query=query_text, size=limit, filters=filters)
        results = [r for r in results if r.get("relevance_score", 0) >= min_score]
    else:
        return create_error_response(400, "Invalid search_type. Use 'vector' or 'text'")

    return create_response(200, {"count": len(results), "results": results})


