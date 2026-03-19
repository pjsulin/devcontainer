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

Bake coder_ui into the devcontainer image. The Dockerfile already installs `claude` via npm — same pattern. Copy coder_ui source in and install its Python deps at build time. Then `dsm container` only needs to mount the project worktree (which it already does) and expose a port. No extra volume mounts.

The frontend stays on the Mac, pointing at the container's exposed port.

### What dsm container already provides
- Git worktree creation and volume mounting at `/workspace`
- `ANTHROPIC_API_KEY` injection
- devcontainer image with `claude` CLI pre-installed
- Container lifecycle (create, resume, rm, clean)

### What's needed

**1. Dockerfile: bake in coder_ui** — Add coder_ui source and deps to the image alongside claude:

```dockerfile
# Copy coder_ui backend and install deps
COPY coder_ui/ /opt/coder_ui/
RUN cd /opt/coder_ui && uv pip install --system -e .
```

This keeps it self-contained — no extra volume mounts, no init steps. The image has claude + coder_ui backend ready to go.

**2. Port mapping in dsm** — `dsm container` needs a `-p` / `--port` flag:

```bash
dsm container -t myproject-ui /path/to/repo main \
  -p 8003:8003 \
  -- python -m uvicorn src.backend.api.main:app --host 0.0.0.0 --port 8003 --app-dir /opt/coder_ui
```

**3. SQLite persistence** — coder_ui stores tasks/messages in `./data/coder_ui.db`. Two options:
- Store it under `/workspace/.coder_ui/` so it lives in the mounted worktree and survives container recreation
- Accept it's ephemeral (MVP — tasks are cheap to recreate)

**4. Claude session files** — Claude writes to `~/.claude/projects/` inside the container. Same persistence question. For MVP, accept they're ephemeral — Claude can start fresh sessions. For durability, store under `/workspace/.claude/`.

**5. Frontend config** — Point the frontend at the container's backend:

```bash
VITE_API_URL=http://localhost:8003 VITE_WS_URL=ws://localhost:8003 npm run dev
```

### Target UX

```bash
# Start a coder_ui-backed container session for a project
dsm container -t myapp-ui /path/to/myapp main \
  -p 8003:8003 \
  -- python -m uvicorn src.backend.api.main:app --host 0.0.0.0 --port 8003 --app-dir /opt/coder_ui

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
┌──────────────────┐              ┌──────────────────────────────────┐
│ Browser           │              │ /opt/coder_ui (baked into image)  │
│   ↕ WebSocket    │   port 8003  │   FastAPI Backend                │
│ React Frontend ──────────────────→   ↕ subprocess.Popen            │
│ (npm run dev)    │              │   claude CLI (stream-json)        │
│                  │              │     cwd=/workspace                │
│                  │              │                                   │
│                  │              │ /workspace (mounted worktree)     │
│                  │              │ SQLite (tasks, messages)          │
└──────────────────┘              └──────────────────────────────────┘
```

### Implementation changes

**dsm cli.py** — add `-p`/`--port` flag to `cmd_container()`:

```python
# In argparse setup
p_container.add_argument("-p", "--port", action="append", default=[],
                         help="Port mapping (host:container), repeatable")

# In docker run command construction
for port in args.port:
    docker_cmd.extend(["-p", port])
```

**Dockerfile** — add coder_ui install after claude:

```dockerfile
COPY coder_ui/ /opt/coder_ui/
RUN cd /opt/coder_ui && uv pip install --system -e .
```

Everything else (worktree, API key, container lifecycle, resume/rm/clean) works as-is.
