"""
Unified Working Memory Lambda
Handles add, get, and clear operations for working memory stored in Redis.
"""

import json
import sys
import os
import time
from typing import Optional, List, Dict, Any
from datetime import datetime

# Add shared modules to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'shared'))

from services.redis import RedisAdapter
from models import WorkingMemoryBase, WorkingMemoryCreate, WorkingMemoryResponse
from utils import (
    setup_logging, get_env_var, generate_id, current_timestamp,
    extract_body, extract_query_params, create_response, create_error_response, logger
)

logger = setup_logging()


class WorkingMemoryHandler:
    def __init__(self, tenant_id: str = "default_tenant"):
        self.tenant_id = tenant_id
        redis_endpoint = get_env_var("REDIS_URL")
        self.redis = RedisAdapter(redis_endpoint)
        
    def add_memory(self, memory_data: WorkingMemoryCreate) -> WorkingMemoryResponse:
        memory_id = generate_id("wm")
        timestamp = current_timestamp()

        # Create the base memory model (use memory_id instead of id)
        memory = WorkingMemoryBase(
            memory_id=memory_id,
            content=json.dumps(memory_data.data),  # store data as JSON string
            timestamp=timestamp,
            metadata=memory_data.metadata or {},
            ttl_seconds=memory_data.ttl_seconds or 3600,
            context=memory_data.session_id
        )

        # Redis key pattern
        redis_key = f"tenant:{self.tenant_id}:session:{memory_data.session_id}:memory:{memory_id}"

        success = self.redis.set(redis_key, memory.dict(), memory.ttl_seconds)
        if not success:
            raise Exception("Failed to store working memory")

        logger.info(f"Stored working memory: {memory_id} | Tenant: {self.tenant_id}")

        # Build and return response
        return WorkingMemoryResponse(
            memory_id=memory.memory_id,
            content=memory.content,
            timestamp=memory.timestamp,
            ttl_seconds=memory.ttl_seconds,
            context=memory.context,
            metadata=memory.metadata,
            session_id=memory_data.session_id,
            tenant_id=self.tenant_id,
            data=memory_data.data
        )

    def get_memories(self, session_id: Optional[str] = None, limit: int = 10) -> List[WorkingMemoryResponse]:
        memories = []
        pattern = f"tenant:{self.tenant_id}:session:{session_id}:memory:*" if session_id else f"tenant:{self.tenant_id}:session:*:memory:*"
        keys = self.redis.keys(pattern)[:limit]

        for key in keys:
            data = self.redis.get(key)
            if data:
                mem = WorkingMemoryBase(**data)
                mem_data = json.loads(mem.content) if mem.content else {}
                memories.append(WorkingMemoryResponse(
                    memory_id=mem.id,
                    content=mem.content,
                    timestamp=mem.timestamp,
                    ttl_seconds=mem.ttl_seconds,
                    context=mem.context,
                    metadata=mem.metadata,
                    session_id=mem.context,
                    tenant_id=self.tenant_id,
                    data=mem_data
                ))

        logger.info(f"Retrieved {len(memories)} working memories | Tenant: {self.tenant_id}")
        return memories

    def clear_memory(self, memory_id: str, session_id: str):
        redis_key = f"tenant:{self.tenant_id}:session:{session_id}:memory:{memory_id}"
        self.redis.delete(redis_key)
        logger.info(f"Cleared working memory: {memory_id} | Tenant: {self.tenant_id}")



# Lambda Handler Entry Point

def lambda_handler(event, context):
    try:
        http_method = event.get("httpMethod", "").upper()
        query_params = extract_query_params(event) or {}

        # For POST, read body; else use query params
        body = extract_body(event) or {}
        tenant_id = body.get("tenant_id") if http_method == "POST" else query_params.get("tenant_id")
        tenant_id = tenant_id or "default_tenant"
        session_id = body.get("session_id") or query_params.get("session_id")

        handler = WorkingMemoryHandler(tenant_id=tenant_id)

        if http_method == "POST":
            required_fields = ["session_id", "data"]
            missing = [f for f in required_fields if f not in body]
            if missing:
                return create_error_response(400, f"Missing required fields: {', '.join(missing)}")

            memory_data = WorkingMemoryCreate(
                session_id=body["session_id"],
                data=body["data"],
                metadata=body.get("metadata"),
                ttl_seconds=body.get("ttl_seconds"),
                context=body.get("context", "")
            )
            result = handler.add_memory(memory_data)
            return create_response(201, result.dict())

        elif http_method == "GET":
            limit = int(query_params.get("limit", 10))
            memories = handler.get_memories(session_id=session_id, limit=limit)
            return create_response(200, {
                "count": len(memories),
                "memories": [m.dict() for m in memories]
            })

        elif http_method == "DELETE":
            memory_id = query_params.get("memory_id")
            if not memory_id or not session_id:
                return create_error_response(400, "memory_id and session_id are required for deletion")
            handler.clear_memory(memory_id=memory_id, session_id=session_id)
            return create_response(200, {"message": f"Memory {memory_id} cleared"})

        else:
            return create_error_response(405, f"Unsupported method: {http_method}")

    except Exception as e:
        logger.error(f"Error in working memory handler: {e}", exc_info=True)
        return create_error_response(500, "Internal server error")
