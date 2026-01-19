# Workflow Hub v2

Minimal agentic task system with AI-powered code editing via Aider and local LLMs via Ollama.

## Quick Start

```bash
# One-command installation (creates venv, starts services, opens browser)
./install.sh

# Or start existing installation (opens browser)
./start.sh
```

Both scripts automatically open the chat UI in your browser when complete.
Use `--no-browser` flag to disable: `./start.sh --no-browser`

## Architecture

```
v2/
├── install.sh           # One-command installer (venv, deps, Docker, migrations)
├── start.sh             # Start services after installation
├── chat.html            # Single-file web UI (vanilla JS, no build step)
├── main.py              # FastAPI main API (port 8002)
├── models.py            # SQLAlchemy models (Project, Task)
├── database.py          # PostgreSQL connection
├── .env                 # Configuration (single source of truth)
│
├── scripts/
│   └── aider_api.py     # Aider HTTP wrapper API (port 8001)
│
├── docker/
│   ├── docker-compose.yml       # Container orchestration
│   ├── Dockerfile.aider-api     # Aider API container
│   ├── Dockerfile.main-api      # Main API container
│   └── Dockerfile.ollama        # Custom Ollama with init script
│
├── workspaces/          # Project workspaces (mounted to containers)
│   ├── poc/             # Proof of concept workspace
│   └── beatbridge_app/  # Example project workspace
│
├── alembic/             # Database migrations
│   ├── env.py
│   └── versions/
│
└── tests/
    ├── test_aider_api.py    # API endpoint tests
    └── test_poc_game.py     # Integration tests
```

## Installation

### Prerequisites

- Python 3.10+
- Docker Desktop
- Git

### Full Installation

```bash
cd /mnt/c/dropbox/_coding/agentic/v2
./install.sh
```

The installer will:
1. Check prerequisites (Python, Docker)
2. Create Python virtual environment
3. Install dependencies from requirements.txt
4. Install Playwright browsers
5. Create .env with defaults (if missing)
6. Start Docker services
7. Wait for all services to be healthy
8. Run database migrations
9. Pull Ollama models (qwen3:1.7b)
10. Configure agentmz.local domain
11. Open browser to the UI

### Installation Options

```bash
./install.sh --skip-models   # Skip Ollama model pulling
./install.sh --skip-hosts    # Skip /etc/hosts modification
./install.sh --no-browser    # Don't open browser at end
./install.sh --help          # Show all options
```

## Services

| Service | Port | Description |
|---------|------|-------------|
| Main API | 8002 | FastAPI - projects, tasks, health, WebSocket logs |
| Aider API | 8001 | Code editing agent with Ollama integration |
| PostgreSQL | 5433 | Database for projects and tasks |
| Ollama | 11435 | Local LLM serving |

### Docker Containers

```bash
# View status
docker compose --env-file .env -f docker/docker-compose.yml ps

# View logs
docker compose --env-file .env -f docker/docker-compose.yml logs -f

# Restart a service
docker compose --env-file .env -f docker/docker-compose.yml restart aider-api
```

## Web UI (chat.html)

The UI is a single-file vanilla JavaScript application served by the main API at `/`.

### Features

- **Project Management** - Create, edit, delete projects
- **Task Management** - Create tasks with stages (dev, qa, review, complete)
- **File Browser** - Browse workspace files, click to add as context
- **Chat Interface** - Send prompts to the AI agent
- **Model Selector** - Switch between available Ollama models
- **Container Logs** - Real-time WebSocket log streaming
- **VS Code Integration** - Double-click files to open in VS Code
- **Cookie Persistence** - Selected project and model persist across page reloads

### Cookie Persistence

The UI stores selections in browser cookies:
- `agentic_project_id` - Currently selected project
- `agentic_model` - Currently selected model

Cookies expire after 1 year and are automatically restored on page load.

## API Endpoints

### Core API Quick Reference

```bash
# Health check
curl http://localhost:8002/health/full

# List projects
curl http://localhost:8002/projects

# Create project
curl -X POST http://localhost:8002/projects \
  -H "Content-Type: application/json" \
  -d '{"name": "My App", "workspace_path": "my_app"}'

# Create task
curl -X POST http://localhost:8002/tasks \
  -H "Content-Type: application/json" \
  -d '{"project_id": 1, "title": "Add login page"}'

# Run agent
curl -X POST http://localhost:8001/api/agent/run \
  -H "Content-Type: application/json" \
  -d '{"task": "Create index.html with hello world", "workspace": "poc"}'

# Switch model
curl -X POST http://localhost:8001/api/model/switch \
  -H "Content-Type: application/json" \
  -d '{"model": "qwen3:1.7b"}'
```

