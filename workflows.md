# Development CLI Workflows - Mermaid Sequence Diagrams

This document contains mermaid sequence diagrams for the standard workflows supported by the development CLI defined in `cli.py`.

## 1. Git Worktree Initialization Workflow

```mermaid
sequenceDiagram
    participant U as User
    participant CLI as CLI Tool
    participant Git as Git
    participant FS as File System

    U->>CLI: init-worktree <git-url> [main-branch]
    
    alt main-branch not provided
        CLI->>Git: git ls-remote --symref <git-url> HEAD
        Git-->>CLI: default branch detected
        CLI->>U: Display detected branch
    end
    
    CLI->>FS: Create project directory
    CLI->>Git: git clone --bare <git-url> .bare/
    CLI->>FS: Write .git pointer to .bare
    CLI->>Git: git worktree add <main-branch> <main-branch>
    CLI->>U: Display success message with usage examples
```

## 2. Host Claude Session Management Workflow

```mermaid
sequenceDiagram
    participant U as User
    participant CLI as CLI Tool
    participant Git as Git
    participant Tmux as Tmux
    participant Claude as Claude Code

    U->>CLI: session [session-name] [--auto-attach]
    
    opt Auto-detect session name
        CLI->>Git: Check if in git worktree
        Git-->>CLI: Repository and branch info
        CLI->>CLI: Generate session name: repo:branch
    end
    
    CLI->>CLI: Sanitize session name
    CLI->>Tmux: Check if session exists
    
    alt Session exists
        CLI->>U: Prompt [a]ttach, [k]ill, or [c]ancel
        alt User chooses attach
            CLI->>Tmux: tmux attach -t <session>
        else User chooses kill
            CLI->>Tmux: tmux kill-session -t <session>
            CLI->>Tmux: Create new session
        else User cancels
            CLI->>U: Exit
        end
    else Session doesn't exist
        CLI->>Tmux: tmux new-session -d -s <session>
        CLI->>Tmux: Configure session (clear, echo messages)
        CLI->>CLI: Check if claude command exists
        opt Claude available
            CLI->>Tmux: Send "claude" command
        end
        CLI->>Tmux: Rename window to "claude"
        
        opt Auto-attach requested
            CLI->>Tmux: tmux attach -t <session>
        end
    end
```

## 3. Container Session Management Workflow

```mermaid
sequenceDiagram
    participant U as User
    participant CLI as CLI Tool
    participant Git as Git
    participant Docker as Docker
    participant Tmux as Tmux in Container
    participant FS as File System

    U->>CLI: con session <repo-path> <branch-name> [--auto-attach]
    
    CLI->>FS: Validate repository path exists
    CLI->>CLI: Generate sanitized session name
    CLI->>Docker: Check if container exists
    
    alt Container exists
        CLI->>Tmux: Check if tmux session exists in container
        alt Session exists in container
            CLI->>U: Prompt [a]ttach, [r]ecreate, or [c]ancel
        end
    end
    
    CLI->>FS: Check if git worktree exists for branch
    alt Worktree doesn't exist
        CLI->>Git: Create git worktree for branch
    end
    
    alt Container doesn't exist
        CLI->>CLI: Get Anthropic API key
        CLI->>Docker: docker run devcontainer with volume mounts
        CLI->>Docker: Install tmux in container
    end
    
    CLI->>Tmux: Create tmux session in container
    CLI->>Tmux: Configure session (messages, claude command)
    CLI->>U: Display connection command
    
    opt Auto-attach requested
        CLI->>Docker: docker exec -it <container> tmux attach
    end
```

## 4. Session List and Management Workflow

```mermaid
sequenceDiagram
    participant U as User
    participant CLI as CLI Tool
    participant Tmux as Tmux
    participant Docker as Docker

    alt Host session management
        U->>CLI: list
        CLI->>Tmux: tmux list-sessions
        CLI->>U: Display numbered table of sessions
        
        U->>CLI: attach <number>
        CLI->>Tmux: Get session by number
        CLI->>Tmux: tmux attach -t <session>
        
        U->>CLI: kill <number>
        CLI->>Tmux: Get session by number  
        CLI->>Tmux: tmux kill-session -t <session>
    else Container session management
        U->>CLI: con list
        CLI->>Docker: docker ps --filter name=devcontainer_
        CLI->>U: Display numbered table of containers
        
        U->>CLI: con attach <number|name>
        CLI->>Docker: Get container by number/name
        CLI->>Docker: docker exec -it <container> tmux attach
        
        U->>CLI: con kill <number|name>
        alt Number provided (kill container)
            CLI->>Docker: docker stop <container>
            CLI->>Docker: docker rm <container>
        else Name provided (kill session only)
            CLI->>Docker: docker exec <container> tmux kill-session
        end
    end
```

## 5. Bulk Session Termination Workflow

```mermaid
sequenceDiagram
    participant U as User
    participant CLI as CLI Tool
    participant Tmux as Tmux
    participant Docker as Docker

    alt Host sessions
        U->>CLI: kill-all
        CLI->>Tmux: tmux list-sessions
        CLI->>CLI: Filter for likely Claude sessions
        CLI->>U: Display sessions to be killed
        CLI->>U: Confirm termination
        alt User confirms
            loop For each session
                CLI->>Tmux: tmux kill-session -t <session>
            end
        end
    else Container sessions
        U->>CLI: con kill-all
        CLI->>Docker: docker ps --filter name=devcontainer_
        CLI->>U: Display containers to be killed
        CLI->>U: Confirm termination
        alt User confirms
            loop For each container
                CLI->>Docker: docker stop <container>
                CLI->>Docker: docker rm <container>
            end
        end
    end
```

## 6. Git Worktree Creation Within Container Session

```mermaid
sequenceDiagram
    participant CLI as CLI Tool
    participant Git as Git
    participant FS as File System

    CLI->>FS: Check if worktree path exists
    alt Worktree doesn't exist
        CLI->>Git: Try: git worktree add <path> origin/<branch>
        alt Remote branch exists
            Git-->>CLI: Success
        else Remote branch doesn't exist
            CLI->>Git: Try: git worktree add <path> <branch>
            alt Local branch exists
                Git-->>CLI: Success
            else Local branch doesn't exist
                CLI->>Git: Get default branch (main/master)
                CLI->>Git: git worktree add -b <branch> <path> <default>
                Git-->>CLI: New branch and worktree created
            end
        end
    end
```

## Key Workflow Features

### Host vs Container Operations
- **Host commands**: Direct tmux session management on local machine
- **Container commands**: Docker-based isolated environments with tmux sessions

### Session Naming Convention
- **Host**: `repository:branch` (auto-detected from git)
- **Container**: `repository__branch` (sanitized for Docker)

### State Management
- Automatic detection of existing sessions/containers
- Interactive prompts for conflict resolution
- Graceful fallbacks for missing dependencies

### Integration Points
- Git worktree integration for branch-specific workspaces
- Claude Code integration for AI-assisted development
- Anthropic API key management across environments