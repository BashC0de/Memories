"""
Unified Memory API — Short-Term, Episodic, Semantic, Long-Term
Deployable on AWS Lambda using Mangum
"""

from dotenv import load_dotenv
load_dotenv()

import os
import sys
import json
import logging
from fastapi import FastAPI, Query, HTTPException, Request, Depends
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from mangum import Mangum


from pydantic import BaseModel
from typing import List, Optional
# ==================================================
# PATH FIXES FOR LOCAL & LAMBDA IMPORTS
# ==================================================
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(CURRENT_DIR)
sys.path.append(os.path.join(CURRENT_DIR, "handlers"))
sys.path.append(os.path.join(CURRENT_DIR, "services"))
sys.path.append(os.path.join(CURRENT_DIR, "utils"))
sys.path.append(os.path.join(CURRENT_DIR, "..", "..", "shared"))

# ==================================================
# IMPORT HANDLERS AND UTILITIES
# ==================================================
from handlers.shortterm_handler import ShorttermMemoryHandler
from handlers.episodic_handler import EpisodicMemoryHandler
from handlers.semantic_handler import SemanticMemoryHandler
from handlers.longterm_handler import LongTermMemoryHandler
from handlers.procedural_handler import ProceduralMemoryHandler
from handlers.working_handler import WorkingMemoryHandler
from utils import *
from models import *
from tenant_auth import *
from services.redis import *
from services.dynamodb import *
from services.opensearch import *

from models import SemanticMemoryCreate, SemanticMemoryResponse
from models import LongTermMemoryCreate, LongTermMemoryResponse
from models import ShorttermMemoryCreate, ShorttermMemoryRequest
from models import EpisodicMemoryCreate, EpisodicMemoryResponse 
from models import ProcedureCreate, ProcedureResponse

# ==================================================
# APP INITIALIZATION
# ==================================================
app = FastAPI(title="Unified Memory API", version="1.0.0")

# ==================================================
# SHORT-TERM MEMORY ENDPOINTS
# ==================================================
redis_endpoint = os.environ.get("REDIS_SHORTTERM_ENDPOINT")
if not redis_endpoint:
    raise RuntimeError("REDIS_SHORTTERM_ENDPOINT is not set in environment variables")
shortterm_handler = ShorttermMemoryHandler(redis_endpoint)

class ShortTermMemoryRequest(BaseModel):
    user_id: str
    session_id: str
    turn_number: int
    user_input: str
    agent_response: str
    tenant_id: str
    details: Optional[str] = None