### Health

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health/full` | Full system health check |
| GET | `/` | Serves chat.html UI |

### Projects

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/projects` | List all projects |
| POST | `/projects` | Create project |
| GET | `/projects/{id}` | Get project details |
| PATCH | `/projects/{id}` | Update project |
| DELETE | `/projects/{id}` | Delete project |
| GET | `/projects/{id}/files` | Get file tree |
| GET | `/projects/{id}/tasks` | List tasks (tree with subtasks) |

### Tasks

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/tasks` | Create task |
| GET | `/tasks/{id}` | Get task details |
| PATCH | `/tasks/{id}` | Update task |
| DELETE | `/tasks/{id}` | Delete task |

### Agent (Aider API)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| GET | `/api/config` | Get configuration |
| POST | `/api/config` | Update workspace/model |
| POST | `/api/agent/run` | Execute agent task |
| POST | `/api/model/switch` | Switch Ollama model |
| GET | `/api/models` | List available models |
| POST | `/api/grep` | Search file contents |
| POST | `/api/glob` | Find files by pattern |
| POST | `/api/bash` | Run shell commands |
| POST | `/api/read` | Read file contents |

### Operations

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/ops/restart/{service}` | Restart container (ollama, aider, main) |
| GET | `/logs/{container}` | Get recent container logs |
| WS | `/ws/logs/{container}` | Stream container logs |

## Configuration

All configuration is in `.env`:

```bash
# Database
DATABASE_URL=postgresql://wfhub:wfhub@localhost:5433/agentic
POSTGRES_USER=wfhub
POSTGRES_PASSWORD=wfhub
POSTGRES_DB=agentic

# Ollama LLM
OLLAMA_URL=http://localhost:11435
OLLAMA_API_BASE=http://localhost:11435

# Models
AIDER_MODEL=ollama_chat/qwen3:1.7b
AGENT_MODEL=qwen3:1.7b

# Ports
FASTAPI_PORT=8002
AIDER_API_PORT=8001

# Workspaces
WORKSPACES_DIR=workspaces
DEFAULT_WORKSPACE=poc
```

## Database

### Models

**Project**
- `id`, `name`, `workspace_path`, `environment`, `created_at`

**Task**
- `id`, `project_id`, `parent_id`, `title`, `description`
- `status`: backlog | in_progress | done | failed
- `stage`: dev | qa | review | complete

### Migrations

```bash
# Apply migrations
alembic upgrade head

# Create new migration
alembic revision --autogenerate -m "Add new column"

# Check status
alembic current
```

## Testing

```bash
# Activate venv
source venv/bin/activate

# Run all tests
pytest tests/ -v

# Run specific test
pytest tests/test_aider_api.py -v

# Run with output
pytest tests/test_poc_game.py -v -s
```

## Development

### Start Services

```bash
./start.sh                    # Default workspace, opens browser
./start.sh -w beatbridge_app  # Specific workspace
./start.sh --no-browser       # Don't open browser
```

### Manual Commands

```bash
# Start Docker services
docker compose --env-file .env -f docker/docker-compose.yml up -d

# Run migrations
source venv/bin/activate
alembic upgrade head

# View container logs
docker logs -f wfhub-v2-aider-api
docker logs -f wfhub-v2-main-api
```

### Troubleshooting

```bash
# Check service health
curl http://localhost:8002/health/full | python3 -m json.tool

# Check Ollama models
curl http://localhost:11435/api/tags

# Pull missing model
docker exec wfhub-v2-ollama ollama pull qwen3:1.7b

# Reset database (careful - deletes data!)
docker compose --env-file .env -f docker/docker-compose.yml down
docker volume rm docker_v2_pgdata
docker compose --env-file .env -f docker/docker-compose.yml up -d
alembic upgrade head
```

## Agent Flow

```
1. User sends prompt in chat UI
2. → Main API receives request
3. → Calls Aider API /api/agent/run
4. → Agent uses tools (grep, glob, bash, read, edit)
5. → Aider executes code edits
6. → Returns result (PASS/FAIL with summary)
7. → UI displays response with tool call details
```

## Workspaces

Each project has a workspace directory under `v2/workspaces/`. The agent operates within this workspace for file operations.

Special workspace: `[%root%]` - Points to the v2 project root itself (dogfooding).

Example workspace structure:
```
v2/workspaces/poc/
├── .git/
├── game/
│   └── index.html
└── chat.html
```

## Domain Configuration

The installer adds `agentmz.local` to `/etc/hosts`:
```
127.0.0.1 agentmz.local
```

Access the UI at:
- http://agentmz.local:8002
- http://localhost:8002
