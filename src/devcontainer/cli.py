#!/usr/bin/env python3
"""
Development Tools CLI

A Python CLI tool that combines git worktree setup and Claude session management.
Converted from bash scripts git-worktree.sh and claude-session.sh.
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional, List, Tuple

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(
    help="Development tools for git worktrees and Claude sessions.\n\n"
         "Commands:\n"
         "  • init-worktree  - Set up git worktree repository structure\n"
         "  • local         - Local tmux session management\n"
         "  • con           - Container session management",
    rich_markup_mode="rich"
)

local_app = typer.Typer(
    help="[bold green]Local Operations[/bold green]\n\n"
         "Manage Claude Code sessions using local tmux.\n"
         "Use 'list' to see numbered sessions, then 'attach' or 'kill' by number.",
    rich_markup_mode="rich"
)

con_app = typer.Typer(
    help="[bold cyan]Container Operations[/bold cyan]\n\n"
         "Manage Claude Code sessions inside Docker containers.\n"
         "Use 'list' to see numbered containers, then 'attach' or 'kill' by number.",
    rich_markup_mode="rich"
)

console = Console()

# Add subcommand groups
app.add_typer(local_app, name="local")
app.add_typer(con_app, name="con")

# Git Worktree Commands
@app.command("init-worktree")
def init_worktree(
    git_url: str = typer.Argument(..., help="Git repository URL"),
    main_branch: Optional[str] = typer.Argument(None, help="Main branch name (auto-detected if not provided)"),
    help_flag: bool = typer.Option(False, "--help", "-h", help="Show help message")
):
    """Set up Git worktree repository structure."""
    
    if help_flag or not git_url:
        console.print("""
[bold]Usage:[/bold]
  dev_tools init-worktree <git-url> [main-branch]

[bold]This will:[/bold]
  - Create a directory based on the repo name
  - Clone the bare repo into .bare/
  - Create a .git pointer
  - Check out the initial branch using worktree

[bold yellow]Worktree usage examples:[/bold yellow]
  cd <project-dir>
  git worktree add -b feature-x feature-x main
  git fetch origin
  git worktree add feature-y origin/feature-y
  git worktree remove feature-x
  git branch -D feature-x
  git push origin --delete feature-x
  git worktree prune
""")
        return

    # Extract project name from Git URL
    proj_name = Path(git_url).stem
    proj_dir = Path.cwd() / proj_name

    if proj_dir.exists():
        console.print(f"[red] Directory '{proj_dir}' already exists. Choose a different location or delete it first.[/red]")
        raise typer.Exit(1)

    # Detect default branch if not provided
    if not main_branch:
        console.print("[blue]Detecting default branch from remote...[/blue]")
        try:
            result = subprocess.run(
                ["git", "ls-remote", "--symref", git_url, "HEAD"],
                capture_output=True, text=True, check=True
            )
            for line in result.stdout.split('\n'):
                if line.startswith('ref: refs/heads/'):
                    main_branch = line.split('refs/heads/')[1]
                    console.print(f"[green]  Default branch is '{main_branch}'")
                    break
        except subprocess.CalledProcessError:
            pass
        
        if not main_branch:
            console.print("[yellow]  Could not detect default branch. Falling back to 'main'.[/yellow]")
            main_branch = "main"

    console.print(f"[blue]Creating project directory:[/blue] {proj_dir}")
    proj_dir.mkdir(parents=True)
    os.chdir(proj_dir)

    console.print("[blue]Cloning bare repo into .bare...[/blue]")
    subprocess.run(["git", "clone", "--bare", git_url, ".bare"], check=True)

    console.print("[blue]Writing .git pointer to .bare...[/blue]")
    with open(".git", "w") as f:
        f.write("gitdir: ./.bare\n")

    console.print(f"[blue]Creating initial '{main_branch}' worktree...[/blue]")
    subprocess.run(["git", "--git-dir=.bare", "worktree", "add", main_branch, main_branch], check=True)

    console.print(f"""
[green]Git worktree repo initialized at:[/green]
  {proj_dir}

[bold]Layout:[/bold]
  .bare/       → bare repo
  .git         → points to .bare
  {main_branch}/ → initial working branch

[bold yellow]Worktree usage examples:[/bold yellow]
  cd {proj_dir}
  git worktree add -b feature-x feature-x {main_branch}         # create and checkout new local branch
  git fetch origin
  git worktree add feature-y origin/feature-y                 # check out existing remote branch
  git worktree remove feature-x                               # remove folder and detach worktree
  git branch -D feature-x                                     # delete local branch
  git push origin --delete feature-x                          # delete remote branch
  git worktree prune                                          # clean up metadata
