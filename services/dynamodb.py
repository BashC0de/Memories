"""
Storage adapters for different AWS services
"""
import json
import boto3
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import logging

from utils import serialize_memory, deserialize_memory, get_env_var
# storage.py

from models import (
    EpisodicMemoryCreate,
    EpisodicMemoryResponse,
)

def save_memory(memory_type: str, data: dict):
    if memory_type == "episodic":
        memory = EpisodicMemoryCreate(**data)
    else:
        raise ValueError(f"Unsupported memory type: {memory_type}")
    
    # save to the right backend...
    if memory_type == "episodic":
        s3_adapter = S3Adapter(get_env_var("S3_BUCKET_NAME"))
        s3_adapter.put_object(memory.id, memory.dict()) # Simplified     # 1 hour TTL  
    elif memory_type == "long_term":
        dynamodb_adapter = DynamoDBAdapter(get_env_var("DYNAMODB_TABLE_NAME"))
        dynamodb_adapter.put_item(memory.dict())    
# Set up logging
logging.basicConfig(level=logging.INFO) 


logger = logging.getLogger(__name__)
class DynamoDBAdapter:
    """DynamoDB adapter for structured memory"""
    
    def __init__(self, table_name: str):
        self.dynamodb = boto3.resource('dynamodb')
        self.table = self.dynamodb.Table(table_name)
    
    def put_item(self, item: Dict[str, Any]) -> bool:
        """Put item in table"""
        try:
            self.table.put_item(Item=item)
            return True
        except Exception as e:
            logger.error(f"DynamoDB put error: {e}")
            return False
    
    def get_item(self, key: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Get item by key"""
        try:
            response = self.table.get_item(Key=key)
            return response.get('Item')
        except Exception as e:
            logger.error(f"DynamoDB get error: {e}")
            return None
    

    def query_items(
        self,
        key_condition,
        expression_values: Dict[str, Any],
        filter_expression=None,
        limit: Optional[int] = None,
        expression_attribute_names: Optional[Dict[str, str]] = None
    ) -> List[Dict[str, Any]]:
        """Query items with key condition and optional filter expression"""
        try:
            kwargs = {
                'KeyConditionExpression': key_condition,
                'ExpressionAttributeValues': expression_values
            }

            if expression_attribute_names:
                kwargs['ExpressionAttributeNames'] = expression_attribute_names
            if filter_expression:
                kwargs['FilterExpression'] = filter_expression
            if limit:
                kwargs['Limit'] = limit

            response = self.table.query(**kwargs)
            return response.get('Items', [])
        except Exception as e:
            logger.error(f"DynamoDB query error: {e}")
            return []

    
    def scan_items(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Scan all items"""
        try:
            kwargs = {}
            if limit:
                kwargs['Limit'] = limit
            
            response = self.table.scan(**kwargs)
            return response.get('Items', [])
        except Exception as e:
            logger.error(f"DynamoDB scan error: {e}")
            return []


class S3Adapter:
    """S3 adapter for episodic memory"""
    
    def __init__(self, bucket_name: str):
        self.s3 = boto3.client('s3')
        self.bucket_name = bucket_name
    
    def put_object(self, key: str, content: Dict[str, Any]) -> bool:
        """Put object in S3"""
        try:
            self.s3.put_object(
                Bucket=self.bucket_name,
                Key=key,
                Body=serialize_memory(content),
                ContentType='application/json'
            )
            return True
        except Exception as e:
            logger.error(f"S3 put error: {e}")
            return False
    
    def get_object(self, key: str) -> Optional[Dict[str, Any]]:
        """Get object from S3"""
        try:
            response = self.s3.get_object(Bucket=self.bucket_name, Key=key)
            content = response['Body'].read().decode('utf-8')
            return deserialize_memory(content)
        except Exception as e:
            logger.error(f"S3 get error: {e}")
            return None
    
    def list_objects(self, prefix: str, max_keys: int = 100) -> List[str]:
        """List objects with prefix"""
        try:
            response = self.s3.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=prefix,
                MaxKeys=max_keys
            )
            return [obj['Key'] for obj in response.get('Contents', [])]
        except Exception as e:
            logger.error(f"S3 list error: {e}")
            return []

