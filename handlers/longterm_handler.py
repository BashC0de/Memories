"""
Long-Term Memory Handler and Lambda
Stores and retrieves long-term memories from DynamoDB
"""

from typing import List, Optional, Dict
import os
import sys
import json
import boto3
# Add shared modules to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'shared'))
from boto3.dynamodb.conditions import Key, Attr
from models import LongTermMemoryCreate, LongTermMemoryResponse
from services.dynamodb import DynamoDBAdapter
from utils import generate_id, current_timestamp, logger, get_env_var
from utils import setup_logging, create_response, create_error_response, extract_query_params, measure_execution_time

logger = setup_logging()


# Long-Term Memory Handler

class LongTermMemoryHandler:
    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id
        table_name = get_env_var("LONGTERM_MEMORY_TABLE")
        self.dynamodb = DynamoDBAdapter(table_name)

    def update_memory(self, memory_data: LongTermMemoryCreate) -> LongTermMemoryResponse:
        """
        Store or update a long-term memory
        """
        memory_id = memory_data.id or generate_id("ltm")
        timestamp = current_timestamp()

        item: Dict = {
            "id": memory_id,
            "entity_id": memory_data.entity_id,
            "summary": memory_data.summary,
            "metadata": memory_data.metadata or {},
            "timestamp": timestamp.isoformat(),
            "tenant_id": self.tenant_id
        }

        success = self.dynamodb.put_item(item)
        if not success:
            raise Exception("Failed to store long-term memory")

        logger.info(f"Stored long-term memory: {memory_id} | Tenant: {self.tenant_id}")
        return LongTermMemoryResponse(
            memory_id=memory_id,
            entity_id=memory_data.entity_id,
            summary=memory_data.summary,
            metadata=memory_data.metadata or {},
            timestamp=timestamp,
            tenant_id=self.tenant_id
        )

    def get_memory(self, entity_id: str) -> Optional[LongTermMemoryResponse]:
        """
        Retrieve memory by entity_id for this tenant
        """
        # KeyConditionExpression for querying by entity_id
        key_condition = Key("entity_id").eq(entity_id)
        expression_values = {":eid": entity_id}

        # FilterExpression to ensure we only get items for this tenant
        filter_expression = Attr("tenant_id").eq(self.tenant_id)

        results = self.dynamodb.query_items(
            key_condition=key_condition,
            expression_values=expression_values,
            filter_expression=filter_expression
        )

        if not results:
            return None

        r = results[0]
        return LongTermMemoryResponse(
            memory_id=r["id"],
            entity_id=r["entity_id"],
            summary=r["summary"],
            metadata=r.get("metadata", {}),
            timestamp=r["timestamp"],
            tenant_id=self.tenant_id
        )
    
    def query_memories(self, user_id: str, limit: int = 10):
        """
        Query long-term memories for a specific user_id.
        Uses KeyConditionExpression with ExpressionAttributeValues.
        """
        try:
            logger.info(f"Querying long-term memories for user_id: {user_id}, limit: {limit}")

            # Create DynamoDB KeyConditionExpression
            key_condition = Key("user_id").eq(user_id)
            expression_values = {":uid": user_id}

            items = self.dynamodb.query_items(
                key_condition=key_condition,
                expression_values=expression_values,
                limit=limit
            )

            logger.info(f"Retrieved {len(items)} items from DynamoDB")
            return {
                "status": "success",
                "count": len(items),
                "memories": items
            }

        except Exception as e:
            logger.error(f"Error querying long-term memories: {e}", exc_info=True)
            return {
                "status": "error",
                "message": str(e)
            }


# Lambda Handler

@measure_execution_time
def lambda_handler(event, context):
    """
    Lambda entry point for both storing and retrieving long-term memory
    - If HTTP method is POST, it stores/updates memory
    - If HTTP method is GET, it retrieves memory by entity_id query param
    """
    try:
        #  Confirm Lambda trigger
        print("🔹 Lambda triggered successfully")
        logger.info("Lambda triggered successfully")

        # Log the incoming event (trimmed for CloudWatch readability)
        logger.info(f"Incoming event: {json.dumps(event)[:1000]}")

        # Extract tenant info
        tenant_id = event.get("headers", {}).get("X-Tenant-ID", "default_tenant")
        logger.info(f"Tenant ID: {tenant_id}")

        # Initialize handler and get method
        ltm_handler = LongTermMemoryHandler(tenant_id)
        http_method = event.get("httpMethod", "GET").upper()
        logger.info(f"HTTP Method: {http_method}")

        # --------------------------
        # GET Memory
        # --------------------------
        if http_method == "GET":
            logger.info("Processing GET request...")
            params = extract_query_params(event)
            logger.info(f"Query params: {params}")

            entity_id = params.get("entity_id")
            if not entity_id:
                logger.warning("Missing entity_id in query params")
                return create_error_response(400, "entity_id parameter is required")

            memory = ltm_handler.get_memory(entity_id)
            if not memory:
                logger.warning(f"No memory found for entity_id: {entity_id}")
                return create_error_response(404, f"Memory for entity_id {entity_id} not found")

            logger.info(f"Memory retrieved successfully for entity_id: {entity_id}")
            return create_response(200, memory.dict())

        # --------------------------
        # POST Memory
        # --------------------------
        elif http_method == "POST":
            logger.info("Processing POST request...")

            body = event.get("body")
            logger.info(f"Raw body: {body}")

            if not body:
                logger.warning("Request body missing")
                return create_error_response(400, "Request body is required")

            if isinstance(body, str):
                body = json.loads(body)

            logger.info(f"Parsed body: {body}")

            required_fields = ["entity_id", "summary"]
            missing_fields = [f for f in required_fields if f not in body]
            if missing_fields:
                logger.warning(f"Missing fields: {missing_fields}")
                return create_error_response(400, f"Missing required fields: {', '.join(missing_fields)}")

            memory_data = LongTermMemoryCreate(
                entity_id=body["entity_id"],
                summary=body["summary"],
                metadata=body.get("metadata"),
                id=body.get("id"),
                tenant_id=tenant_id
            )

            logger.info("Memory data validated successfully")

            response = ltm_handler.update_memory(memory_data)
            logger.info(f"Memory stored successfully: {response.memory_id}")

            return create_response(201, response.dict())

        # --------------------------
        # Unsupported Methods
        # --------------------------
        else:
            logger.warning(f"Unsupported HTTP method: {http_method}")
            return create_error_response(405, f"HTTP method {http_method} not allowed")

    except Exception as e:
        logger.error(f"Error in long-term memory lambda: {e}", exc_info=True)
        return create_error_response(500, str(e))
