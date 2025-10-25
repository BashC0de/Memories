# """
# Unified Memory Lambda Handler
# - GET  -> Workflow Memory retrieval (DynamoDB)
# - POST -> Working Memory storage (Redis)
# """

# import json
# import os
# import sys

# # Add shared modules
# sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'shared'))

# from utils import (
#     setup_logging, get_env_var, create_response, create_error_response,
#     extract_query_params, extract_body, validate_required_fields,
#     generate_id, current_timestamp, measure_execution_time
# )
# from services.dynamodb import DynamoDBAdapter
# from services.redis import RedisAdapter
# from models import WorkflowMemory

# logger = setup_logging()

# @measure_execution_time
# def lambda_handler(event, context):
#     """
#     Unified Memory Handler

#     Routes:
#     - GET  /memory?type=workflow&workflow_id=xxx -> retrieves workflow memory
#     - POST /memory?type=working                       -> stores working memory
#     """
#     try:
#         http_method = event.get("httpMethod", "").upper()
#         params = extract_query_params(event)
#         memory_type = params.get("type") or (extract_body(event).get("type") if http_method == "POST" else None)

#         if not memory_type:
#             return create_error_response(400, "Memory type is required (workflow or working)")

#         # --------------------- Workflow Memory (DynamoDB) ---------------------
#         if http_method == "GET" and memory_type.lower() == "workflow":
#             workflow_id = params.get("workflow_id")
#             if not workflow_id:
#                 return create_error_response(400, "workflow_id parameter is required")
            
#             table_name = get_env_var("WORKFLOW_MEMORY_TABLE")
#             dynamodb_adapter = DynamoDBAdapter(table_name)
#             workflow = dynamodb_adapter.get_item({"workflow_id": workflow_id})
            
#             if not workflow:
#                 return create_error_response(404, f"Workflow not found: {workflow_id}")
            
#             logger.info(f"Retrieved workflow: {workflow_id}")
#             return create_response(200, {"workflow": workflow, "workflow_id": workflow_id})

#         # --------------------- Working Memory (Redis) ---------------------
#         elif http_method == "POST" and memory_type.lower() == "working":
#             body = extract_body(event)

#             # Validate required fields
#             required_fields = ["content"]
#             missing_fields = validate_required_fields(body, required_fields)
#             if missing_fields:
#                 return create_error_response(400, f"Missing required fields: {', '.join(missing_fields)}")

#             memory_id = generate_id("wm")
#             memory = WorkflowMemory(
#                 id=memory_id,
#                 content=body["content"],
#                 timestamp=current_timestamp(),
#                 metadata=body.get("metadata", {}),
#                 ttl_seconds=body.get("ttl_seconds", 3600),
#                 context=body.get("context", "")
#             )

#             redis_endpoint = get_env_var("REDIS_WORKING_ENDPOINT")
#             redis_adapter = RedisAdapter(redis_endpoint)
#             success = redis_adapter.set(memory_id, memory.to_dict(), memory.ttl_seconds)

#             if not success:
#                 return create_error_response(500, "Failed to store working memory")

#             # Store context-based key for retrieval
#             if memory.context:
#                 context_key = f"context:{memory.context}:{memory_id}"
#                 redis_adapter.set(context_key, memory.to_dict(), memory.ttl_seconds)

#             logger.info(f"Stored working memory: {memory_id}")
#             return create_response(201, {
#                 "memory_id": memory_id,
#                 "message": "Working memory stored successfully",
#                 "ttl_seconds": memory.ttl_seconds
#             })

#         else:
#             return create_error_response(400, f"Unsupported operation for method {http_method} and type {memory_type}")

#     except Exception as e:
#         logger.error(f"Error in unified memory handler: {e}", exc_info=True)
#         return create_error_response(500, "Internal server error")
