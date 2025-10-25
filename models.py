"""
Pydantic Models for the Memory Management System
"""
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Union
from datetime import datetime

# --- Base Models ---
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any

class MemoryEntryBase(BaseModel):
    tenant_id: str = Field(..., description="The ID of the tenant owning the memory.")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Optional metadata for the memory entry.")

    def to_dict(self):
        """Convert the Pydantic model to a Python dict."""
        return self.dict()

# class MemoryEntryBase(BaseModel):
#     tenant_id: str = Field(..., description="The ID of the tenant owning the memory.")
#     metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Optional metadata for the memory entry.")

# --- Episodic Memory ---

class EpisodicMemoryCreate(MemoryEntryBase):
    session_id: str = Field(..., description="The session in which the interaction occurred.")
    turn_number: int = Field(..., description="The turn number within the session.")
    user_input: str
    agent_response: str
    context: Optional[Dict[str, Any]] = None

class EpisodicMemoryResponse(EpisodicMemoryCreate):
    memory_id: str
    timestamp: datetime
    s3_key: Optional[str] = None # May not always be present if not stored in S3

# --- Semantic Memory ---

class SemanticMemoryCreate(MemoryEntryBase):
    concept: str = Field(..., description="The main concept or topic of the memory.")
    content: str = Field(..., description="The detailed information about the concept.")
    embedding: Optional[List[float]] = Field(default=None, description="Vector embedding of the content.")

class SemanticMemory(BaseModel):
    id: str
    content: str
    embedding: List[float]
    metadata: Dict[str, Any]
    tags: List[str]
    timestamp: datetime
    version: int

class SemanticMemoryResponse(SemanticMemoryCreate):
    memory_id: str
    timestamp: datetime

# --- Working Memory ---
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional
from datetime import datetime


class WorkingMemoryBase(BaseModel):
    memory_id: str = Field(..., description="Unique memory ID")
    content: str = Field(..., description="Stored content as JSON string")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)
    ttl_seconds: Optional[int] = Field(3600)
    timestamp: datetime = Field(..., description="When memory was created")
    context: Optional[str] = Field("", description="Session/context identifier")


class WorkingMemoryCreate(BaseModel):
    session_id: str = Field(..., description="Session ID")
    data: Dict[str, Any] = Field(..., description="Data to store")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)
    ttl_seconds: Optional[int] = Field(3600)
    context: Optional[str] = Field("", description="Optional context")


class WorkingMemoryResponse(BaseModel):
    memory_id: str = Field(..., description="Memory ID")
    tenant_id: str = Field(..., description="Tenant ID")
    session_id: str = Field(..., description="Session ID")
    data: Dict[str, Any] = Field(..., description="Original data")
    content: str = Field(..., description="Stored content as JSON string")
    timestamp: datetime = Field(..., description="Memory creation timestamp")
    ttl_seconds: Optional[int] = Field(3600)
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)
    context: Optional[str] = Field("", description="Optional context")


# class WorkingMemoryBase(BaseModel):
#     content: str = Field(..., description="The content of the working memory")
#     metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Optional metadata")
#     ttl_seconds: Optional[int] = Field(3600, description="Time-to-live in seconds")
#     context: Optional[str] = Field("", description="Context or session identifier")
    
# class WorkingMemoryCreate(MemoryEntryBase):
#     session_id: str = Field(..., description="The session ID for the working memory.")
#     data: Dict[str, Any] = Field(..., description="The current working data for the session.")

# class WorkingMemoryResponse(WorkingMemoryCreate):
#     timestamp: datetime
#     ttl: Optional[int] = Field(default=None, description="Time-to-live for the memory entry in seconds.")

# --- Long-Term Memory ---

class LongTermMemoryCreate(MemoryEntryBase):
    entity_id: str = Field(..., description="A unique identifier for the entity being remembered (e.g., a user ID).")
    summary: str = Field(..., description="A summary of the entity's key attributes or history.")
    related_entities: Optional[List[str]] = Field(default_factory=list)
    id: Optional[str] = Field(default=None, description="Optional memory ID")  

class LongTermMemoryResponse(LongTermMemoryCreate):
    memory_id: str
    timestamp: datetime

#------procedural Memory -----
class proceduralMemoryCreate(MemoryEntryBase):
    name: str = Field(..., description="Name of the procedure.")
    steps: List[str] = Field(..., description="List of steps in the procedure.")
    metadata: Optional[dict] = None

class ProcedureCreate(BaseModel):
    name: str
    steps: List[str]
    metadata: Optional[dict] = None

class ProcedureResponse(BaseModel):
    procedure: dict
    procedure_id: str
# --- API Request/Response Models ---

class MemoryCreateRequest(BaseModel):
    memory_type: str = Field(..., description="Type of memory, e.g., 'episodic', 'semantic'.")
    data: Dict[str, Any]

class MemoryUpdateRequest(BaseModel):
    memory_type: str
    tenant_id: str
    memory_id: str
    update_data: Dict[str, Any]

class MemoryQueryRequest(BaseModel):
    memory_type: str
    tenant_id: str
    memory_id: Optional[str] = None
    session_id: Optional[str] = None
    concept: Optional[str] = None
    entity_id: Optional[str] = None
    include_content: bool = False
    limit: int = 10


# --- Short-Term Memory ---

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime

class ShorttermMemoryCreate(BaseModel):
    tenant_id: str = Field(..., description="The ID of the tenant owning the memory.")
    session_id: str = Field(..., description="The session ID for this short-term memory entry.")
    content: str = Field(..., description="The content to store in short-term memory.")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Optional metadata for the memory entry.")
    ttl_seconds: Optional[int] = Field(default=3600, description="Time-to-live for the memory entry in seconds.")

class ShorttermMemoryResponse(ShorttermMemoryCreate):
    memory_id: str = Field(..., description="Unique identifier for the memory entry.")
    timestamp: datetime = Field(..., description="Time when the memory entry was created.")

class ShorttermMemory(BaseModel):
    id: str
    content: Union[str, Dict[str, Any]]  # allows string or structured dict
    timestamp: datetime
    metadata: Dict[str, Any] = {}
    ttl_seconds: int = 604800  # default 7 days (1 week)
    session_id: str = ""
    
    def to_dict(self):
        return self.dict()

from pydantic import BaseModel
from typing import Dict, Optional

class WorkflowMemory(BaseModel):
    workflow_id: str
    content: str
    metadata: Optional[Dict] = {}