""")


# Claude Session Commands
@con_app.command("session")
def container_session(
    repo_path: str = typer.Argument(..., help="Absolute path to the repository"),
    branch_name: str = typer.Argument(..., help="Branch name to work on"),
    auto_attach: bool = typer.Option(False, "--auto-attach", help="Auto-attach after creating session")
):
    """Create a new container session for a repository branch."""
    
    # Validate repo path
    repo_path_obj = Path(repo_path)
    if not repo_path_obj.is_absolute():
        console.print(f"[red] Path must be absolute: {repo_path}[/red]")
        raise typer.Exit(1)
    
    if not repo_path_obj.exists():
        console.print(f"[red] Repository path does not exist: {repo_path}[/red]")
        raise typer.Exit(1)
    
    if not (repo_path_obj / ".git").exists() and not (repo_path_obj / ".bare").exists():
        console.print(f"[red] Path is not a git repository: {repo_path}[/red]")
        raise typer.Exit(1)
    
    # Extract repository name
    repo_name = repo_path_obj.name
    session_name = f"{repo_name}__{branch_name}"
    
    # Sanitize session name for tmux and docker
    sanitized_session = re.sub(r'[^a-zA-Z0-9._-]', '_', session_name)
    container_name = f"devcontainer_{sanitized_session}"
    
    console.print(f"Container session: {session_name}")
    console.print(f"Repository: {repo_path}")
    console.print(f"Branch: {branch_name}")
    
    # Check if container is already running
    container_exists = _container_exists(container_name)
    session_exists_in_container = False
    
    if container_exists:
        # Check if the specific tmux session exists in the container
        session_exists_in_container = _container_session_exists(container_name, sanitized_session)
        
        if session_exists_in_container:
            console.print(f"[yellow]Session '{sanitized_session}' already exists in container![/yellow]")
            choice = typer.prompt("Do you want to [a]ttach, [r]ecreate session, or [c]ancel? (a/r/c)", default="a")
            
            if choice.lower() in ['a', '']:
                console.print("[blue]  Attaching to existing session...[/blue]")
                _attach_container_session(container_name, sanitized_session)
                return
            elif choice.lower() == 'r':
                console.print("[blue]  Recreating tmux session...[/blue]")
                _kill_container_session(container_name, sanitized_session)
            elif choice.lower() == 'c':
                console.print("[red]  Cancelled[/red]")
                return
            else:
                console.print("[red]  Invalid choice. Cancelled.[/red]")
                raise typer.Exit(1)
        else:
            console.print(f"[blue]Container '{container_name}' exists, creating new session...[/blue]")
    
    # Ensure git worktree exists for the branch
    worktree_path = repo_path_obj / branch_name
    if not worktree_path.exists():
        console.print(f"[blue]Creating git worktree for branch '{branch_name}'...[/blue]")
        _create_git_worktree(repo_path_obj, branch_name)
    else:
        console.print(f"[green]Using existing worktree:[/green] {worktree_path}")
    
    # Start container if it doesn't exist
    if not container_exists:
        console.print(f"[blue]Starting container:[/blue] {container_name}")
        _start_container(container_name, repo_path, branch_name)
    
    # Create tmux session inside container
    console.print(f"[blue]Creating tmux session '{sanitized_session}' inside container...[/blue]")
    _create_container_tmux_session(container_name, sanitized_session, branch_name)
    
    console.print("[green]Container session created successfully![/green]")
    console.print(f"[dim]  Connect with:[/dim] docker exec -it {container_name} tmux attach -t '{sanitized_session}'")
    
    # Auto-attach if requested
    if auto_attach:
        console.print("[blue]Auto-attaching to container session...[/blue]")
        import time
        time.sleep(2)
        _attach_container_session(container_name, sanitized_session)


@local_app.command("session")
def claude_session(
    session_name: Optional[str] = typer.Argument(None, help="Custom session name"),
    attach: Optional[int] = typer.Option(None, "--attach", "-a", help="Attach to session number or auto-attach if no number"),
    list_sessions: bool = typer.Option(False, "--list", "-l", help="List all active tmux sessions"),
    kill: Optional[int] = typer.Option(None, "--kill", "-k", help="Kill session by number"),
    auto_attach: bool = typer.Option(False, "--auto-attach", help="Auto-attach after creating session")
):
    """Create and manage Claude Code tmux sessions."""
    
    # Handle list sessions
    if list_sessions:
        _list_tmux_sessions()
        return

    # Handle kill by number
    if kill is not None:
        _kill_session_by_number(kill)
        return

    # Handle attach by number
    if attach is not None:
        _attach_session_by_number(attach)
        return

    # Determine session name
    if session_name:
        console.print(f" Using custom session name: {session_name}")
    else:
        session_name = _detect_session_name()

    # Sanitize session name for tmux
    original_name = session_name
    session_name = re.sub(r'[^a-zA-Z0-9._-]', '_', session_name.replace(':', '_'))
    
    if session_name != original_name:
        console.print(f" Sanitized session name: {original_name} → {session_name}")

    # Check if session already exists
    if _tmux_session_exists(session_name):
        console.print(f"[yellow]Session '{session_name}' already exists![/yellow]")
        choice = typer.prompt("Do you want to [a]ttach, [k]ill and recreate, or [c]ancel? (a/k/c)", default="a")
        
        if choice.lower() in ['a', '']:
            console.print("[blue]  Attaching to existing session...[/blue]")
            _attach_tmux_session(session_name)
            return
        elif choice.lower() == 'k':
            console.print("[blue]  Killing existing session...[/blue]")
            _kill_tmux_session(session_name)
        elif choice.lower() == 'c':
            console.print("[red]  Cancelled[/red]")
            return
        else:
            console.print("[red]  Invalid choice. Cancelled.[/red]")
            raise typer.Exit(1)

    # Create tmux session
    console.print(f" Creating tmux session: {session_name}")
    console.print(f" Directory: {os.getcwd()}")

    try:
        subprocess.run([
            "tmux", "new-session", "-d", "-s", session_name, "-c", os.getcwd()
        ], check=True)
        
        # Give tmux a moment to create the session
        import time
        time.sleep(0.5)
        
        if not _tmux_session_exists(session_name):
            console.print(f"[red] Failed to create tmux session '{session_name}'[/red]")
            raise typer.Exit(1)

        # Configure the session
        subprocess.run(["tmux", "send-keys", "-t", session_name, "clear", "C-m"], check=True)
        subprocess.run(["tmux", "send-keys", "-t", session_name, 
                       f"echo ' Starting Claude Code session for: {session_name}'", "C-m"], check=True)
        subprocess.run(["tmux", "send-keys", "-t", session_name, 
                       f"echo 'Directory: {os.getcwd()}'", "C-m"], check=True)

        # Check if claude command exists
        if not _command_exists("claude"):
            console.print("[yellow]  Warning: 'claude' command not found[/yellow]")
            console.print("   Make sure Claude Code is installed and in your PATH")
            subprocess.run(["tmux", "send-keys", "-t", session_name,
                           "echo 'Warning: claude command not found. Please install Claude Code.'", "C-m"])
        else:
            console.print(" Starting Claude Code...")
            subprocess.run(["tmux", "send-keys", "-t", session_name, "claude", "C-m"], check=True)

        # Set window name
        subprocess.run(["tmux", "rename-window", "-t", f"{session_name}:0", "claude"], check=True)

        console.print("[green] Session created successfully![/green]")
        console.print(f" Connect with: tmux attach -t '{session_name}'")

        # Auto-attach if requested
        if auto_attach or attach == 0:  # attach with no number means auto-attach
            console.print(" Auto-attaching to session...")
            time.sleep(1)
            _attach_tmux_session(session_name)

    except subprocess.CalledProcessError as e:
        console.print(f"[red] Failed to create tmux session: {e}[/red]")
        raise typer.Exit(1)


@local_app.command("list")
def list_sessions():
    """List all active tmux sessions with numbers."""
    _list_tmux_sessions()


@local_app.command("kill")
def kill_session(number: int = typer.Argument(..., help="Session number to kill")):
    """Kill a local tmux session by number."""
    _kill_session_by_number(number)


@local_app.command("attach")
def attach_session(number: int = typer.Argument(..., help="Session number to attach to")):
    """Attach to a local tmux session by number."""
    _attach_session_by_number(number)


@local_app.command("kill-all")
def kill_all_sessions():
    """Kill all local Claude sessions."""
    try:
        result = subprocess.run(
            ["tmux", "list-sessions", "-F", "#{session_name}"],
            capture_output=True, text=True, check=True
        )
        all_sessions = result.stdout.strip().split('\n') if result.stdout.strip() else []
    except subprocess.CalledProcessError:
        console.print("  No active sessions found")
        return

    # Filter for likely Claude sessions
    claude_sessions = [s for s in all_sessions if re.search(r'(claude|_|-)', s) and s != "crashes"]

    if claude_sessions:
        console.print(" Found likely Claude sessions:")
        for session in claude_sessions:
            console.print(f"   {session}")
        console.print()
        
        if typer.confirm("Kill these sessions?", default=False):
            for session in claude_sessions:
                subprocess.run(["tmux", "kill-session", "-t", session])
            console.print("[green] Sessions terminated[/green]")
        else:
            console.print("[red]  Cancelled[/red]")
    else:
        console.print("  No Claude sessions to kill")


@con_app.command("attach")
def container_attach(
    target: str = typer.Argument(..., help="Container number (from 'list') or session name (repo__branch)")
):
    """Attach to an existing container session.
    
    Examples:
      wgx con list              # Show numbered containers
      wgx con attach 1          # Attach to container #1
      wgx con attach repo__main # Attach to specific session
    """
    
    # Check if target is a number
    if target.isdigit():
        number = int(target)
        containers = _get_container_sessions()
        if not containers:
            console.print("[red]No active container sessions found[/red]")
            raise typer.Exit(1)
        
        if number < 1 or number > len(containers):
            console.print(f"[red]Invalid container number: {number}[/red]")
            console.print(f"Available containers (1-{len(containers)}):")
            _list_container_sessions()
            raise typer.Exit(1)
        
        container_name = containers[number - 1]
        console.print(f"[blue]Attaching to container #{number}: {container_name}[/blue]")
        
        # Get the session name from container name
        # Container name format: devcontainer_repo__branch
        if container_name.startswith("devcontainer_"):
            sanitized_session = container_name[13:]  # Remove "devcontainer_" prefix
        else:
            sanitized_session = container_name
    else:
        # Treat as session name
        session_name = target
        sanitized_session = re.sub(r'[^a-zA-Z0-9._-]', '_', session_name)
        container_name = f"devcontainer_{sanitized_session}"
        
        console.print(f"[blue]Attempting to attach to container session: {session_name}[/blue]")
        
        # Check if container exists and is running
        if not _container_exists(container_name):
            console.print(f"[red]Container '{container_name}' is not running[/red]")
            console.print("Available containers:")
            _list_container_sessions()
            raise typer.Exit(1)
    
    # Check if tmux session exists in container
    try:
        result = subprocess.run([
            "docker", "exec", container_name,
            "tmux", "has-session", "-t", sanitized_session
        ], capture_output=True)
        
        if result.returncode != 0:
            console.print(f"[red]Tmux session '{sanitized_session}' not found in container[/red]")
            console.print("Available tmux sessions in container:")
            _list_container_tmux_sessions(container_name)
            raise typer.Exit(1)
    except subprocess.CalledProcessError:
        console.print(f"[red]Cannot check tmux sessions in container '{container_name}'[/red]")
        raise typer.Exit(1)
    
    # Attach to the session
    _attach_container_session(container_name, sanitized_session)


@con_app.command("list")
def list_container_sessions():
    """List all running container sessions with numbers."""
    _list_container_sessions()


@con_app.command("kill")
def kill_container_session(
    target: str = typer.Argument(..., help="Container number (from 'list') or session name (repo__branch)")
):
    """Kill a container session (tmux session only, not the container).
    
    Examples:
      wgx con list               # Show numbered containers
      wgx con kill 1             # Kill session in container #1
      wgx con kill repo__main    # Kill session by name
    
    Note: This only kills the tmux session. If it's the last session in the container,
    you'll be prompted whether to kill the container too.
    """
    
    container_name = None
    sanitized_session = None
    
    # Check if target is a number
    if target.isdigit():
        number = int(target)
        containers = _get_container_sessions()
        if not containers:
            console.print("[red]No active container sessions found[/red]")
            raise typer.Exit(1)
        
        if number < 1 or number > len(containers):
            console.print(f"[red]Invalid container number: {number}[/red]")
            console.print(f"Available containers (1-{len(containers)}):")
            _list_container_sessions()
            raise typer.Exit(1)
        
        container_name = containers[number - 1]
        
        # Get the session name from container name
        # Container name format: devcontainer_repo__branch
        if container_name.startswith("devcontainer_"):
            sanitized_session = container_name[13:]  # Remove "devcontainer_" prefix
        else:
            sanitized_session = container_name
            
        console.print(f"[yellow]Killing session in container #{number}: {container_name}[/yellow]")
    else:
        # Treat as session name
        session_name = target
        sanitized_session = re.sub(r'[^a-zA-Z0-9._-]', '_', session_name)
        container_name = f"devcontainer_{sanitized_session}"
        
        if not _container_exists(container_name):
            console.print(f"[red]Container '{container_name}' is not running[/red]")
            console.print("Available containers:")
            _list_container_sessions()
            raise typer.Exit(1)
            
        console.print(f"[yellow]Killing session '{sanitized_session}' in container[/yellow]")
    
    if not _container_session_exists(container_name, sanitized_session):
        console.print(f"[red]Session '{sanitized_session}' not found in container[/red]")
        raise typer.Exit(1)
    
    # Kill the tmux session
    _kill_container_session(container_name, sanitized_session)
    
    # Check if this was the last session in the container
    remaining_sessions = _get_container_tmux_sessions(container_name)
    if not remaining_sessions:
        console.print(f"[yellow]This was the last session in container '{container_name}'[/yellow]")
        if typer.confirm("Do you want to kill the container too?", default=False):
            try:
                subprocess.run(["docker", "stop", container_name], capture_output=True, check=True)
                subprocess.run(["docker", "rm", container_name], capture_output=True, check=True)
                console.print("[green]Container terminated[/green]")
            except subprocess.CalledProcessError:
                console.print("[red]Failed to kill container[/red]")
        else:
            console.print("[blue]Container left running (empty)[/blue]")


@con_app.command("kill-all")
def kill_all_container_sessions(
    target: Optional[str] = typer.Argument(None, help="Optional container number or name to kill only that container")
):
    """Kill all container sessions, or a specific container if target is provided.
    
    Examples:
      wgx con kill-all           # Kill all containers
      wgx con kill-all 1         # Kill container #1
      wgx con kill-all repo__main # Kill container by session name
    """
    
    try:
        result = subprocess.run([
            "docker", "ps", "--filter", "name=devcontainer_", "--format", "{{.Names}}"
        ], capture_output=True, text=True, check=True)
        
        all_containers = result.stdout.strip().split('\n') if result.stdout.strip() else []
        if not all_containers:
            console.print("[dim]  No container sessions found[/dim]")
            return
        
        containers_to_kill = []
        
        if target:
            # Kill specific container
            if target.isdigit():
                number = int(target)
                if number < 1 or number > len(all_containers):
                    console.print(f"[red]Invalid container number: {number}[/red]")
                    console.print(f"Available containers (1-{len(all_containers)}):")
                    _list_container_sessions()
                    raise typer.Exit(1)
                
                containers_to_kill = [all_containers[number - 1]]
                console.print(f"[yellow]Killing container #{number}: {containers_to_kill[0]}[/yellow]")
            else:
                # Treat as session name
                session_name = target
                sanitized_session = re.sub(r'[^a-zA-Z0-9._-]', '_', session_name)
                container_name = f"devcontainer_{sanitized_session}"
                
                if container_name in all_containers:
                    containers_to_kill = [container_name]
                    console.print(f"[yellow]Killing container: {container_name}[/yellow]")
                else:
                    console.print(f"[red]Container '{container_name}' not found[/red]")
                    console.print("Available containers:")
                    _list_container_sessions()
                    raise typer.Exit(1)
        else:
            # Kill all containers
            containers_to_kill = all_containers
            console.print("[yellow]Found container sessions:[/yellow]")
            for i, container in enumerate(containers_to_kill, 1):
                console.print(f"   {i}. {container}")
        
        if not containers_to_kill:
            return
            
        # Confirm before killing
        if len(containers_to_kill) == 1:
            if not typer.confirm(f"Kill container '{containers_to_kill[0]}'?", default=False):
                console.print("[red]  Cancelled[/red]")
                return
        else:
            if not typer.confirm("Kill all container sessions?", default=False):
                console.print("[red]  Cancelled[/red]")
                return
        
        # Kill the containers
        for container in containers_to_kill:
            try:
                subprocess.run(["docker", "stop", container], capture_output=True, check=True)
                subprocess.run(["docker", "rm", container], capture_output=True, check=True)
                console.print(f"[green]Container '{container}' terminated[/green]")
            except subprocess.CalledProcessError:
                console.print(f"[red]Failed to kill container '{container}'[/red]")
                
    except subprocess.CalledProcessError:
        console.print("[dim]  No container sessions found[/dim]")


# Helper functions
def _list_tmux_sessions():
    """List all tmux sessions with numbers."""
    try:
        result = subprocess.run(
            ["tmux", "list-sessions", "-F", "#{session_name}"],
            capture_output=True, text=True, check=True
        )
        sessions = sorted(result.stdout.strip().split('\n')) if result.stdout.strip() else []
    except subprocess.CalledProcessError:
        console.print(" Active tmux sessions:")
        console.print("   No active sessions found")
        return

    if not sessions:
        console.print(" Active tmux sessions:")
        console.print("   No active sessions found")
        return

    table = Table(title=" Active tmux sessions")
    table.add_column("No.", style="cyan", no_wrap=True)
    table.add_column("Session Info", style="white")

    for i, session in enumerate(sessions, 1):
        try:
            session_info_result = subprocess.run(
                ["tmux", "list-sessions"],
                capture_output=True, text=True, check=True
            )
            session_info = next(
                (line for line in session_info_result.stdout.split('\n') if line.startswith(f"{session}:")),
                f"{session}: (info unavailable)"
            )
            table.add_row(str(i), session_info)
        except subprocess.CalledProcessError:
            table.add_row(str(i), f"{session}: (info unavailable)")

    console.print(table)


def _kill_session_by_number(number: int):
    """Kill a tmux session by its number in the list."""
    sessions = _get_tmux_sessions()
    if not sessions:
        console.print("[red] No active sessions found[/red]")
        raise typer.Exit(1)

    if number < 1 or number > len(sessions):
        console.print(f"[red] Invalid session number: {number}[/red]")
        console.print(f" Available sessions (1-{len(sessions)}):")
        _list_tmux_sessions()
        raise typer.Exit(1)

    target_session = sessions[number - 1]
    console.print(f" Killing session #{number}: {target_session}")
    
    try:
        subprocess.run(["tmux", "kill-session", "-t", target_session], check=True)
        console.print("[green] Session killed successfully[/green]")
    except subprocess.CalledProcessError:
        console.print("[red] Failed to kill session[/red]")
        raise typer.Exit(1)


def _attach_session_by_number(number: int):
    """Attach to a tmux session by its number in the list."""
    sessions = _get_tmux_sessions()
    if not sessions:
        console.print("[red] No active sessions found[/red]")
        raise typer.Exit(1)

    if number < 1 or number > len(sessions):
        console.print(f"[red] Invalid session number: {number}[/red]")
        console.print(f" Available sessions (1-{len(sessions)}):")
        _list_tmux_sessions()
        raise typer.Exit(1)

    target_session = sessions[number - 1]
    console.print(f" Attaching to session #{number}: {target_session}")
    _attach_tmux_session(target_session)


def _get_tmux_sessions() -> List[str]:
    """Get list of tmux session names."""
    try:
        result = subprocess.run(
            ["tmux", "list-sessions", "-F", "#{session_name}"],
            capture_output=True, text=True, check=True
        )
        return sorted(result.stdout.strip().split('\n')) if result.stdout.strip() else []
    except subprocess.CalledProcessError:
        return []


def _detect_session_name() -> str:
    """Detect appropriate session name based on current directory and git status."""
    try:
        # Check if we're in a git worktree
        subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], 
                      capture_output=True, check=True)
        
        # Get repository name
        repo_name = ""
        try:
            result = subprocess.run(["git", "remote", "get-url", "origin"],
                                  capture_output=True, text=True, check=True)
            remote_url = result.stdout.strip()
            repo_name = Path(remote_url).stem
        except subprocess.CalledProcessError:
            # Fallback to git root directory name
            result = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                                  capture_output=True, text=True, check=True)
            repo_name = Path(result.stdout.strip()).name

        # Get current branch name
        try:
            result = subprocess.run(["git", "branch", "--show-current"],
                                  capture_output=True, text=True, check=True)
            branch_name = result.stdout.strip()
        except subprocess.CalledProcessError:
            # Fallback for detached HEAD
            try:
                result = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                                      capture_output=True, text=True, check=True)
                branch_name = result.stdout.strip()
            except subprocess.CalledProcessError:
                branch_name = "detached"

        session_name = f"{repo_name}:{branch_name}"
        console.print(f"[green]Git worktree detected:[/green] {session_name}")
        return session_name

    except subprocess.CalledProcessError:
        # Use current directory name
        session_name = Path.cwd().name
        console.print(f" Using directory name: {session_name}")
        return session_name


def _tmux_session_exists(session_name: str) -> bool:
    """Check if tmux session exists."""
    try:
        subprocess.run(["tmux", "has-session", "-t", session_name],
                      capture_output=True, check=True)
        return True
    except subprocess.CalledProcessError:
        return False


def _attach_tmux_session(session_name: str):
    """Attach to a tmux session."""
    subprocess.run(["tmux", "attach-session", "-t", session_name])


def _kill_tmux_session(session_name: str):
    """Kill a tmux session."""
    subprocess.run(["tmux", "kill-session", "-t", session_name])


def _command_exists(command: str) -> bool:
    """Check if a command exists in PATH."""
    try:
        subprocess.run(["which", command], capture_output=True, check=True)
        return True
    except subprocess.CalledProcessError:
        return False


# Container management helper functions
def _container_exists(container_name: str) -> bool:
    """Check if a Docker container exists and is running."""
    try:
        result = subprocess.run([
            "docker", "ps", "-q", "-f", f"name={container_name}"
        ], capture_output=True, text=True, check=True)
        return bool(result.stdout.strip())
    except subprocess.CalledProcessError:
        return False



def _start_container(container_name: str, repo_path: str, branch_name: str):
    """Start a Docker container using docker-compose."""
    try:
        # Create a temporary docker-compose override for this specific container
        branch_path = Path(repo_path) / branch_name
        
        # Get Anthropic API key from environment or prompt user
        anthropic_key = _get_anthropic_key()
        
        # Build docker run command with environment variables
        docker_cmd = [
            "docker", "run", "-d", "--name", container_name,
            "-v", f"{branch_path}:/workspace",
            "-w", "/workspace"
        ]
        
        # Add Anthropic API key as environment variable if available
        if anthropic_key:
            docker_cmd.extend(["-e", f"ANTHROPIC_API_KEY={anthropic_key}"])
            console.print(" Anthropic API key configured in container")
        else:
            console.print("[yellow]  No Anthropic API key found - Claude Code may not work in container[/yellow]")
        
        # Add image and command
        docker_cmd.extend(["devcontainer:latest", "sleep", "infinity"])
        
        subprocess.run(docker_cmd, check=True)
        
        console.print(f" Container '{container_name}' started successfully")
        
        # Install tmux in the container if not already available
        subprocess.run([
            "docker", "exec", container_name,
            "sh", "-c", "which tmux || (apt-get update && apt-get install -y tmux)"
        ], capture_output=True)
        
    except subprocess.CalledProcessError as e:
        console.print(f"[red] Failed to start container: {e}[/red]")
        raise typer.Exit(1)


def _create_container_tmux_session(container_name: str, session_name: str, branch_name: str):
    """Create a tmux session inside the container."""
    try:
        # Check if tmux session already exists in container
        result = subprocess.run([
            "docker", "exec", container_name,
            "tmux", "has-session", "-t", session_name
        ], capture_output=True)
        
        if result.returncode == 0:
            console.print(f"[yellow]  Tmux session '{session_name}' already exists in container[/yellow]")
            return
        
        # Create new tmux session
        subprocess.run([
            "docker", "exec", "-d", container_name,
            "tmux", "new-session", "-d", "-s", session_name, "-c", "/workspace"
        ], check=True)
        
        # Configure the session
        subprocess.run([
            "docker", "exec", container_name,
            "tmux", "send-keys", "-t", session_name, "clear", "C-m"
        ], check=True)
        
        subprocess.run([
            "docker", "exec", container_name,
            "tmux", "send-keys", "-t", session_name,
            f"echo ' Container Claude Code session: {session_name}'", "C-m"
        ], check=True)
        
        subprocess.run([
            "docker", "exec", container_name,
            "tmux", "send-keys", "-t", session_name,
            f"echo ' Branch: {branch_name}'", "C-m"
        ], check=True)
        
        # Check if claude command exists in container
        result = subprocess.run([
            "docker", "exec", container_name,
            "which", "claude"
        ], capture_output=True)
        
        if result.returncode == 0:
            console.print(" Starting Claude Code in container...")
            subprocess.run([
                "docker", "exec", container_name,
                "tmux", "send-keys", "-t", session_name, "claude", "C-m"
            ], check=True)
        else:
            subprocess.run([
                "docker", "exec", container_name,
                "tmux", "send-keys", "-t", session_name,
                "echo 'Claude Code not available in container. Install it or use: docker exec -it CONTAINER bash'", "C-m"
            ], check=True)
        
        # Set window name
        subprocess.run([
            "docker", "exec", container_name,
            "tmux", "rename-window", "-t", f"{session_name}:0", "claude"
        ], check=True)
        
    except subprocess.CalledProcessError as e:
        console.print(f"[red] Failed to create tmux session in container: {e}[/red]")
        raise typer.Exit(1)


def _attach_container_session(container_name: str, session_name: str):
    """Attach to a tmux session inside a container."""
    try:
        subprocess.run([
            "docker", "exec", "-it", container_name,
            "tmux", "attach-session", "-t", session_name
        ])
    except subprocess.CalledProcessError as e:
        console.print(f"[red] Failed to attach to container session: {e}[/red]")
        raise typer.Exit(1)


def _container_session_exists(container_name: str, session_name: str) -> bool:
    """Check if a specific tmux session exists inside a container."""
    try:
        result = subprocess.run([
            "docker", "exec", container_name,
            "tmux", "has-session", "-t", session_name
        ], capture_output=True)
        return result.returncode == 0
    except subprocess.CalledProcessError:
        return False


def _kill_container_session(container_name: str, session_name: str):
    """Kill a specific tmux session inside a container."""
    try:
        subprocess.run([
            "docker", "exec", container_name,
            "tmux", "kill-session", "-t", session_name
        ], check=True)
        console.print(f"[blue]  Session '{session_name}' killed in container[/blue]")
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Failed to kill session in container: {e}[/red]")
        raise typer.Exit(1)


def _create_git_worktree(repo_path: Path, branch_name: str):
    """Create a git worktree for the specified branch."""
    try:
        worktree_path = repo_path / branch_name
        
        # Change to repo directory for git operations
        original_cwd = os.getcwd()
        os.chdir(repo_path)
        
        try:
            # First try to create worktree from existing remote branch
            subprocess.run([
                "git", "worktree", "add", str(worktree_path), f"origin/{branch_name}"
            ], check=True, capture_output=True)
            console.print(f" Created worktree from remote branch 'origin/{branch_name}'")
        except subprocess.CalledProcessError:
            try:
                # If that fails, try to create worktree from local branch
                subprocess.run([
                    "git", "worktree", "add", str(worktree_path), branch_name
                ], check=True, capture_output=True)
                console.print(f" Created worktree from local branch '{branch_name}'")
            except subprocess.CalledProcessError:
                # If that also fails, create new branch and worktree
                try:
                    # Determine the main/default branch
                    result = subprocess.run([
                        "git", "symbolic-ref", "refs/remotes/origin/HEAD"
                    ], capture_output=True, text=True, check=True)
                    default_branch = result.stdout.strip().split('/')[-1]
                except subprocess.CalledProcessError:
                    default_branch = "main"
                
                subprocess.run([
                    "git", "worktree", "add", "-b", branch_name, str(worktree_path), default_branch
                ], check=True)
                console.print(f" Created new branch '{branch_name}' and worktree from '{default_branch}'")
        
        finally:
            os.chdir(original_cwd)
            
    except subprocess.CalledProcessError as e:
        console.print(f"[red] Failed to create git worktree: {e}[/red]")
        raise typer.Exit(1)


def _get_anthropic_key() -> Optional[str]:
    """Get Anthropic API key from environment variables or common config locations."""
    
    # Check environment variable first
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if api_key:
        console.print(" Found Anthropic API key in environment variable")
        return api_key
    
    # Check Claude Code config locations
    claude_config_paths = [
        Path.home() / ".config" / "claude" / "config.json",
        Path.home() / ".claude" / "config.json",
        Path.home() / "Library" / "Application Support" / "Claude" / "config.json",  # macOS
    ]
    
    for config_path in claude_config_paths:
        if config_path.exists():
            try:
                with open(config_path, 'r') as f:
                    config = json.load(f)
                    if "api_key" in config:
                        console.print(f" Found Anthropic API key in {config_path}")
                        return config["api_key"]
                    elif "anthropic_api_key" in config:
                        console.print(f" Found Anthropic API key in {config_path}")
                        return config["anthropic_api_key"]
            except (json.JSONDecodeError, KeyError, IOError):
                continue
    
    # Check common shell config files for exported variables
    shell_configs = [
        Path.home() / ".bashrc",
        Path.home() / ".zshrc", 
        Path.home() / ".bash_profile",
        Path.home() / ".profile"
    ]
    
    for shell_config in shell_configs:
        if shell_config.exists():
            try:
                with open(shell_config, 'r') as f:
                    content = f.read()
                    # Look for export ANTHROPIC_API_KEY=
                    match = re.search(r'export\s+ANTHROPIC_API_KEY\s*=\s*["\']?([^"\'\s]+)["\']?', content)
                    if match:
                        console.print(f" Found Anthropic API key in {shell_config}")
                        return match.group(1)
            except IOError:
                continue
    
    # Prompt user to enter API key
    console.print("[yellow]  Anthropic API key not found in environment or config files[/yellow]")
    console.print("Claude Code requires an API key to work properly in the container.")
    
    if typer.confirm("Would you like to enter your Anthropic API key now?", default=False):
        api_key = typer.prompt("Enter your Anthropic API key", hide_input=True)
        if api_key.strip():
            return api_key.strip()
    
    return None


def _list_container_sessions():
    """List all running devcontainer sessions with numbers."""
    try:
        result = subprocess.run([
            "docker", "ps", "--filter", "name=devcontainer_", "--format", "{{.Names}}\t{{.Status}}\t{{.CreatedAt}}"
        ], capture_output=True, text=True, check=True)
        
        lines = result.stdout.strip().split('\n') if result.stdout.strip() else []
        if not lines:
            console.print("Active container sessions:")
            console.print("   No active container sessions found")
            return
        
        table = Table(title="Active container sessions")
        table.add_column("No.", style="cyan", no_wrap=True)
        table.add_column("Container Name", style="white")
        table.add_column("Status", style="green")
        table.add_column("Created", style="dim")
        
        for i, line in enumerate(lines, 1):
            parts = line.split('\t')
            if len(parts) >= 3:
                name = parts[0]
                status = parts[1]
                created = parts[2]
                table.add_row(str(i), name, status, created)
        
        console.print(table)
            
    except subprocess.CalledProcessError:
        console.print("Active container sessions:")
        console.print("   Unable to list containers (Docker not available?)")


def _get_container_sessions() -> List[str]:
    """Get list of container names."""
    try:
        result = subprocess.run([
            "docker", "ps", "--filter", "name=devcontainer_", "--format", "{{.Names}}"
        ], capture_output=True, text=True, check=True)
        return result.stdout.strip().split('\n') if result.stdout.strip() else []
    except subprocess.CalledProcessError:
        return []


def _list_container_tmux_sessions(container_name: str):
    """List tmux sessions inside a specific container."""
    try:
        result = subprocess.run([
            "docker", "exec", container_name,
            "tmux", "list-sessions", "-F", "#{session_name}"
        ], capture_output=True, text=True, check=True)
        
        sessions = result.stdout.strip().split('\n') if result.stdout.strip() else []
        if sessions:
            console.print("   Available tmux sessions:")
            for session in sessions:
                console.print(f"     - {session}")
        else:
            console.print("   No tmux sessions found in container")
            
    except subprocess.CalledProcessError:
        console.print("   Unable to list tmux sessions in container")


def _get_container_tmux_sessions(container_name: str) -> List[str]:
    """Get list of tmux session names inside a specific container."""
    try:
        result = subprocess.run([
            "docker", "exec", container_name,
            "tmux", "list-sessions", "-F", "#{session_name}"
        ], capture_output=True, text=True, check=True)
        
        return result.stdout.strip().split('\n') if result.stdout.strip() else []
    except subprocess.CalledProcessError:
        return []


def main():
    app()


if __name__ == "__main__":
    main()