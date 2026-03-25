# coder_ui + dsm Integration Plan

## Design

dsm and coder_ui are independent tools with no runtime dependency on each other.

- **dsm** manages sessions (local, SSH, container), worktrees, and container lifecycle. It doesn't know about coder_ui.
- **coder_ui** is a web UI that spawns Claude CLI subprocesses via stream-json protocol. It doesn't know about dsm.
- **The devcontainer Dockerfile** is the integration point — it installs both claude CLI and coder_ui's backend at build time.
- **The user's command** ties them together: dsm starts a container, the user tells it to run coder_ui's backend.

### Container model

One container per repo. The repo root (containing `.bare/` and all worktree directories) is mounted at `/workspace`. coder_ui creates one task per branch, each pointing at `/workspace/{branch}`. Claude maintains separate sessions per directory automatically.

```
Host                                Container (dsm_myapp)
~/repos/myapp/                 →    /workspace/
  .bare/                              .bare/
  .git                                .git
  main/                               main/        ← coder_ui task, cwd here
  feature-x/                          feature-x/   ← coder_ui task, cwd here
```

### Authentication

coder_ui strips `ANTHROPIC_API_KEY` and uses Claude CLI subscription auth. Subscription credentials live in `~/.claude/` on the host. This directory is mounted into the container so Claude CLI can authenticate. This also persists Claude session files (`~/.claude/projects/`) across container restarts.

## Changes

### 1. dsm cli.py — generic container improvements

These are general-purpose changes, not coder_ui-specific.

**a. Add `-p`/`--port` flag** (repeatable, passes through to `docker run`):

```python
p_container.add_argument("-p", "--port", action="append", default=[],
                         help="Port mapping (host:container), repeatable")

# In docker run construction:
for port in args.port:
    docker_cmd.extend(["-p", port])
```

**b. Add `-v`/`--volume` flag** (repeatable, passes through to `docker run`):

```python
p_container.add_argument("-v", "--volume", action="append", default=[],
                         help="Volume mount (host:container), repeatable")

# In docker run construction:
for vol in args.volume:
    docker_cmd.extend(["-v", vol])
```

**c. Mount repo root, not single worktree.** Change:

```python
# Before: mounts one worktree
"-v", f"{worktree_path}:/workspace"

# After: mounts repo root
"-v", f"{repo_path}:/workspace"
```

**d. Make branch argument optional.** Currently `dsm container REPO_PATH BRANCH` requires a branch. For repo-level containers, branch is not needed. Make it optional — if provided, dsm still creates the worktree but the container sees the whole repo regardless.

### 2. Dockerfile — add coder_ui backend

```dockerfile
# Existing: claude CLI
RUN npm install -g @anthropic-ai/claude-code

# New: coder_ui backend
COPY coder_ui/ /opt/coder_ui/
RUN cd /opt/coder_ui && uv pip install --system -e .
```

This is a build-time dependency of the image. dsm's source code does not reference coder_ui.

### 3. coder_ui config — SQLite path

The database path (`sqlite+aiosqlite:///./coder_ui.db`) is relative to CWD. When running inside the container, this needs to resolve to somewhere under `/workspace` so it persists across container restarts. Options:

- Set `DATABASE_URL=sqlite+aiosqlite:////workspace/.coder_ui/coder_ui.db` as an env var in the docker run command
- Or change coder_ui's default config to use an absolute path

This is a coder_ui config change, not a dsm change.

## Usage

```bash
# Build image (copies ui_coder into build context, then cleans up)
make build
# Or with custom source path:
CODER_UI_SRC=~/repos/dev/ui_coder make build

# Start container for a repo
dsm container -t myapp ~/repos/myapp \
  -p 8007:8007 \
  -v ~/.claude:/root/.claude \
  -- uvicorn src.backend.api.main:app --host 0.0.0.0 --port 8007 --app-dir /opt/coder_ui

# Frontend on host (separate terminal)
cd ~/repos/dev/ui_coder/src/frontend
VITE_API_URL=http://localhost:8007 npm run dev

# Create tasks in the UI pointing at /workspace/main, /workspace/feature-x, etc.

# Management via dsm
dsm ls                    # shows myapp as container session
dsm resume myapp          # shell into the container
dsm rm myapp              # stops and removes container
```
