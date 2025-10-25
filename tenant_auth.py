"""
Multi-tenant authentication and authorization for Agent Memory System
"""
import json
import jwt
import boto3
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


@dataclass
class TenantContext:
    """Tenant context information"""
    tenant_id: str
    user_id: str
    permissions: List[str]
    subscription_tier: str
    rate_limits: Dict[str, int]
    metadata: Dict[str, Any]


class TenantAuthenticator:
    """Multi-tenant authentication and authorization"""
    
    def __init__(self):
        self.dynamodb = boto3.resource('dynamodb')
        self.tenants_table = self.dynamodb.Table('TenantRegistry')
        self.api_keys_table = self.dynamodb.Table('ApiKeys')
        
    def authenticate_request(self, event: Dict[str, Any]) -> Optional[TenantContext]:
        """Authenticate and authorize a request"""
        try:
            # Extract authentication information
            auth_header = event.get('headers', {}).get('Authorization', '')
            api_key = event.get('headers', {}).get('X-API-Key', '')
            
            if auth_header.startswith('Bearer '):
                # JWT token authentication
                token = auth_header[7:]
                return self._authenticate_jwt(token)
            elif api_key:
                # API key authentication
                return self._authenticate_api_key(api_key)
            else:
                logger.warning("No authentication provided")
                return None
                
        except Exception as e:
            logger.error(f"Authentication error: {str(e)}")
            return None
    
    def _authenticate_jwt(self, token: str) -> Optional[TenantContext]:
        """Authenticate using JWT token"""
        try:
            # Decode JWT (in production, use proper secret management)
            payload = jwt.decode(token, options={"verify_signature": False})
            
            tenant_id = payload.get('tenant_id')
            user_id = payload.get('user_id')
            
            if not tenant_id or not user_id:
                return None
            
            # Validate tenant exists and is active
            tenant_info = self._get_tenant_info(tenant_id)
            if not tenant_info or tenant_info.get('status') != 'active':
                return None
            
            return TenantContext(
                tenant_id=tenant_id,
                user_id=user_id,
                permissions=payload.get('permissions', []),
                subscription_tier=tenant_info.get('subscription_tier', 'basic'),
                rate_limits=tenant_info.get('rate_limits', {}),
                metadata=payload.get('metadata', {})
            )
            
        except jwt.InvalidTokenError as e:
            logger.error(f"Invalid JWT token: {str(e)}")
            return None
    
    def _authenticate_api_key(self, api_key: str) -> Optional[TenantContext]:
        """Authenticate using API key"""
        try:
            # Look up API key in DynamoDB
            response = self.api_keys_table.get_item(
                Key={'api_key': api_key}
            )
            
            if 'Item' not in response:
                logger.warning(f"Invalid API key: {api_key[:8]}...")
                return None
            
            key_info = response['Item']
            
            # Check if key is active and not expired
            if key_info.get('status') != 'active':
                return None
            
            expires_at = key_info.get('expires_at')
            if expires_at and datetime.fromisoformat(expires_at) < datetime.utcnow():
                return None
            
            tenant_id = key_info['tenant_id']
            tenant_info = self._get_tenant_info(tenant_id)
            
            if not tenant_info or tenant_info.get('status') != 'active':
                return None
            
            return TenantContext(
                tenant_id=tenant_id,
                user_id=key_info.get('user_id', 'api_user'),
                permissions=key_info.get('permissions', []),
                subscription_tier=tenant_info.get('subscription_tier', 'basic'),
                rate_limits=tenant_info.get('rate_limits', {}),
                metadata=key_info.get('metadata', {})
            )
            
        except Exception as e:
            logger.error(f"API key authentication error: {str(e)}")
            return None
    
    def _get_tenant_info(self, tenant_id: str) -> Optional[Dict[str, Any]]:
        """Get tenant information from registry"""
        try:
            response = self.tenants_table.get_item(
                Key={'tenant_id': tenant_id}
            )
            return response.get('Item')
        except Exception as e:
            logger.error(f"Error fetching tenant info: {str(e)}")
            return None
    
    def authorize_operation(self, context: TenantContext, operation: str, resource: str = None) -> bool:
        """Check if tenant is authorized for operation"""
        try:
            # Check subscription tier limits
            tier_permissions = self._get_tier_permissions(context.subscription_tier)
            if operation not in tier_permissions:
                return False
            
            # Check specific permissions
            if context.permissions and f"{operation}:{resource}" not in context.permissions:
                # Check for wildcard permissions
                if f"{operation}:*" not in context.permissions and "*:*" not in context.permissions:
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"Authorization error: {str(e)}")
            return False
    
    def _get_tier_permissions(self, tier: str) -> List[str]:
        """Get permissions for subscription tier"""
        tier_permissions = {
            'basic': [
                'memory:read', 'memory:write', 'memory:delete',
                'retrieval:query'
            ],
            'premium': [
                'memory:read', 'memory:write', 'memory:delete',
                'retrieval:query', 'retrieval:advanced',
                'graph:query', 'analytics:basic'
            ],
            'enterprise': [
                'memory:*', 'retrieval:*', 'graph:*', 
                'analytics:*', 'admin:*'
            ]
        }
        return tier_permissions.get(tier, [])
    
    def check_rate_limits(self, context: TenantContext, operation: str) -> bool:
        """Check if request is within rate limits"""
        # Implementation would use Redis or DynamoDB for rate limiting
        # For now, return True (implement based on requirements)
        return True


