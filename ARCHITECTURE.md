# Architecture Overview

This document describes the architecture of the Workflow Hub v2 (wfhub-v2) system.

## System Overview

```
                    ┌─────────────────────────────────────────────────────┐
                    │                    Browser                           │
                    └─────────────────────────────────────────────────────┘
                                              │
                                              ▼
                    ┌─────────────────────────────────────────────────────┐
                    │              Caddy (HTTPS Reverse Proxy)            │
                    │          wfhub.localhost / api.localhost            │
                    └─────────────────────────────────────────────────────┘
                              │                               │
                              ▼                               ▼
        ┌─────────────────────────────┐     ┌─────────────────────────────┐
        │         main-api            │     │        aider-api            │
        │    (FastAPI - Port 8002)    │     │    (FastAPI - Port 8001)    │
        │   CRUD, UI, orchestration   │     │   Coding tools, LangGraph   │
        └─────────────────────────────┘     └─────────────────────────────┘
                    │       │                           │
                    │       │                           │
          ┌─────────┘       └───────────┬───────────────┘
          ▼                             ▼
┌─────────────────────┐     ┌─────────────────────────────┐
│    PostgreSQL       │     │         Ollama              │
│   (Port 5432/5433)  │     │     (Port 11434/11435)      │
│   agentic database  │     │   Local LLM inference       │
└─────────────────────┘     └─────────────────────────────┘
```

## Services

### main-api (Port 8002)
- **Role**: Central hub for CRUD operations, UI serving, and orchestration
- **Technology**: FastAPI + SQLAlchemy + PostgreSQL
- **Container**: `wfhub-v2-main-api`
- **Responsibilities**:
  - Project and task management (CRUD)
  - Workspace file browser
  - Ollama proxy (for request logging)
  - Container log streaming
  - WebSocket terminal access
  - Ollama service management (restart via SSH)

### aider-api (Port 8001)
- **Role**: Coding agent with AI-powered tools
- **Technology**: FastAPI + Aider + LangGraph
- **Container**: `wfhub-v2-aider-api`
- **Responsibilities**:
  - AI coding assistance via Aider
  - LangGraph agent orchestration
  - Tool execution (file operations, git, shell)
  - Workspace management

### ollama (Port 11434/11435)
- **Role**: Local LLM inference server
- **Technology**: Ollama + NVIDIA GPU
- **Container**: `wfhub-v2-ollama`
- **Responsibilities**:
  - LLM inference for coding models
  - Model management and caching
  - SSH server for remote restart capability

### db (Port 5432/5433)
- **Role**: Data persistence
- **Technology**: PostgreSQL 16
- **Container**: `wfhub-v2-db`
- **Database**: `agentic`

### caddy (Port 80/443)
- **Role**: HTTPS reverse proxy with local CA
- **Technology**: Caddy 2
- **Container**: `wfhub-v2-caddy`
- **Routes**:
  - `wfhub.localhost` → main-api
  - `aider.localhost` → aider-api
  - `ollama.localhost` → ollama
  - `api.localhost` → main-api

## Directory Structure

```
/mnt/c/dropbox/_coding/agentmz/
├── main.py                 # FastAPI application entry point
├── models.py               # SQLAlchemy ORM models
├── database.py             # Database connection and session
├── env_utils.py            # Environment configuration utilities
├── container_manager.py    # Docker container management
├── ARCHITECTURE.md         # This file
├── AGENTS.md               # Agent development guidelines
├── routers/                # FastAPI routers (API endpoints)
│   ├── projects.py         # Project CRUD
│   ├── tasks.py            # Task management
│   ├── workspace.py        # File browser + git
│   ├── integrations.py     # External service sync (Asana)
│   ├── ollama.py           # Ollama service management
│   ├── logs.py             # Container log streaming
│   ├── terminal.py         # WebSocket terminal
│   └── ...
├── services/               # Business logic layer
│   └── ollama_service.py   # Ollama restart service
├── core/                   # Shared utilities
│   └── context.py          # Task context building
├── integrations/           # External integrations
│   └── providers/          # Integration provider implementations
│       ├── base.py         # Abstract base class
│       └── asana.py        # Asana provider
├── agent/                  # LangGraph agent infrastructure
├── scripts/                # CLI scripts and utilities
│   └── aider_api.py        # Aider API server
├── static/                 # Static web assets
├── docker/                 # Docker configuration
│   ├── docker-compose.yml  # Container orchestration
│   ├── Dockerfile.main-api # Main API container
│   ├── Dockerfile.aider-api # Aider API container
│   ├── Dockerfile.ollama   # Ollama container with SSH
│   ├── Caddyfile           # Reverse proxy config
│   ├── ollama-init.sh      # Ollama model initialization
│   └── scripts/            # Container scripts
│       ├── generate-ssh-keys.sh  # SSH key generation
│       ├── restart-ollama.sh     # Ollama restart script
│       └── ssh-init-ollama.sh    # SSH initialization
├── tests/                  # Test suite
└── workspaces/             # User workspaces (project code)
```

