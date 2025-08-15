#!/usr/bin/env python3
"""
Development Tools CLI

A Python CLI tool that combines git worktree setup and Claude session management.
Converted from bash scripts git-worktree.sh and claude-session.sh.
"""

import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional, List, Tuple

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(help="Development tools for git worktrees and Claude sessions")
console = Console()

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

[bold yellow]💡 Worktree usage examples:[/bold yellow]
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
        console.print(f"[red]❌ Directory '{proj_dir}' already exists. Choose a different location or delete it first.[/red]")
        raise typer.Exit(1)

    # Detect default branch if not provided
    if not main_branch:
        console.print("🔍 Detecting default branch from remote...")
        try:
            result = subprocess.run(
                ["git", "ls-remote", "--symref", git_url, "HEAD"],
                capture_output=True, text=True, check=True
            )
            for line in result.stdout.split('\n'):
                if line.startswith('ref: refs/heads/'):
                    main_branch = line.split('refs/heads/')[1]
                    console.print(f"📌 Default branch is '{main_branch}'")
                    break
        except subprocess.CalledProcessError:
            pass
        
        if not main_branch:
            console.print("⚠️  Could not detect default branch. Falling back to 'main'.")
            main_branch = "main"

    console.print(f"📁 Creating project directory: {proj_dir}")
    proj_dir.mkdir(parents=True)
    os.chdir(proj_dir)

    console.print("📦 Cloning bare repo into .bare...")
    subprocess.run(["git", "clone", "--bare", git_url, ".bare"], check=True)

    console.print("🔗 Writing .git pointer to .bare...")
    with open(".git", "w") as f:
        f.write("gitdir: ./.bare\n")

    console.print(f"🌱 Creating initial '{main_branch}' worktree...")
    subprocess.run(["git", "--git-dir=.bare", "worktree", "add", main_branch, main_branch], check=True)

    console.print(f"""
[green]✅ Git worktree repo initialized at:[/green]
  {proj_dir}

[bold]📂 Layout:[/bold]
  .bare/       → bare repo
  .git         → points to .bare
  {main_branch}/ → initial working branch

[bold yellow]💡 Worktree usage examples:[/bold yellow]
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
@app.command("session")
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
        console.print(f"🎯 Using custom session name: {session_name}")
    else:
        session_name = _detect_session_name()

    # Sanitize session name for tmux
    original_name = session_name
    session_name = re.sub(r'[^a-zA-Z0-9._-]', '_', session_name.replace(':', '_'))
    
    if session_name != original_name:
        console.print(f"🔧 Sanitized session name: {original_name} → {session_name}")

    # Check if session already exists
    if _tmux_session_exists(session_name):
        console.print(f"⚡ Session '{session_name}' already exists!")
        choice = typer.prompt("Do you want to [a]ttach, [k]ill and recreate, or [c]ancel? (a/k/c)", default="a")
        
        if choice.lower() in ['a', '']:
            console.print("🔗 Attaching to existing session...")
            _attach_tmux_session(session_name)
            return
        elif choice.lower() == 'k':
            console.print("💀 Killing existing session...")
            _kill_tmux_session(session_name)
        elif choice.lower() == 'c':
            console.print("❌ Cancelled")
            return
        else:
            console.print("❌ Invalid choice. Cancelled.")
            raise typer.Exit(1)

    # Create tmux session
    console.print(f"🚀 Creating tmux session: {session_name}")
    console.print(f"📍 Directory: {os.getcwd()}")

    try:
        subprocess.run([
            "tmux", "new-session", "-d", "-s", session_name, "-c", os.getcwd()
        ], check=True)
        
        # Give tmux a moment to create the session
        import time
        time.sleep(0.5)
        
        if not _tmux_session_exists(session_name):
            console.print(f"[red]❌ Failed to create tmux session '{session_name}'[/red]")
            raise typer.Exit(1)

        # Configure the session
        subprocess.run(["tmux", "send-keys", "-t", session_name, "clear", "C-m"], check=True)
        subprocess.run(["tmux", "send-keys", "-t", session_name, 
                       f"echo '🤖 Starting Claude Code session for: {session_name}'", "C-m"], check=True)
        subprocess.run(["tmux", "send-keys", "-t", session_name, 
                       f"echo '📁 Directory: {os.getcwd()}'", "C-m"], check=True)

        # Check if claude command exists
        if not _command_exists("claude"):
            console.print("[yellow]⚠️  Warning: 'claude' command not found[/yellow]")
            console.print("   Make sure Claude Code is installed and in your PATH")
            subprocess.run(["tmux", "send-keys", "-t", session_name,
                           "echo 'Warning: claude command not found. Please install Claude Code.'", "C-m"])
        else:
            console.print("🤖 Starting Claude Code...")
            subprocess.run(["tmux", "send-keys", "-t", session_name, "claude", "C-m"], check=True)

        # Set window name
        subprocess.run(["tmux", "rename-window", "-t", f"{session_name}:0", "claude"], check=True)

        console.print("[green]✅ Session created successfully![/green]")
        console.print(f"🔗 Connect with: tmux attach -t '{session_name}'")

        # Auto-attach if requested
        if auto_attach or attach == 0:  # attach with no number means auto-attach
            console.print("🔗 Auto-attaching to session...")
            time.sleep(1)
            _attach_tmux_session(session_name)

    except subprocess.CalledProcessError as e:
        console.print(f"[red]❌ Failed to create tmux session: {e}[/red]")
        raise typer.Exit(1)


@app.command("list-sessions")
def list_sessions():
    """List all active tmux sessions."""
    _list_tmux_sessions()


@app.command("kill-session")
def kill_session(number: int = typer.Argument(..., help="Session number to kill")):
    """Kill a tmux session by number."""
    _kill_session_by_number(number)


@app.command("attach-session")
def attach_session(number: int = typer.Argument(..., help="Session number to attach to")):
    """Attach to a tmux session by number."""
    _attach_session_by_number(number)


@app.command("kill-all-sessions")
def kill_all_sessions():
    """Kill all likely Claude sessions."""
    try:
        result = subprocess.run(
            ["tmux", "list-sessions", "-F", "#{session_name}"],
            capture_output=True, text=True, check=True
        )
        all_sessions = result.stdout.strip().split('\n') if result.stdout.strip() else []
    except subprocess.CalledProcessError:
        console.print("ℹ️  No active sessions found")
        return

    # Filter for likely Claude sessions
    claude_sessions = [s for s in all_sessions if re.search(r'(claude|_|-)', s) and s != "crashes"]

    if claude_sessions:
        console.print("💀 Found likely Claude sessions:")
        for session in claude_sessions:
            console.print(f"   {session}")
        console.print()
        
        if typer.confirm("Kill these sessions?", default=False):
            for session in claude_sessions:
                subprocess.run(["tmux", "kill-session", "-t", session])
            console.print("[green]✅ Sessions terminated[/green]")
        else:
            console.print("❌ Cancelled")
    else:
        console.print("ℹ️  No Claude sessions to kill")


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
        console.print("📋 Active tmux sessions:")
        console.print("   No active sessions found")
        return

    if not sessions:
        console.print("📋 Active tmux sessions:")
        console.print("   No active sessions found")
        return

    table = Table(title="📋 Active tmux sessions")
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
        console.print("[red]❌ No active sessions found[/red]")
        raise typer.Exit(1)

    if number < 1 or number > len(sessions):
        console.print(f"[red]❌ Invalid session number: {number}[/red]")
        console.print(f"📋 Available sessions (1-{len(sessions)}):")
        _list_tmux_sessions()
        raise typer.Exit(1)

    target_session = sessions[number - 1]
    console.print(f"💀 Killing session #{number}: {target_session}")
    
    try:
        subprocess.run(["tmux", "kill-session", "-t", target_session], check=True)
        console.print("[green]✅ Session killed successfully[/green]")
    except subprocess.CalledProcessError:
        console.print("[red]❌ Failed to kill session[/red]")
        raise typer.Exit(1)


def _attach_session_by_number(number: int):
    """Attach to a tmux session by its number in the list."""
    sessions = _get_tmux_sessions()
    if not sessions:
        console.print("[red]❌ No active sessions found[/red]")
        raise typer.Exit(1)

    if number < 1 or number > len(sessions):
        console.print(f"[red]❌ Invalid session number: {number}[/red]")
        console.print(f"📋 Available sessions (1-{len(sessions)}):")
        _list_tmux_sessions()
        raise typer.Exit(1)

    target_session = sessions[number - 1]
    console.print(f"🔗 Attaching to session #{number}: {target_session}")
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
        console.print(f"📁 Git worktree detected: {session_name}")
        return session_name

    except subprocess.CalledProcessError:
        # Use current directory name
        session_name = Path.cwd().name
        console.print(f"📂 Using directory name: {session_name}")
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

def main():
    app()


if __name__ == "__main__":
    main()