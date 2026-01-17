# Workflow Hub v2

Minimal agentic task system with Aider integration for code editing.

## Architecture

```
v2/
├── main.py              # FastAPI app (port 8002)
├── models.py            # SQLAlchemy models (Project, Task)
├── database.py          # PostgreSQL connection
├── director.py          # Task orchestration loop
├── .env                 # Configuration variables
├── agent/
│   ├── aider_runner.py  # Aider API client
│   ├── runner.py        # Ollama native tool calling (alternative)
│   └── tools.py         # Agent tools (list_files, edit_file, etc.)
├── scripts/
│   └── aider_api.py     # Aider HTTP wrapper (port 8001)
├── docker/
│   ├── docker-compose.yml
│   └── Dockerfile.aider-api
├── workspaces/          # Project workspaces
│   └── poc/             # Proof of concept workspace
└── tests/
    └── test_*.py        # Playwright browser tests
```

## Quick Start

### 1. Start Services

```bash
# Terminal 1: Start Ollama (if not running)
ollama serve

# Terminal 2: Start Aider API
cd v2
source .env
python scripts/aider_api.py

# Terminal 3: Start FastAPI
cd v2
source .env
python main.py
```

### 2. Verify Services

```bash
# Ollama
curl http://localhost:11434/api/tags

# Aider API
curl http://localhost:8001/health

# FastAPI
curl http://localhost:8002/
```

### 3. Create and Trigger a Task

```bash
# Create project
curl -X POST http://localhost:8002/projects \
  -H "Content-Type: application/json" \
  -d '{"name": "My Project", "workspace_path": "poc"}'

# Create task
curl -X POST http://localhost:8002/tasks \
  -H "Content-Type: application/json" \
  -d '{"project_id": 1, "title": "Create hello world", "description": "Create index.html with animated Hello World"}'

# Trigger agent
curl -X POST http://localhost:8002/tasks/1/trigger
```

## Configuration

Edit `.env` to customize:

| Variable | Default | Description |
|----------|---------|-------------|
| `AIDER_MODEL` | `ollama_chat/qwen3:4b` | LLM model for Aider |
| `OLLAMA_URL` | `http://localhost:11434` | Ollama API endpoint |
| `DATABASE_URL` | `postgresql://wfhub:wfhub@localhost:5433/agentic` | PostgreSQL connection |
| `FASTAPI_PORT` | `8002` | FastAPI server port |
| `AIDER_API_PORT` | `8001` | Aider API server port |

## Docker Setup

```bash
cd v2/docker
docker compose up -d
```

Services:
- `wfhub-v2-db`: PostgreSQL on port 5433
- `wfhub-v2-ollama`: Ollama on port 11435
- `wfhub-v2-aider-api`: Aider API on port 8001

## API Endpoints

### Projects
- `GET /projects` - List all projects
- `POST /projects` - Create project
- `GET /projects/{id}` - Get project details
- `DELETE /projects/{id}` - Delete project

### Tasks
- `GET /projects/{id}/tasks` - List tasks (tree with subtasks)
- `POST /tasks` - Create task
- `GET /tasks/{id}` - Get task details
- `PATCH /tasks/{id}` - Update task
- `POST /tasks/{id}/trigger` - Trigger Aider agent

### Director
- `GET /director/status` - Check director status
- `POST /director/cycle` - Run one director cycle

## Models

### Project
- `id`, `name`, `workspace_path`, `environment`, `created_at`

### Task
- `id`, `project_id`, `parent_id`, `title`, `description`
- `status`: backlog | in_progress | done | failed
- `stage`: dev | qa | review | complete

## Agent Flow

```
1. POST /tasks/{id}/trigger
2. → Get task + project from DB
3. → Call aider_runner.run_agent(workspace, task)
4. → Aider API executes prompt in workspace
5. → Returns result (PASS/FAIL)
6. → Update task status
```

## Tests

```bash
cd v2
pytest tests/ -v
```

## Workspaces

Each project has a workspace directory under `v2/workspaces/`.
The Aider agent operates within this workspace for file operations.

Example workspace structure:
```
v2/workspaces/poc/
├── .git/
├── .pipeline/
│   └── result.json
├── index.html
└── styles.css
```