## API Structure

### Router Organization

Each domain has its own router module in `/routers/`:

| Router | Prefix | Purpose |
|--------|--------|---------|
| projects | `/projects` | Project CRUD |
| tasks | `/tasks` | Task management + subtasks |
| workspace | `/workspace` | File browser + git operations |
| ollama | `/ollama` | Ollama service management |
| logs | `/logs` | Container log streaming |
| terminal | `/terminal` | WebSocket terminal |
| integrations | `/integrations` | External sync (Asana) |

### Key Endpoints

```
# Health
GET  /health              # Simple health check
GET  /health/full         # Full service health (all dependencies)

# Projects
GET  /projects            # List all projects
POST /projects            # Create project
GET  /projects/{id}       # Get project details
PUT  /projects/{id}       # Update project

# Tasks
GET  /tasks/{project_id}/tasks    # List tasks
POST /tasks/{project_id}/tasks    # Create task
GET  /tasks/{task_id}             # Get task details

# Ollama Management
GET  /ollama/status               # Service status
POST /ollama/restart              # Restart with fallback
POST /ollama/restart/ssh          # Force SSH restart
POST /ollama/restart/container    # Force container restart
```

## Container Communication

### Network

All containers are on the `wfhub-v2` Docker network and communicate via hostnames:

| From | To | Method | Endpoint |
|------|----|--------|----------|
| main-api | db | PostgreSQL | `wfhub-v2-db:5432` |
| main-api | ollama | HTTP | `http://wfhub-v2-ollama:11434` |
| main-api | ollama | SSH | `wfhub-v2-ollama:22` (restart only) |
| main-api | aider-api | HTTP | `http://wfhub-v2-aider-api:8001` |
| aider-api | db | PostgreSQL | `wfhub-v2-db:5432` |
| aider-api | main-api | HTTP | `http://wfhub-v2-main-api:8002/ollama` |

### SSH Key Management

SSH keys for container management are automatically generated and shared:

```
docker compose up
    │
    ├─► main-api starts FIRST
    │       └─► /opt/generate-ssh-keys.sh runs
    │               └─► Generates ed25519 keypair in /ssh_keys/
    │
    └─► ollama starts (after main-api healthy)
            └─► /opt/ssh-init.sh runs
                    └─► Copies public key to authorized_keys
                    └─► Starts SSH daemon
```

**Volume**: `wfhub_ssh_keys` (shared between main-api and ollama)

### Environment Variables

Key environment variables for container communication:

```bash
# main-api
DATABASE_URL=postgresql://wfhub:$POSTGRES_PASSWORD@wfhub-v2-db:5432/agentic
AIDER_API_URL=http://wfhub-v2-aider-api:8001
OLLAMA_PROXY_TARGET=http://wfhub-v2-ollama:11434
SSH_KEY_DIR=/ssh_keys
OLLAMA_SSH_HOST=wfhub-v2-ollama

# aider-api
OLLAMA_API_BASE=http://wfhub-v2-main-api:8002/ollama
DATABASE_URL=postgresql://wfhub:$POSTGRES_PASSWORD@wfhub-v2-db:5432/agentic
```

## Database Schema

### Core Entities

```
Project
├── id (PK)
├── name
├── workspace_path      # Path to workspace directory
├── environment         # local, staging, prod
└── created_at

Task
├── id (PK)
├── project_id (FK → Project)
├── parent_id (FK → Task)  # For subtasks
├── title
├── description
├── status              # pending, in_progress, completed
├── depth               # Nesting level (0 = root)
└── created_at

TaskNode                # Workflow pipeline nodes
├── id (PK)
├── task_id (FK → Task)
├── node_type           # agent, tool, condition
├── pre_hook / post_hook
└── routing_config
```

## Ollama Restart Service

The ollama restart service allows restarting the ollama process without restarting the entire container. This is useful for recovering from hung processes, memory issues, or model loading problems.

### Architecture

