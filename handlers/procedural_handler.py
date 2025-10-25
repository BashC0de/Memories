"""
Robust Procedural Memory Lambda Handler
Supports: Add procedure, Get procedure, List procedures
"""
import json
import sys
import os
import base64
from typing import List, Dict, Optional

# Add shared modules to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'shared'))

from utils import (
    setup_logging, get_env_var, create_response, create_error_response,
    extract_query_params, measure_execution_time
)
from services.dynamodb import DynamoDBAdapter
from utils import generate_id, logger

logger = setup_logging()

class ProceduralMemoryHandler:
    def __init__(self):
        table_name = get_env_var("PROCEDURAL_MEMORY_TABLE")
        self.dynamodb_adapter = DynamoDBAdapter(table_name)

    def add_procedure(self, name: str, steps: List[str], metadata: Optional[Dict] = None) -> Dict:
        procedure_id = generate_id("proc")
        item = {
            "procedure_id": procedure_id,
            "name": name,
            "steps": steps,
            "metadata": metadata or {}
        }
        success = self.dynamodb_adapter.put_item(item)
        if not success:
            raise Exception("Failed to store procedural memory")
        logger.info(f"Stored procedural memory: {procedure_id}")
        return item

    def get_procedure(self, procedure_id: str) -> Optional[Dict]:
        procedure = self.dynamodb_adapter.get_item({"procedure_id": procedure_id})
        if not procedure:
            logger.warning(f"Procedure not found: {procedure_id}")
            return None
        logger.info(f"Retrieved procedure: {procedure_id}")
        return procedure

    def list_procedures(self, limit: int = 20, min_success_rate: Optional[float] = None) -> List[Dict]:
        procedures = self.dynamodb_adapter.scan_items(limit=limit)
        if not isinstance(procedures, list):
            procedures = procedures.get("Items", [])
        if min_success_rate is not None:
            procedures = [p for p in procedures if p.get("success_rate", 0) >= min_success_rate]
        procedures.sort(key=lambda x: (x.get("success_rate", 0), x.get("last_used", "")), reverse=True)
        summaries = [
            {
                "procedure_id": p.get("procedure_id"),
                "name": p.get("name"),
                "description": p.get("description"),
                "success_rate": p.get("success_rate", 0),
                "last_used": p.get("last_used"),
                "step_count": len(p.get("steps", []))
            }
            for p in procedures
        ]
        return summaries


@measure_execution_time
def lambda_handler(event, context):
    """
    Unified handler:
    - POST /procedural_memory -> add procedure
    - GET /procedural_memory -> get procedure by procedure_id
    - GET /procedural_memory/list -> list procedures
    """
    try:
        logger.info(f"Incoming event: {json.dumps(event)}")

        handler = ProceduralMemoryHandler()
        method = event.get("httpMethod", "GET")
        path = event.get("path", "").rstrip("/").lower()
        body = event.get("body")
        params = extract_query_params(event)

        # Decode Base64 body if needed
        if body and event.get("isBase64Encoded", False):
            body = base64.b64decode(body).decode("utf-8")

        logger.info(f"Method: {method}, Path: {path}, Params: {params}, Body: {body}")

        # Handle POST /procedural_memory -> Add procedure
        if method.upper() == "POST" and "/procedural_memory" in path:
            if not body:
                return create_error_response(400, "Request body is required")
            try:
                data = json.loads(body)
            except Exception:
                return create_error_response(400, "Invalid JSON body")
            name = data.get("name")
            steps = data.get("steps")
            metadata = data.get("metadata")
            if not name or not steps:
                return create_error_response(422, "name and steps are required")
            procedure = handler.add_procedure(name=name, steps=steps, metadata=metadata)
            logger.info(f"Add procedure response: {procedure}")
            return create_response(201, procedure)

        # Handle GET /procedural_memory/list -> List procedures
        elif method.upper() == "GET" and "/procedural_memory/list" in path:
            limit = int(params.get("limit", 20))
            min_success_rate = params.get("min_success_rate")
            min_success_rate = float(min_success_rate) if min_success_rate else None
            procedures = handler.list_procedures(limit=limit, min_success_rate=min_success_rate)
            response = {"procedures": procedures, "count": len(procedures)}
            logger.info(f"List procedures response: {response}")
            return create_response(200, response)

        # Handle GET /procedural_memory?procedure_id=... -> Get procedure
        elif method.upper() == "GET" and "/procedural_memory" in path:
            procedure_id = params.get("procedure_id")
            if not procedure_id:
                return create_error_response(400, "procedure_id parameter is required")
            procedure = handler.get_procedure(procedure_id)
            if not procedure:
                return create_error_response(404, f"Procedure not found: {procedure_id}")
            logger.info(f"Get procedure response: {procedure}")
            return create_response(200, procedure)

        else:
            return create_error_response(405, f"Unsupported method/path: {method} {path}")

    except Exception as e:
        logger.error(f"Error in procedural_memory_handler: {e}", exc_info=True)
        return create_error_response(500, "Internal server error")