class TenantIsolationMixin:
    """Mixin for tenant data isolation"""
    
    def add_tenant_filter(self, query_params: Dict[str, Any], tenant_id: str) -> Dict[str, Any]:
        """Add tenant filter to query parameters"""
        if 'FilterExpression' in query_params:
            # Add tenant filter to existing filter
            query_params['FilterExpression'] = query_params['FilterExpression'] & boto3.dynamodb.conditions.Attr('tenant_id').eq(tenant_id)
        else:
            # Create new tenant filter
            query_params['FilterExpression'] = boto3.dynamodb.conditions.Attr('tenant_id').eq(tenant_id)
        
        return query_params
    
    def add_tenant_key(self, key: Dict[str, Any], tenant_id: str) -> Dict[str, Any]:
        """Add tenant_id to DynamoDB key"""
        # For composite keys, prepend tenant_id
        if 'pk' in key:
            key['pk'] = f"{tenant_id}#{key['pk']}"
        elif 'id' in key:
            key['id'] = f"{tenant_id}#{key['id']}"
        else:
            key['tenant_id'] = tenant_id
        
        return key
    
    def get_tenant_prefix(self, tenant_id: str) -> str:
        """Get S3 prefix for tenant isolation"""
        return f"tenants/{tenant_id}/"
    
    def get_tenant_index_name(self, tenant_id: str, base_name: str) -> str:
        """Get tenant-specific index name"""
        return f"{tenant_id}-{base_name}"


def require_tenant_auth(operation: str, resource: str = None):
    """Decorator for tenant authentication and authorization"""
    def decorator(func):
        def wrapper(event, context):
            authenticator = TenantAuthenticator()
            
            # Authenticate request
            tenant_context = authenticator.authenticate_request(event)
            if not tenant_context:
                return {
                    'statusCode': 401,
                    'body': json.dumps({'error': 'Authentication required'})
                }
            
            # Authorize operation
            if not authenticator.authorize_operation(tenant_context, operation, resource):
                return {
                    'statusCode': 403,
                    'body': json.dumps({'error': 'Operation not authorized'})
                }
            
            # Check rate limits
            if not authenticator.check_rate_limits(tenant_context, operation):
                return {
                    'statusCode': 429,
                    'body': json.dumps({'error': 'Rate limit exceeded'})
                }
            
            # Add tenant context to event
            event['tenant_context'] = tenant_context
            
            return func(event, context)
        
        return wrapper
    return decorator


def extract_tenant_context(event: Dict[str, Any]) -> Optional[TenantContext]:
    """Extract tenant context from Lambda event"""
    return event.get('tenant_context')


def validate_tenant_access(tenant_id: str, resource_tenant_id: str) -> bool:
    """Validate that tenant can access resource"""
    return tenant_id == resource_tenant_id