# coder_ui + dsm Integration

## Overview

[coder_ui](~/repos/dev/coder_ui) is a web UI for Claude Code — React frontend + FastAPI backend + WebSocket streaming. The backend spawns `claude` as a subprocess using `--output-format stream-json`, streaming messages to the browser in real time.

Currently coder_ui runs locally and requires `claude` in PATH on the host. Running it inside a dsm container would give isolated, persistent, per-project coder_ui instances.

## How coder_ui works

```
Browser (React) ←WebSocket→ FastAPI Backend ←subprocess.Popen→ Claude Code CLI
                                  ↓
                            SQLite (tasks, messages)
```

- **Backend:** `uvicorn src.backend.api.main:app --port 8003`
- **Frontend:** Vite dev server on port 5173, or static build served separately
- **Transport:** `ClaudeSubprocessCLITransport` — direct Popen with stdin/stdout JSON lines
- **Session recovery:** Claude CLI session files in `.claude/projects/`, resumed via `--resume {session_id}`

Key files:
- `src/backend/core/claude_transport.py` — spawns claude subprocess
- `src/backend/services/task_manager.py` — task lifecycle, process management
- `src/backend/api/tasks.py` — REST + WebSocket endpoints

## Integration approach

Run coder_ui's backend inside a dsm container, with the frontend on the host pointing at the container's exposed port.

### What dsm container already provides
- Git worktree creation and volume mounting at `/workspace`
- `ANTHROPIC_API_KEY` injection
- devcontainer image with `claude` CLI pre-installed
- Container lifecycle (create, resume, rm, clean)

### What's needed

**1. Port mapping** — `dsm container` needs a `-p` / `--port` flag to expose ports:

```bash
dsm container -t myproject-ui /path/to/repo main \
  -p 8003:8003 \
  -- uvicorn src.backend.api.main:app --host 0.0.0.0 --port 8003
```

This adds `-p 8003:8003` to the `docker run` command.

**2. Python deps in container** — The devcontainer image needs coder_ui's dependencies (fastapi, aiosqlite, uvicorn, etc.). Options:
- Bake them into the Dockerfile
- Mount coder_ui source and `uv pip install -e .` as a setup step
- Add an `--init-cmd` flag to dsm container that runs before the main command

**3. Frontend config** — Point the frontend at the container's backend:

```bash
VITE_API_URL=http://localhost:8003 VITE_WS_URL=ws://localhost:8003 npm run dev
```

### Target UX

```bash
# Start a coder_ui-backed container session for a project
dsm container -t myapp-ui /path/to/myapp main \
  -p 8003:8003 \
  -- uvicorn src.backend.api.main:app --host 0.0.0.0 --port 8003

# Frontend on host
cd ~/repos/dev/coder_ui/src/frontend
VITE_API_URL=http://localhost:8003 npm run dev

# Management
dsm ls                    # shows myapp-ui as container session
dsm resume myapp-ui       # docker exec -it into the container
dsm rm myapp-ui           # stops and removes
```

### Architecture with dsm

```
Mac Host                          Docker Container (dsm_myapp_main)
┌──────────────────┐              ┌──────────────────────────────┐
│ Browser           │              │ /workspace (mounted worktree) │
│   ↕ WebSocket    │   port 8003  │                              │
│ React Frontend ──────────────────→ FastAPI Backend              │
│ (npm run dev)    │              │   ↕ subprocess.Popen         │
│                  │              │ claude CLI (stream-json)      │
│                  │              │   ↕                           │
│                  │              │ SQLite (tasks, messages)      │
└──────────────────┘              └──────────────────────────────┘
```

### Implementation changes to dsm

Minimal — add port mapping support to `cmd_container()`:

```python
# In argparse setup
p_container.add_argument("-p", "--port", action="append", default=[],
                         help="Port mapping (host:container), repeatable")

# In docker run command construction
for port in args.port:
    docker_cmd.extend(["-p", port])
```

Everything else (worktree, API key, container lifecycle, resume/rm/clean) works as-is.
