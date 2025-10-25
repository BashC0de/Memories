"""
Unified Short-term Memory Service
Handles both Add and Get operations for short-term memory.
Uses Redis as backend with 7-day TTL.
"""

import os
import json
import logging
import time
from utils import (
    setup_logging, get_env_var, create_response, create_error_response,
    extract_body, extract_query_params, validate_required_fields,
    generate_id, current_timestamp, measure_execution_time
)
from services.redis import RedisAdapter
from models import ShorttermMemory

logger = logging.getLogger()
logger.setLevel(logging.INFO)
logger = setup_logging()


class ShorttermMemoryHandler:
    """Handles all short-term memory operations."""

    def __init__(self):
        redis_endpoint = get_env_var('REDIS_URL')
        self.redis_adapter = RedisAdapter(redis_endpoint)

    def add_memory(self, body: dict) -> dict:
        logger.info(f"add_memory called with body: {body}")
        missing_fields = validate_required_fields(body, ['content'])
        if missing_fields:
            return create_error_response(400, f"Missing required fields: {', '.join(missing_fields)}")

        memory_id = generate_id("stm")
        memory = ShorttermMemory(
            id=memory_id,
            content=body['content'],
            timestamp=current_timestamp(),
            metadata=body.get('metadata', {}),
            ttl_seconds=body.get('ttl_seconds', 604800),
            session_id=body.get('session_id', '')
        )

        logger.info(f"Storing memory in Redis with ID {memory_id}")
        success = self.redis_adapter.set(memory_id, memory.to_dict(), memory.ttl_seconds)
        logger.info(f"Redis set success: {success}")
        if not success:
            return create_error_response(500, "Failed to store memory")

        if memory.session_id:
            session_key = f"session:{memory.session_id}:{memory_id}"
            logger.info(f"Storing session memory with key {session_key}")
            self.redis_adapter.set(session_key, memory.to_dict(), memory.ttl_seconds)

        logger.info(f"Stored short-term memory: {memory_id}")
        return create_response(201, {
            'memory_id': memory_id,
            'message': 'Short-term memory stored successfully',
            'ttl_seconds': memory.ttl_seconds
        })

    def get_memory(self, params: dict) -> dict:
        logger.info(f"get_memory called with params: {params}")
        memory_id = params.get('memory_id')
        session_id = params.get('session_id')
        limit = int(params.get('limit', 10))

        if not memory_id and not session_id:
            return create_error_response(400, "Either memory_id or session_id is required")

        results = []
        if memory_id:
            logger.info(f"Fetching memory_id {memory_id} from Redis")
            memory = self.redis_adapter.get(memory_id)
            if memory:
                results.append(memory)
        elif session_id:
            pattern = f"session:{session_id}:*"
            logger.info(f"Scanning Redis keys with pattern {pattern}")
            keys = self.redis_adapter.scan_keys(pattern)
            logger.info(f"Found {len(keys)} keys for session {session_id}")
            if keys:
                memories = self.redis_adapter.get_multiple(keys[:limit])
                results = [m for m in memories if m is not None]

        logger.info(f"Retrieved {len(results)} short-term memories")
        return create_response(200, {
            'memories': results,
            'count': len(results),
            'query': {
                'memory_id': memory_id,
                'session_id': session_id,
                'limit': limit
            }
        })
# --- Unified Lambda Handler ---
@measure_execution_time
def lambda_handler(event, context):
    """
    AWS Lambda entry point for Short-term Memory Service.
    Supports:
    - POST /add → Add short-term memory
    - GET  /get  → Retrieve short-term memory
    """
    try:
        logger.info("Lambda started")
        handler = ShorttermMemoryHandler()
        http_method = event.get("httpMethod", "").upper()
        path = event.get("path", "")

        if http_method == "POST":
            body = extract_body(event)
            logger.info(f"POST request received: {body}")

            start_step = time.time()
            response = handler.add_memory(body)
            logger.info(f"add_memory completed in {time.time() - start_step:.2f}s")
            return response

        elif http_method == "GET":
            params = extract_query_params(event)
            logger.info(f"GET request received: {params}")

            start_step = time.time()
            response = handler.get_memory(params)
            logger.info(f"get_memory completed in {time.time() - start_step:.2f}s")
            return response

        logger.warning(f"Unsupported HTTP method: {http_method}")
        return create_error_response(400, f"Unsupported method: {http_method}")

    except Exception as e:
        logger.error(f"Error in shortterm_memory_handler: {str(e)}", exc_info=True)
        return create_error_response(500, "Internal server error")
