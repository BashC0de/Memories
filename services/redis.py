"""
Storage adapters for different AWS services
"""
from ast import pattern
import json
import boto3
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import logging
import redis
import logging
from urllib.parse import urlparse
import time
from typing import Dict, Any, Optional, List
import ssl
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO) 


from utils import serialize_memory, deserialize_memory, get_env_var, serialize_for_storage
# storage.py

from models import (
    ShorttermMemoryCreate,
    EpisodicMemoryCreate,
    SemanticMemoryCreate,
    WorkingMemoryCreate,
    LongTermMemoryCreate,
)
# from Memory.services.redis import RedisAdapter
from utils import get_env_var
from datetime import datetime


def save_memory_redis(memory_type: str, data: dict):
    if memory_type == "short_term":
        memory = ShorttermMemoryCreate(**data)
    elif memory_type == "episodic":
        memory = EpisodicMemoryCreate(**data)
    elif memory_type == "semantic":
        memory = SemanticMemoryCreate(**data)
    elif memory_type == "working":
        memory = WorkingMemoryCreate(**data)
    elif memory_type == "long_term":
        memory = LongTermMemoryCreate(**data)
    else:
        raise ValueError(f"Unsupported memory type: {memory_type}")

    # save to Redis
    redis_adapter = RedisAdapter(get_env_var("REDIS_ENDPOINT"))
    # using memory id as key and storing dict as value, with TTL of 1 hour
    redis_adapter.set(memory.id, serialize_for_storage(memory.dict()), ttl_seconds=3600)

    # redis_adapter.set(memory.id, memory.dict(), ttl_seconds=3600)

    return {"status": "success", "memory_id": memory.id}

   
from utils import serialize_memory  

class RedisAdapter:
    def __init__(self, redis_url: str, connect_retries: int = 3):
        parsed = urlparse(redis_url)
        host = parsed.hostname
        port = parsed.port or 6379
        db = int(parsed.path[1:]) if parsed.path else 0
        password = parsed.password

        # Build SSL context (do NOT require certs by default in Lambda unless you manage CA)
        ssl_ctx = ssl.create_default_context()
        # If certificate verification causes issues, you can relax it (not recommended for prod):
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE

        last_exc = None
        for attempt in range(1, connect_retries + 1):
            try:
                self.client = redis.Redis(
                    host=host,
                    port=port,
                    db=db,
                    password=password,
                    decode_responses=True,
                    ssl=True,                     
                    ssl_cert_reqs=None,           
                    # ssl_context=ssl_ctx,
                    socket_connect_timeout=20,
                    socket_timeout=20,
                )
                # Try a ping
                self.client.ping()
                print(f" Redis connected (TLS) to {host}:{port}")
                return
            except Exception as e:
                print(f"Attempt {attempt} - Redis connect failed: {e}")
                last_exc = e
                time.sleep(2)

        # If here, all attempts failed
        raise RuntimeError(f"Redis connection failed after {connect_retries} attempts: {last_exc}")

    def set(self, key: str, value: dict, ttl_seconds: int = None):
        try:
            # serialize dict with datetime converted to string
            serialized_value = json.dumps(serialize_memory(value))
            if ttl_seconds:
                return self.client.setex(key, ttl_seconds, serialized_value)
            return self.client.set(key, serialized_value)
        except Exception as e:
            import logging
            logging.error(f"Redis set error: {e}")
            raise  # re-raise for debugging


    def get(self, key: str):
        try:
            value = self.client.get(key)
            if value:
                return json.loads(value)
            return None
        except Exception as e:
            import logging
            logging.error(f"Redis get error: {e}")
            return None

    def delete(self, key: str) -> bool:
        """Delete key"""
        try:
            return bool(self.client.delete(key))
        except Exception as e:
            logger.error(f"Redis delete error: {e}")
            return False
    
    def scan_keys(self, pattern: str) -> List[str]:
        """Scan keys matching pattern"""
        try:
            return list(self.client.scan_iter(match=pattern))
        except Exception as e:
            logger.error(f"Redis scan error: {e}")
            return []
    
    def get_multiple(self, keys: List[str]) -> List[Optional[Dict[str, Any]]]:
        """Get multiple values"""
        try:
            values = self.client.mget(keys)
            return [deserialize_memory(v) if v else None for v in values]
        except Exception as e:
            logger.error(f"Redis mget error: {e}")
            return [None] * len(keys)
        
    def keys(self, pattern: str):
        """Return a list of Redis keys matching the given pattern."""
        try:
            return [key.decode('utf-8') for key in self.client.keys(pattern)]
        except Exception as e:
            print(f"Error fetching keys with pattern {pattern}: {e}")
        return []
