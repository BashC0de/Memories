"""
Episodic Memory Lambda Handler
Supports both adding and querying episodic memories.
"""
from dotenv import load_dotenv
load_dotenv()

import json
import os
from utils import (
    setup_logging, create_response, create_error_response,
    extract_body, validate_required_fields, measure_execution_time
)
from services.dynamodb import S3Adapter, DynamoDBAdapter
from models import EpisodicMemoryCreate
from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field

logger = setup_logging()

# --- Business Logic Class ---
class EpisodicMemoryHandler:
    def __init__(self):
        self.s3_bucket = os.getenv('S3_BUCKET')
        self.index_table = os.getenv('EPISODIC_INDEX_TABLE')
        self.s3_adapter = S3Adapter(self.s3_bucket)
        self.dynamodb_adapter = DynamoDBAdapter(self.index_table)

    def add_memory(self, tenant_id: str, session_id: str, turn_number: int, user_input: str, agent_response: str, context: dict = None, metadata: dict = None):
        """Adds new episodic memory"""
        memory_id = f"epi_{int(datetime.utcnow().timestamp())}"
        timestamp = datetime.utcnow()

        memory = EpisodicMemoryCreate(
            id=memory_id,
            content=f"Turn {turn_number}: {user_input} -> {agent_response}",
            timestamp=timestamp,
            metadata=metadata or {},
            tenant_id=tenant_id,
            session_id=session_id,
            turn_number=turn_number,
            user_input=user_input,
            agent_response=agent_response,
            context=context or {}
        )

        s3_key = f"sessions/{session_id}/{timestamp.strftime('%Y/%m/%d')}/{memory_id}.json"
        self.s3_adapter.put_object(s3_key, json.dumps(memory.to_dict()))

        self.dynamodb_adapter.put_item({
            'session_id': session_id,
            'timestamp': timestamp.isoformat(),
            'memory_id': memory_id,
            'turn_number': turn_number,
            's3_key': s3_key,
            'user_input': user_input[:200],
            'agent_response': agent_response[:200]
        })

        return {
            "status": "success",
            "memory_id": memory_id,
            "session_id": session_id,
            "turn_number": turn_number,
            "s3_key": s3_key
        }

    def query_memories(self, session_id: str, limit: int = 10, include_content: bool = False):
        """Queries episodic memories for a session"""
        results = self.dynamodb_adapter.query_items(
            key_condition='session_id = :session_id',
            expression_values={':session_id': session_id},
            limit=limit
        )

        if include_content:
            full_data = []
            for item in results:
                s3_key = item.get('s3_key')
                content = self.s3_adapter.get_object(s3_key)
                full_data.append(content or item)
            results = full_data

        return {"count": len(results), "memories": results}


# --- Unified Lambda Handler ---
@measure_execution_time
def lambda_handler(event, context):
    """
    Unified handler that supports both add and get operations.
    Operation type is determined by HTTP method or an 'action' key.
    """

    try:
        http_method = event.get("httpMethod", "").upper()

        handler = EpisodicMemoryHandler()

        # --- POST → Add Memory ---
        if http_method == "POST":
            body = extract_body(event)
            required = ['tenant_id', 'session_id', 'turn_number', 'user_input', 'agent_response']
            missing = validate_required_fields(body, required)
            if missing:
                return create_error_response(400, f"Missing: {', '.join(missing)}")

            result = handler.add_memory(
                tenant_id=body["tenant_id"],
                session_id=body["session_id"],
                turn_number=body["turn_number"],
                user_input=body["user_input"],
                agent_response=body["agent_response"],
                context=body.get("context"),
                metadata=body.get("metadata"),
            )
            return create_response(201, result)

        # --- GET → Query Memories ---
        elif http_method == "GET":
            params = event.get("queryStringParameters", {}) or {}
            session_id = params.get("session_id")
            if not session_id:
                return create_error_response(400, "session_id is required")

            limit = int(params.get("limit", 10))
            include_content = params.get("include_content", "false").lower() == "true"
            result = handler.query_memories(session_id, limit, include_content)
            return create_response(200, result)

        else:
            return create_error_response(405, "Unsupported method")

    except Exception as e:
        logger.error(f"Error in episodic lambda handler: {e}")
        return create_error_response(500, str(e))
