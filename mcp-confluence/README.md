# MCP Confluence Sync

Sync Confluence pages to LlamaCloud for RAG (Retrieval-Augmented Generation) with LibreChat/Mesh.

## Quick Start

### 1. Prerequisites

- Python 3.10+
- Confluence Cloud account with OAuth app
- LlamaCloud account with API key

### 2. Setup Confluence OAuth App

1. Go to [Atlassian Developer Console](https://developer.atlassian.com/console/myapps/)
2. Create a new OAuth 2.0 app
3. Add the following scopes:
   - `read:confluence-content.all`
   - `read:confluence-space.summary`
   - `offline_access`
4. Set callback URL: `http://localhost:8001/api/confluence/callback`
5. Copy Client ID and Client Secret

### 3. Setup LlamaCloud

1. Go to [LlamaCloud](https://cloud.llamaindex.ai/)
2. Create a project
3. Get your API key and Project ID

### 4. Install & Configure

```bash
# Clone and enter directory
cd mcp-confluence

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your credentials
```

### 5. Edit `.env` File

```env
# Required - Confluence OAuth
CONFLUENCE_CLIENT_ID=your-client-id
CONFLUENCE_CLIENT_SECRET=your-client-secret

# Required - LlamaCloud
LLAMA_CLOUD_API_KEY=your-api-key
LLAMA_CLOUD_PROJECT_ID=your-project-id

# Optional - Change secret in production
SECRET_KEY=change-this-in-production
```

### 6. Run the Server

```bash
# Option 1: Using uvicorn directly
uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload

# Option 2: Using Python
python -m app.main
```

Server runs at: `http://localhost:8001`
API docs at: `http://localhost:8001/docs`

---

## API Usage Flow

### Step 1: Register User (for testing)
```bash
curl -X POST http://localhost:8001/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username": "testuser", "email": "test@example.com", "password": "password123"}'
```

### Step 2: Connect Confluence
```bash
# Get OAuth URL
curl "http://localhost:8001/api/confluence/connect?state=1"
# Visit the returned authorization_url in browser
```

### Step 3: Create Index
```bash
curl -X POST "http://localhost:8001/api/indexes/?user_id=1" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My Confluence Index",
    "confluence_spaces": ["MYSPACE"],
    "interval_minutes": 60
  }'
```

### Step 4: Trigger Sync
```bash
curl -X POST "http://localhost:8001/api/indexes/1/sync?user_id=1"
```

### Step 5: View Sync History
```bash
curl "http://localhost:8001/api/indexes/1/sync-history?user_id=1"
```

---

## API Endpoints

### Authentication
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/auth/register` | Register user |
| POST | `/api/auth/login` | Login |

### Confluence OAuth
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/confluence/connect` | Get OAuth URL |
| GET | `/api/confluence/callback` | OAuth callback |
| GET | `/api/confluence/status` | Check connection |
| DELETE | `/api/confluence/disconnect` | Disconnect |

### Indexes & Sync
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/indexes/` | Create index |
| GET | `/api/indexes/` | List indexes |
| GET | `/api/indexes/{id}` | Get index |
| PATCH | `/api/indexes/{id}` | Update index |
| DELETE | `/api/indexes/{id}` | Delete index |
| POST | `/api/indexes/{id}/sync` | Trigger sync |
| GET | `/api/indexes/{id}/sync-history` | View history |

---

## Architecture

```
┌─────────────┐     ┌───────────────────┐     ┌─────────────────┐
│   Client    │────▶│ mcp-confluence    │────▶│   Confluence    │
│  (LibreChat)│     │   API (FastAPI)   │     │     Cloud       │
└─────────────┘     └─────────┬─────────┘     └─────────────────┘
                              │
                     ┌────────▼─────────┐
                     │   LlamaCloud     │
                     │   (Indexing)     │
                     └──────────────────┘
```

### Sync Flow
1. Fetch pages from configured Confluence spaces
2. Check page versions for incremental sync
3. Convert HTML content to Markdown
4. Upload to LlamaCloud pipeline
5. Track synced pages in database

### Background Scheduler
- Checks every 5 minutes for indexes needing sync
- Respects per-index `interval_minutes` setting

---

## Docker

```bash
docker build -t mcp-confluence .
docker run -p 8001:8001 --env-file .env mcp-confluence
```

---

## Project Structure

```
mcp-confluence/
├── app/
│   ├── api/
│   │   ├── auth.py           # User authentication
│   │   ├── confluence.py     # Confluence OAuth
│   │   └── indexes.py        # Index CRUD & sync
│   ├── models/
│   │   ├── user.py
│   │   ├── oauth_token.py
│   │   ├── index.py
│   │   ├── sync_config.py
│   │   ├── sync_history.py
│   │   └── synced_page.py
│   ├── services/
│   │   ├── confluence_oauth.py
│   │   ├── confluence_api.py
│   │   ├── llama_cloud.py
│   │   ├── sync_service.py
│   │   └── scheduler.py
│   ├── config.py
│   ├── database.py
│   └── main.py
├── requirements.txt
├── Dockerfile
├── .env.example
└── README.md
```