# Unified Memory API

A comprehensive memory management system for AI agents, providing unified access to multiple memory types: Short-Term, Episodic, Semantic, Long-Term, Procedural, and Working Memory. Built with FastAPI and deployable on AWS Lambda using Mangum.

## Features

- **Short-Term Memory**: Temporary storage using Redis for session-based conversations.
- **Episodic Memory**: Event-based storage using S3 for data and DynamoDB for indexing.
- **Semantic Memory**: Concept-based storage with vector embeddings using OpenSearch.
- **Long-Term Memory**: Persistent entity-based storage using DynamoDB.
- **Procedural Memory**: Step-by-step procedure storage using DynamoDB.
- **Working Memory**: Temporary task-based storage using Redis.
- **Multi-Tenant Support**: Tenant isolation with authentication.
- **Serverless Deployment**: AWS Lambda functions via SAM template.
- **FastAPI Framework**: RESTful API with automatic documentation.

## Architecture

The system is composed of:
- **API Layer**: FastAPI application handling HTTP requests.
- **Handlers**: Individual modules for each memory type.
- **Services**: Abstractions for external services (Redis, DynamoDB, OpenSearch, S3).
- **Models**: Pydantic models for request/response validation.
- **Utils**: Shared utilities and helpers.

### Memory Types Overview

| Memory Type | Storage | Purpose | Key Features |
|-------------|---------|---------|--------------|
| Short-Term | Redis | Session conversations | Fast access, TTL |
| Episodic | S3 + DynamoDB | Event sequences | Time-based queries, metadata |
| Semantic | OpenSearch | Knowledge/concepts | Vector similarity search |
| Long-Term | DynamoDB | Entity summaries | Persistent, entity-focused |
| Procedural | DynamoDB | Procedures/steps | Structured workflows |
| Working | Redis | Task context | Temporary, context-aware |

## Installation

### Prerequisites
- Python 3.12+
- AWS CLI configured (for deployment)
- Redis instance (for local development)
- OpenSearch domain (for semantic memory)

### Local Setup
1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd memory-api
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Set up environment variables:
   Create a `.env` file with:
   ```
   REDIS_SHORTTERM_ENDPOINT=redis://localhost:6379
   # Add other service endpoints as needed
   ```

4. Run locally:
   ```bash
   python app.py
   ```
   The API will be available at `http://localhost:8000`

## Deployment

### AWS Deployment
1. Install AWS SAM CLI:
   ```bash
   pip install aws-sam-cli
   ```

2. Build and deploy:
   ```bash
   sam build
   sam deploy --guided
   ```

3. The API endpoints will be available via API Gateway URLs as specified in the CloudFormation outputs.

### Environment Variables
Configure the following in your deployment environment:
- `REDIS_SHORTTERM_ENDPOINT`: Redis URL for short-term memory
- `S3_BUCKET`: S3 bucket for episodic memory
- `OPENSEARCH_ENDPOINT`: OpenSearch domain URL
- `LONGTERM_MEMORY_TABLE`: DynamoDB table name
- `PROCEDURAL_MEMORY_TABLE`: DynamoDB table name

## API Endpoints

### Short-Term Memory
- `POST /memories/shortterm` - Add memory
- `GET /memories/shortterm/{session_id}` - Get memories by session
- `GET /memories/shortterm` - Get memory by ID

### Episodic Memory
- `POST /memories/episodic` - Add memory
- `GET /memories/episodic/{session_id}` - Query memories

### Semantic Memory
- `POST /memories/semantic` - Add memory
- `GET /memories/semantic/query` - Query memories

### Long-Term Memory
- `POST /memories/longterm` - Add/update memory
- `GET /memories/longterm` - Get memory by entity ID

### Procedural Memory
- `POST /memories/procedural` - Add procedure
- `GET /memories/procedural` - Get procedure by ID

### Working Memory
- `POST /working_memory` - Add memory
- `GET /working_memory` - Get memories
- `DELETE /working_memory/{memory_id}` - Clear memory

## Usage Examples

### Adding Short-Term Memory
```bash
curl -X POST "http://localhost:8000/memories/shortterm" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user123",
    "session_id": "session456",
    "turn_number": 1,
    "user_input": "Hello",
    "agent_response": "Hi there!",
    "tenant_id": "tenant1"
  }'
```

### Querying Semantic Memory
```bash
curl -X GET "http://localhost:8000/memories/semantic/query?query=artificial%20intelligence&limit=5" \
  -H "X-Tenant-ID: tenant1" \
  -H "X-Agent-ID: agent1"
```

## Development

### Project Structure
```
├── app.py                 # Main FastAPI application
├── handlers/              # Memory type handlers
├── services/              # External service integrations
├── models.py              # Pydantic models
├── utils.py               # Utility functions
├── tenant_auth.py         # Authentication logic
├── template.yaml          # SAM deployment template
├── requirements.txt       # Python dependencies
└── README.md              # This file
```

### Testing
Run tests with:
```bash
pytest
```

### Adding New Memory Types
1. Create a new handler in `handlers/`
2. Add service integration in `services/` if needed
3. Update `app.py` with new endpoints
4. Add to `template.yaml` for deployment

## Authentication

The API supports multi-tenant authentication via headers:
- `X-Tenant-ID`: Required for tenant isolation
- `X-Agent-ID`: Optional agent identifier

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For questions or issues, please open a GitHub issue or contact the development team.