@app.post("/memories/shortterm", status_code=201)
def add_shortterm_memory(body: ShortTermMemoryRequest):
    try:
        return shortterm_handler.add_memory(body.dict())
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/memories/shortterm/{session_id}")
def get_shortterm_memories(session_id: str, limit: int = Query(10, ge=1)):
    try:
        return shortterm_handler.get_memories_by_session(session_id, limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/memories/shortterm")
def get_shortterm_memory_by_id(memory_id: str):
    try:
        return shortterm_handler.get_memory_by_id(memory_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ==================================================
# EPISODIC MEMORY ENDPOINTS
# ==================================================
class EpisodicMemoryRequest(BaseModel):
    session_id: str
    turn_number: int
    user_input: str
    agent_response: str
    tenant_id: str
    context: Optional[dict] = None
    metadata: Optional[dict] = None

episodic_handler = EpisodicMemoryHandler()

@app.post("/memories/episodic", status_code=201)
def add_episodic_memory(req: EpisodicMemoryRequest):
    try:
        return episodic_handler.add_memory(
            session_id=req.session_id,
            turn_number=req.turn_number,
            user_input=req.user_input,
            agent_response=req.agent_response,
            context=req.context,
            metadata=req.metadata,
            tenant_id=req.tenant_id
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/memories/episodic/{session_id}")
def query_episodic_memories(
    session_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = Query(10, ge=1),
    include_content: bool = Query(False)
):
    try:
        return episodic_handler.query_memories(
            session_id=session_id,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            include_content=include_content
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ==================================================
# SEMANTIC MEMORY ENDPOINTS
# ==================================================
class AddMemoryResponse(BaseModel):
    memory_id: str
    timestamp: str
    version: Optional[int] = None
    embedding_size: Optional[int] = None
    tags: Optional[List[str]] = None
    agent_id: Optional[str] = None
    tenant_id: Optional[str] = None
    content: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

class QueryMemoryResponse(BaseModel):
    memories: List[AddMemoryResponse]
    count: int
    query: Dict[str, Any]

def get_semantic_handler(request: Request):
    tenant_id = request.headers.get("X-Tenant-ID") or None
    agent_id = request.headers.get("X-Agent-ID") or "default_agent"
    return SemanticMemoryHandler(tenant_id=tenant_id, agent_id=agent_id)

@app.post("/memories/semantic", response_model=SemanticMemoryResponse)
async def add_semantic_memory(request: Request, body: dict, handler: SemanticMemoryHandler = Depends(get_semantic_handler)):
    try:
        tenant_id = request.headers.get("X-Tenant-ID") or body.get("tenant_id")
        if not tenant_id:
            raise HTTPException(status_code=422, detail="tenant_id is required")

        concept = body.get("concept")
        if not concept:
            raise HTTPException(status_code=422, detail="concept is required")

        source_id = body.get("source_id")
        if not source_id:
            raise HTTPException(status_code=422, detail="source_id is required")

        memory_data = SemanticMemoryCreate(
            tenant_id=tenant_id,
            concept=concept,
            content=body["content"],
            embedding=body.get("embedding"),
            tags=body.get("tags"),
            metadata=body.get("metadata"),
            source_id=source_id,
            source_type=body.get("source_type")
        )

        response = handler.add_memory(memory_data)
        return response

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {e}")

@app.get("/memories/semantic/query", response_model=QueryMemoryResponse)
async def query_semantic_memory(
    request: Request,
    query: str = Query(...),
    search_type: str = Query("vector"),
    limit: int = Query(10, ge=1, le=100),
    min_score: float = Query(0.7, ge=0.0, le=1.0),
    embedding: Optional[str] = Query(None)
):
    try:
        tenant_id = request.headers.get("X-Tenant-ID")
        agent_id = request.headers.get("X-Agent-ID")
        if not tenant_id or not agent_id:
            raise HTTPException(status_code=400, detail="X-Tenant-ID and X-Agent-ID required")
        
        handler = SemanticMemoryHandler(tenant_id=tenant_id, agent_id=agent_id)

        if search_type == "vector":
            if embedding:
                query_embedding = json.loads(embedding)
            else:
                query_embedding = handler._generate_embedding(query)

            memories = handler.search_similar(query_embedding=query_embedding, top_k=limit)
        else:
            memories = handler.get_memory(concept=query)[:limit]

        return QueryMemoryResponse(
            memories=memories,
            count=len(memories),
            query={
                "text": query,
                "search_type": search_type,
                "limit": limit,
                "min_score": min_score,
                "tenant_id": tenant_id,
                "agent_id": agent_id
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {e}")

# ==================================================
# LONG-TERM MEMORY ENDPOINTS
# ==================================================
class AddLongTermMemoryRequest(BaseModel):
    entity_id: str
    summary: str
    metadata: Optional[dict] = None
    id: Optional[str] = None

@app.post("/memories/longterm", response_model=LongTermMemoryResponse)
async def add_longterm_memory(request: Request, body: AddLongTermMemoryRequest):
    tenant_id = request.headers.get("X-Tenant-ID", "default_tenant")
    ltm_handler = LongTermMemoryHandler(tenant_id)
    memory_data = LongTermMemoryCreate(
        id=body.id,
        entity_id=body.entity_id,
        summary=body.summary,
        metadata=body.metadata
    )
    try:
        return ltm_handler.update_memory(memory_data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/memories/longterm", response_model=Optional[LongTermMemoryResponse])
async def get_longterm_memory(request: Request, entity_id: str):
    tenant_id = request.headers.get("X-Tenant-ID", "default_tenant")
    ltm_handler = LongTermMemoryHandler(tenant_id)
    memory = ltm_handler.get_memory(entity_id)
    if not memory:
        raise HTTPException(status_code=404, detail=f"Memory for entity_id {entity_id} not found")
    return memory

# ===========================
# PROCEDURAL MEMORY ENDPOINTS
# ===========================

procedural_handler = ProceduralMemoryHandler()

@app.post("/memories/procedural", response_model=ProcedureResponse)
async def add_procedure(body: ProcedureCreate):
    try:
        procedure = procedural_handler.add_procedure(
            name=body.name,
            steps=body.steps,
            metadata=body.metadata
        )
        return {"procedure": procedure, "procedure_id": procedure["procedure_id"]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/memories/procedural", response_model=ProcedureResponse)
async def get_procedure(procedure_id: str = Query(..., description="Procedure ID to retrieve")):
    try:
        procedure = procedural_handler.get_procedure(procedure_id)
        if not procedure:
            raise HTTPException(status_code=404, detail=f"Procedure not found: {procedure_id}")
        return {"procedure": procedure, "procedure_id": procedure["procedure_id"]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ===========================
# Request & Response Models
# ===========================
class AddMemoryRequest(BaseModel):
    content: str
    context: Optional[str] = None
    metadata: Optional[dict] = None
    ttl_seconds: Optional[int] = 3600

class AddMemoryResponse(BaseModel):
    memory_id: str
    message: str
    ttl_seconds: int

class GetMemoryResponse(BaseModel):
    memories: List[WorkingMemoryResponse]
    count: int
    context: Optional[str] = None

class ClearMemoryResponse(BaseModel):
    memory_id: str
    message: str

# ===========================
# Helpers
# ===========================
def get_tenant_id(request: Request) -> str:
    # Retrieve tenant ID from headers or fallback
    return request.headers.get("X-Tenant-ID", "default_tenant")

# ===========================
# POST /working_memory -> Add memory
# ===========================
@app.post("/working_memory", response_model=AddMemoryResponse)
async def add_working_memory(request: Request, body: AddMemoryRequest):
    tenant_id = get_tenant_id(request)
    memory_handler = WorkingMemoryHandler(tenant_id)

    memory_data = WorkingMemoryCreate(
        content=body.content,
        context=body.context,
        metadata=body.metadata,
        ttl_seconds=body.ttl_seconds
    )

    try:
        response: WorkingMemoryResponse = memory_handler.add_memory(memory_data)
        return AddMemoryResponse(
            memory_id=response.memory_id,
            message="Working memory stored successfully",
            ttl_seconds=response.ttl_seconds
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ===========================
# GET /working_memory -> Get memories
# ===========================
@app.get("/working_memory", response_model=GetMemoryResponse)
async def get_working_memory(
    request: Request,
    context: Optional[str] = Query(None, description="Filter memories by context")
):
    tenant_id = get_tenant_id(request)
    memory_handler = WorkingMemoryHandler(tenant_id)

    try:
        memories = memory_handler.get_memories(context=context)
        return GetMemoryResponse(
            memories=memories,
            count=len(memories),
            context=context
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ===========================
# DELETE /working_memory/{memory_id} -> Clear memory
# ===========================
@app.delete("/working_memory/{memory_id}", response_model=ClearMemoryResponse)
async def clear_working_memory(request: Request, memory_id: str):
    tenant_id = get_tenant_id(request)
    memory_handler = WorkingMemoryHandler(tenant_id)

    try:
        memory_handler.clear_memory(memory_id)
        return ClearMemoryResponse(
            memory_id=memory_id,
            message="Working memory cleared successfully"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
        
# ==================================================
# MANGUM HANDLER (for AWS Lambda)
# ==================================================
handler = Mangum(app)

# ==================================================
# LOCAL DEBUG ENTRYPOINT
# ==================================================
if __name__ == "__main__":
    import uvicorn
    logging.basicConfig(level=logging.INFO)
    uvicorn.run(app, host="0.0.0.0", port=8000)
