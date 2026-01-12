# MCP Confluence Sync

**Hybrid RAG & Sync Solution for LibreChat**

This service provides a bridge between Confluence and LibreChat, enabling AI agents to search and retrieve up-to-date documentation. It uses a **Hybrid Architecture** combining robust REST APIs for management with the MCP (Model Context Protocol) for seamless AI tool integration.

## 🚀 Key Features

- **Hybrid Architecture**: 
  - **REST API**: For index management, syncing, and admin tasks.
  - **MCP Interface**: Native tool integration for LibreChat/Mesh agents.
- **Incremental Syncing**: Only syncs new or modified pages (tracks version numbers).
- **Agent-Based Indexing**: Dedicated indexes per Agent ID (e.g., `agent-123`).
- **LlamaCloud Integration**: State-of-the-art RAG pipelines using LlamaIndex.
- **Automatic Background Sync**: Built-in scheduler for periodic updates (configurable interval).
- **Secure Authentication**: OAuth-ready architecture.

## 🏗️ Architecture

```mermaid
graph TB
    User[LibreChat User] --> LC[LibreChat]
    
    subgraph "Hybrid Integration"
    LC -- MCP Protocol /mcp/sse --> HybridService
    LC -- REST API /api/indexes --> HybridService
    end
    
    subgraph "mcp-confluence Service"
    HybridService[FastAPI Service]
    HybridService --> SyncLogic[Sync Service]
    HybridService --> Scheduler[Background Scheduler]
    
    SyncLogic --> Confluence[Confluence Cloud]
    SyncLogic --> DB[(SQLite Metastore)]
    SyncLogic --> Llama[LlamaCloud (Vector DB)]
    end
```

## 🛠️ Quick Start

### 1. Prerequisites
- **Confluence Cloud** account & API Token
- **LlamaCloud** account & API Key
- **Docker & Docker Compose**

### 2. Configuration (.env)
Create a `.env` file in `mcp-confluence/` with your credentials:

```env
# Confluence Credentials
CONFLUENCE_BASE_URL=https://your-domain.atlassian.net
CONFLUENCE_EMAIL=your-email@example.com
CONFLUENCE_API_TOKEN=your-api-token
CONFLUENCE_CLOUD_ID=your-cloud-id (optional)

# LlamaCloud Credentials
LLAMA_CLOUD_API_KEY=llx-your-key
LLAMA_CLOUD_PROJECT_ID=your-project-id
# OPENAI_API_KEY=sk-... (Required if creating new LlamaCloud pipelines)

# Service Settings
API_PORT=8001
DEFAULT_SYNC_INTERVAL_MINUTES=60
DATABASE_URL=sqlite:///./confluence_sync.db
```

### 3. Run with Docker
Add to your LibreChat `docker-compose.yml`:

```yaml
  mcp-confluence:
    container_name: mcp-confluence
    build:
      context: ./mcp-confluence
    environment:
      - API_PORT=8001
    volumes:
      - ./mcp-confluence/.env:/app/.env
      - ./mcp-confluence/confluence_sync.db:/app/confluence_sync.db
    ports:
      - "8001:8001"
```

## 🔌 LibreChat Integration

### 1. Configure LibreChat (`librechat.yaml`)

Enable the MCP connection and set strong instructions:

```yaml
mcpServers:
  confluence:
    type: sse
    url: http://mcp-confluence:8001/mcp/sse
    timeout: 60000
    serverInstructions: |
      You are connected to the internal Confluence Sync system via MCP.
      CRITICAL INSTRUCTIONS:
      1. You MUST use `search_confluence` for ANY question about internal projects.
      2. Do NOT say "I don't have access". You DO have access via these tools.
      Tools available: `search_confluence`, `get_page`, `list_spaces`.
```

### 2. Usage in Chat
Start a **New Chat** (to load tools) and asking:
> "Search Confluence for AI Engineer Learning Plan"

## 📡 REST API Reference

The service exposes a full REST API on port `8001`.

### Index Management
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/indexes/` | Create a new index |
| `GET` | `/api/indexes/` | List all indexes |
| `PATCH` | `/api/indexes/{id}` | Update config (spaces, interval) |
| `DELETE` | `/api/indexes/{id}` | Delete index |

### Agent Integration
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/indexes/agent/{agent_id}` | Get index config for a specific Agent ID |
| `POST` | `/api/indexes/agent/{agent_id}/sync` | Trigger sync for an Agent's index |
| `POST` | `/api/indexes/agent/{agent_id}/query` | RAG Query via REST (App-to-App) |

### creating an Index Example
```bash
curl -X POST http://localhost:8001/api/indexes/ \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Engineering Knowledge Base",
    "agent_id": "dev-agent",
    "confluence_spaces": ["ENG", "ARCH"],
    "interval_minutes": 60
  }'
```

## 🔄 Sync Logic details

The synchronization process is efficient and incremental:

1.  **Scheduled Check**: Runs every 5 minutes (via APScheduler).
2.  **Versioning**: Checks `confluence_version` of each page against the local database.
3.  **Extraction**: Downloads new/modified pages as HTML.
4.  **Conversion**: Converts HTML to Markdown for optimal LLM consumption.
5.  **Indexing**: Uploads to LlamaCloud Pipeline.
6.  **Tracking**: Updates `synced_pages` table with new version and timestamp.

## 🐛 Troubleshooting

**"I don't have access" in Chat?**
- Ensure you started a **New Chat** to refresh the tool context.
- Verify `mcp-confluence` is running (`docker logs mcp-confluence`).
- Check if `LLAMA_CLOUD_API_KEY` is valid.

**Authentication Errors?**
- Verify `CONFLUENCE_API_TOKEN` and `CONFLUENCE_EMAIL`.
- Note: `OPENAI_API_KEY` is required only for creating *new* LlamaCloud pipelines, not for search/retrieval.