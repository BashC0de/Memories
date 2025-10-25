"""
Utility functions for the Agent Memory System
"""
import json
import logging
import os
import time
from typing import Dict, Any, List, Optional
from datetime import datetime
import hashlib
import uuid



def setup_logging(level: str = "INFO") -> logging.Logger:
    """Setup logging configuration"""
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    return logging.getLogger(__name__)


def get_env_var(name: str, default: Optional[str] = None) -> str:
    """Get environment variable with optional default"""
    value = os.getenv(name, default)
    if value is None:
        raise ValueError(f"Environment variable {name} is required")
    return value


def generate_id(prefix: str = "") -> str:
    """Generate unique ID with optional prefix"""
    unique_id = str(uuid.uuid4())
    return f"{prefix}_{unique_id}" if prefix else unique_id


def hash_content(content: str) -> str:
    """Generate hash for content deduplication"""
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def current_timestamp() -> datetime:
    """Get current UTC timestamp"""
    return datetime.utcnow()


def timestamp_to_string(timestamp: datetime) -> str:
    """Convert timestamp to ISO string"""
    return timestamp.isoformat()


def string_to_timestamp(timestamp_str: str) -> datetime:
    """Convert ISO string to timestamp"""
    return datetime.fromisoformat(timestamp_str)


def serialize_memory(obj):
    def default(o):
        if isinstance(o, datetime):
            return o.isoformat()
        raise TypeError(f"Type {type(o)} not serializable")
    return json.loads(json.dumps(obj, default=default))


def serialize_for_storage(data: dict) -> dict:
    """Recursively convert datetime to string for JSON storage"""
    for key, value in data.items():
        if isinstance(value, datetime):
            data[key] = value.isoformat()
        elif isinstance(value, dict):
            data[key] = serialize_for_storage(value)
        elif isinstance(value, list):
            data[key] = [serialize_for_storage(v) if isinstance(v, dict) else v for v in value]
    return data

from dateutil.parser import parse as parse_dt

def deserialize_memory(obj):
    # Convert ISO string back to datetime if needed
    for k, v in obj.items():
        if isinstance(v, str) and v.endswith("Z"):  # crude check for ISO UTC
            try:
                obj[k] = parse_dt(v)
            except Exception:
                pass
    return obj


def create_response(
    status_code: int,
    body: Dict[str, Any],
    headers: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """Create standardized API Gateway compatible response"""
    if headers is None:
        headers = {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
            'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS'
        }

    # ✅ Convert to JSON string before returning
    return {
        'statusCode': status_code,
        'headers': headers,
        'body': json.dumps(serialize_memory(body))
    }


def create_error_response(
    status_code: int,
    error_message: str,
    error_code: Optional[str] = None
) -> Dict[str, Any]:
    """Create standardized error response"""
    body = {
        'error': error_message,
        'timestamp': current_timestamp().isoformat()
    }
    if error_code:
        body['error_code'] = error_code
    
    return create_response(status_code, body)


def validate_required_fields(data: Dict[str, Any], required_fields: List[str]) -> List[str]:
    """Validate required fields in request data"""
    missing_fields = []
    for field in required_fields:
        if field not in data or data[field] is None:
            missing_fields.append(field)
    return missing_fields


def extract_query_params(event: Dict[str, Any]) -> Dict[str, str]:
    """Extract query parameters from Lambda event"""
    return event.get('queryStringParameters') or {}


def extract_path_params(event: Dict[str, Any]) -> Dict[str, str]:
    """Extract path parameters from Lambda event"""
    return event.get('pathParameters') or {}


def extract_body(event: Dict[str, Any]) -> Dict[str, Any]:
    """Extract and parse body from Lambda event"""
    body = event.get('body', '{}')
    if isinstance(body, str):
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return {}
    return body


def measure_execution_time(func):
    """Decorator to measure function execution time"""
    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        execution_time = (time.time() - start_time) * 1000  # Convert to milliseconds
        
        # Add execution time to result if it's a dict
        if isinstance(result, dict) and 'body' in result:
            try:
                body = json.loads(result['body'])
                body['execution_time_ms'] = round(execution_time, 2)
                result['body'] = json.dumps(serialize_memory(body))

            except (json.JSONDecodeError, TypeError):
                pass
        
        return result
    return wrapper


def chunk_text(text: str, chunk_size: int = 1000, overlap: int = 100) -> List[str]:
    """Split text into overlapping chunks"""
    if len(text) <= chunk_size:
        return [text]
    
    chunks = []
    start = 0
    
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        
        # Try to break at word boundary
        if end < len(text):
            last_space = chunk.rfind(' ')
            if last_space > chunk_size * 0.8:  # Only if we don't lose too much
                chunk = chunk[:last_space]
                end = start + last_space
        
        chunks.append(chunk.strip())
        start = end - overlap
        
        if start >= len(text):
            break
    
    return chunks


def calculate_relevance_score(query_embedding: List[float], doc_embedding: List[float]) -> float:
    """Calculate cosine similarity between embeddings"""
    if not query_embedding or not doc_embedding:
        return 0.0
    
    # Dot product
    dot_product = sum(a * b for a, b in zip(query_embedding, doc_embedding))
    
    # Magnitudes
    magnitude_a = sum(a * a for a in query_embedding) ** 0.5
    magnitude_b = sum(b * b for b in doc_embedding) ** 0.5
    
    if magnitude_a == 0 or magnitude_b == 0:
        return 0.0
    
    return dot_product / (magnitude_a * magnitude_b)


def merge_and_rank_results(
    results: List[Dict[str, Any]],
    max_results: int = 10,
    relevance_threshold: float = 0.7
) -> List[Dict[str, Any]]:
    """Merge and rank results from multiple sources"""
    # Filter by relevance threshold
    filtered_results = [
        result for result in results
        if result.get('relevance_score', 0) >= relevance_threshold
    ]
    
    # Sort by relevance score (descending) and timestamp (descending)
    sorted_results = sorted(
        filtered_results,
        key=lambda x: (x.get('relevance_score', 0), x.get('timestamp', '')),
        reverse=True
    )
    
    # Remove duplicates based on content hash
    seen_hashes = set()
    unique_results = []
    
    for result in sorted_results:
        content_hash = hash_content(result.get('content', ''))
        if content_hash not in seen_hashes:
            seen_hashes.add(content_hash)
            unique_results.append(result)
    
    return unique_results[:max_results]


# Global logger instance
logger = logging.getLogger(__name__)