```
main-api                          ollama container
    │                                   │
    │  POST /ollama/restart             │
    │  ─────────────────────►           │
    │                                   │
    │  1. Try SSH restart               │
    │  ════════════════════►  SSH:22    │
    │     run /opt/restart-ollama.sh    │
    │     (kills ollama, entrypoint     │
    │      auto-restarts it)            │
    │                                   │
    │  2. If SSH fails, use Docker SDK  │
    │  ════════════════════►  Docker    │
    │     container.restart()           │
    │                                   │
```

### Restart Methods

| Method | Speed | Models | Use Case |
|--------|-------|--------|----------|
| SSH Restart | ~4-5s | Preserved in cache | Preferred - fast recovery |
| Container Restart | ~35-40s | Must reload | Fallback - guaranteed recovery |

**SSH Restart** (preferred):
- Connects via SSH using auto-generated ed25519 keys
- Executes `/opt/restart-ollama.sh` which kills the ollama process
- Entrypoint's auto-restart loop starts a new ollama instance
- Models remain in the volume cache, loaded on first request

**Container Restart** (fallback):
- Uses Docker SDK via mounted `/var/run/docker.sock`
- Completely restarts the container
- More reliable but slower
- Models reload from cache on startup

### Auto-Restart Loop

The ollama container runs an entrypoint with an auto-restart loop:

```bash
while true; do
    ollama serve &
    OLLAMA_PID=$!
    wait $OLLAMA_PID  # Blocks until ollama exits
    sleep 2           # Brief pause before restart
done
```

This allows SSH restart to work by:
1. Killing the ollama process via SSH
2. The `wait` returns, loop continues
3. New ollama instance starts automatically
4. Container stays running throughout

### SSH Key Management

Keys are automatically generated on first startup:

1. **main-api** starts first and runs `/opt/generate-ssh-keys.sh`
   - Creates ed25519 keypair in `/ssh_keys/` volume
   - Keys persist across container restarts

2. **ollama** starts and runs `/opt/ssh-init.sh`
   - Waits for public key to appear (up to 60s)
   - Copies to `/root/.ssh/authorized_keys`
   - Starts SSH daemon on port 22

**Volume**: `wfhub_ssh_keys` shared between containers

### API Endpoints

```bash
# Check ollama status (container + API health)
curl http://localhost:8002/ollama/status
# Response: {"container_status":"running","service_status":"running","models_loaded":["qwen3:1.7b",...]}

# Restart with automatic fallback (tries SSH first, then container)
curl -X POST http://localhost:8002/ollama/restart
# Response: {"success":true,"method":"ssh","message":"...","duration_seconds":4.5}

# Force SSH restart only
curl -X POST http://localhost:8002/ollama/restart/ssh

# Force container restart only
curl -X POST http://localhost:8002/ollama/restart/container
```

### Response Format

All restart endpoints return:

```json
{
  "success": true,
  "method": "ssh",           // or "container_restart"
  "message": "Ollama restarted successfully via SSH",
  "duration_seconds": 4.447
}
```

### Implementation Files

| File | Purpose |
|------|---------|
| `services/ollama_service.py` | OllamaService class with restart logic |
| `routers/ollama.py` | FastAPI endpoints |
| `docker/scripts/restart-ollama.sh` | Script executed via SSH |
| `docker/scripts/generate-ssh-keys.sh` | Key generation on main-api |
| `docker/scripts/ssh-init-ollama.sh` | SSH setup on ollama |
| `docker/Dockerfile.ollama` | SSH server + auto-restart entrypoint |

## Development

### Running Locally

```bash
cd docker
docker compose up -d
```

### Port Mapping

| Service | Container Port | Host Port |
|---------|---------------|-----------|
| db | 5432 | 5433 |
| ollama | 11434 | 11435 |
| main-api | 8002 | 8002 |
| aider-api | 8001 | 8001 |
| caddy | 80, 443 | 80, 443 |

### Volumes

| Volume | Purpose |
|--------|---------|
| `wfhub_v2_pgdata` | PostgreSQL data |
| `wfhub_ollama_data` | Ollama model cache (external) |
| `wfhub_ssh_keys` | SSH keys for container management |
| `wfhub_v2_caddy_data` | Caddy certificates |
| `wfhub_v2_caddy_config` | Caddy configuration |

### Hot Reload

Code changes are reflected immediately via volume mounts:
- `..:/app` mounts the project root in containers
- `../workspaces:/workspaces` mounts user workspaces
