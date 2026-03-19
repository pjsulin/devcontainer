#!/usr/bin/env python3
"""dsm - dtach session manager

Manage persistent detachable terminal sessions using dtach,
with container and git worktree support.

Usage:
    dsm create -t "Title" [-d "Description"] [-C DIR] -- <command...>
    dsm ssh HOST [-t TITLE] [-d DESC] [SSH_ARGS...]
    dsm container -t TITLE REPO_PATH BRANCH [--image IMG] [-- CMD]
    dsm init-worktree URL [BRANCH]
    dsm list
    dsm resume <id>
    dsm tail <id> [<id>...]
    dsm rm <id>
    dsm clean
    dsm alias set|ls|rm
"""

import argparse
import json
import os
import re
import shlex
import shutil
import socket
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

DSM_DIR = Path.home() / ".dsm"


# ── Utilities ──────────────────────────────────────────────────────────────


def slugify(text: str) -> str:
    slug = text.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug.strip("-")


def unique_id(slug: str) -> str:
    if not (DSM_DIR / slug).exists():
        return slug
    i = 2
    while (DSM_DIR / f"{slug}-{i}").exists():
        i += 1
    return f"{slug}-{i}"


def socket_alive(sock_path: Path) -> bool:
    if not sock_path.exists():
        return False
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(0.5)
        s.connect(str(sock_path))
        s.close()
        return True
    except (ConnectionRefusedError, FileNotFoundError, OSError):
        return False


def container_alive(name: str) -> bool:
    try:
        result = subprocess.run(
            ["docker", "ps", "-q", "-f", f"name=^{name}$"],
            capture_output=True, text=True, check=True,
        )
        return bool(result.stdout.strip())
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def load_meta(session_dir: Path) -> dict | None:
    meta_path = session_dir / "meta.json"
    if not meta_path.exists():
        return None
    with open(meta_path) as f:
        return json.load(f)


def save_meta(session_dir: Path, meta: dict):
    meta["modified_at"] = datetime.now().isoformat()
    with open(session_dir / "meta.json", "w") as f:
        json.dump(meta, f, indent=2)


def find_session(sid: str) -> Path:
    session_dir = DSM_DIR / sid
    if session_dir.exists() and (session_dir / "meta.json").exists():
        return session_dir
    matches = [
        d for d in DSM_DIR.iterdir()
        if d.is_dir() and d.name.startswith(sid) and (d / "meta.json").exists()
    ]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        print(f"Error: ambiguous id '{sid}', matches: {', '.join(d.name for d in matches)}", file=sys.stderr)
        sys.exit(1)
    print(f"Error: session '{sid}' not found", file=sys.stderr)
    sys.exit(1)


def session_status(session_dir: Path, meta: dict) -> str:
    stype = meta.get("type", "local")
    if stype == "container":
        cname = meta.get("container", {}).get("name", "")
        return "live" if container_alive(cname) else "dead"
    return "live" if socket_alive(session_dir / "socket") else "dead"


def next_session_number() -> int:
    if not DSM_DIR.exists():
        return 1
    nums = []
    for d in DSM_DIR.iterdir():
        meta = load_meta(d)
        if meta and meta.get("title", "").startswith("session-"):
            try:
                nums.append(int(meta["title"].split("-", 1)[1]))
            except (ValueError, IndexError):
                pass
    return max(nums, default=0) + 1


def dtach_exec(sock: str, command: list[str], log_path: str | None = None):
    """Launch dtach with optional output capture via script."""
    if log_path:
        # macOS uses -F for flush, Linux uses -f
        script_cmd = ["script", "-q", "-F", log_path] + command
        os.execvp("dtach", ["dtach", "-c", sock, "-z"] + script_cmd)
    else:
        os.execvp("dtach", ["dtach", "-c", sock, "-z"] + command)


# ── Aliases ────────────────────────────────────────────────────────────────


def load_aliases() -> dict:
    alias_file = DSM_DIR / "aliases.json"
    if not alias_file.exists():
        return {}
    with open(alias_file) as f:
        return json.load(f)


def save_aliases(aliases: dict):
    DSM_DIR.mkdir(parents=True, exist_ok=True)
    with open(DSM_DIR / "aliases.json", "w") as f:
        json.dump(aliases, f, indent=2)


def resolve_alias(host: str) -> str:
    aliases = load_aliases()
    return aliases.get(host, host)


# ── Worktree helpers ───────────────────────────────────────────────────────


def create_git_worktree(repo_path: Path, branch_name: str):
    """Create a git worktree for the specified branch (3-tier: remote, local, new)."""
    worktree_path = repo_path / branch_name
    original_cwd = os.getcwd()
    os.chdir(repo_path)
    try:
        # Tier 1: remote branch
        try:
            subprocess.run(
                ["git", "worktree", "add", str(worktree_path), f"origin/{branch_name}"],
                check=True, capture_output=True,
            )
            print(f"Created worktree from remote branch 'origin/{branch_name}'")
            return
        except subprocess.CalledProcessError:
            pass

        # Tier 2: local branch
        try:
            subprocess.run(
                ["git", "worktree", "add", str(worktree_path), branch_name],
                check=True, capture_output=True,
            )
            print(f"Created worktree from local branch '{branch_name}'")
            return
        except subprocess.CalledProcessError:
            pass

        # Tier 3: new branch from default
        try:
            result = subprocess.run(
                ["git", "symbolic-ref", "refs/remotes/origin/HEAD"],
                capture_output=True, text=True, check=True,
            )
            default_branch = result.stdout.strip().split("/")[-1]
        except subprocess.CalledProcessError:
            default_branch = "main"

        subprocess.run(
            ["git", "worktree", "add", "-b", branch_name, str(worktree_path), default_branch],
            check=True,
        )
        print(f"Created new branch '{branch_name}' and worktree from '{default_branch}'")
    except subprocess.CalledProcessError as e:
        print(f"Error: failed to create git worktree: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        os.chdir(original_cwd)


def get_anthropic_key() -> Optional[str]:
    """Get Anthropic API key from environment, config files, or shell configs."""
    # Environment variable
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if api_key:
        print("Found Anthropic API key in environment variable")
        return api_key

    # Claude config locations
    claude_config_paths = [
        Path.home() / ".config" / "claude" / "config.json",
        Path.home() / ".claude" / "config.json",
        Path.home() / "Library" / "Application Support" / "Claude" / "config.json",
    ]
    for config_path in claude_config_paths:
        if config_path.exists():
            try:
                with open(config_path) as f:
                    config = json.load(f)
                    for key_name in ("api_key", "anthropic_api_key"):
                        if key_name in config:
                            print(f"Found Anthropic API key in {config_path}")
                            return config[key_name]
            except (json.JSONDecodeError, KeyError, IOError):
                continue

    # Shell configs
    shell_configs = [
        Path.home() / ".bashrc",
        Path.home() / ".zshrc",
        Path.home() / ".bash_profile",
        Path.home() / ".profile",
    ]
    for shell_config in shell_configs:
        if shell_config.exists():
            try:
                with open(shell_config) as f:
                    content = f.read()
                    match = re.search(
                        r'export\s+ANTHROPIC_API_KEY\s*=\s*["\']?([^"\'\s]+)["\']?',
                        content,
                    )
                    if match:
                        print(f"Found Anthropic API key in {shell_config}")
                        return match.group(1)
            except IOError:
                continue

    return None


# ── Commands ───────────────────────────────────────────────────────────────


def cmd_create(args):
    if not args.command:
        print("Error: no command specified after --", file=sys.stderr)
        sys.exit(1)

    if not shutil.which("dtach"):
        print("Error: dtach is not installed", file=sys.stderr)
        sys.exit(1)

    slug = slugify(args.title)
    if not slug:
        print("Error: title produces empty slug", file=sys.stderr)
        sys.exit(1)

    sid = unique_id(slug)
    session_dir = DSM_DIR / sid
    session_dir.mkdir(parents=True)

    command = args.command
    if command and command[0] == "claude" and "--dangerously-skip-permissions" not in command:
        command = [command[0], "--dangerously-skip-permissions"] + command[1:]

    cwd = os.path.abspath(args.dir) if args.dir else os.getcwd()
    if not os.path.isdir(cwd):
        print(f"Error: directory '{cwd}' does not exist", file=sys.stderr)
        sys.exit(1)
    os.chdir(cwd)

    meta = {
        "id": sid,
        "type": "local",
        "title": args.title,
        "description": args.description or "",
        "command": command,
        "cwd": cwd,
        "created_at": datetime.now().isoformat(),
        "modified_at": datetime.now().isoformat(),
    }
    save_meta(session_dir, meta)

    sock = str(session_dir / "socket")
    log_path = str(session_dir / "output.log")
    dtach_exec(sock, command, log_path)


def cmd_ssh(args):
    host = resolve_alias(args.host)
    title = args.title or f"session-{next_session_number()}"
    description = args.description or f"SSH session to {host}"

    if not shutil.which("dtach"):
        print("Error: dtach is not installed", file=sys.stderr)
        sys.exit(1)

    slug = slugify(title)
    if not slug:
        print("Error: title produces empty slug", file=sys.stderr)
        sys.exit(1)

    sid = unique_id(slug)
    session_dir = DSM_DIR / sid
    session_dir.mkdir(parents=True)

    keepalive = [
        "-o", "ServerAliveInterval=60",
        "-o", "ServerAliveCountMax=3",
        "-o", "TCPKeepAlive=yes",
    ]
    ssh_cmd = ["ssh"] + keepalive + args.ssh_args + [host]

    meta = {
        "id": sid,
        "type": "ssh",
        "title": title,
        "description": description,
        "command": ssh_cmd,
        "cwd": os.getcwd(),
        "created_at": datetime.now().isoformat(),
        "modified_at": datetime.now().isoformat(),
    }
    save_meta(session_dir, meta)

    sock = str(session_dir / "socket")
    log_path = str(session_dir / "output.log")
    dtach_exec(sock, ssh_cmd, log_path)


def cmd_container(args):
    repo_path = Path(args.repo_path).resolve()
    branch = args.branch
    image = args.image or "devcontainer:latest"

    # Validate repo path is git repo
    if not repo_path.exists():
        print(f"Error: repository path does not exist: {repo_path}", file=sys.stderr)
        sys.exit(1)
    if not (repo_path / ".git").exists() and not (repo_path / ".bare").exists():
        print(f"Error: path is not a git repository: {repo_path}", file=sys.stderr)
        sys.exit(1)

    repo_name = repo_path.name
    container_name = f"dsm_{repo_name}_{branch}"
    # Sanitize for docker
    container_name = re.sub(r"[^a-zA-Z0-9._-]", "_", container_name)

    title = args.title or f"{repo_name}/{branch}"
    slug = slugify(title)
    if not slug:
        slug = container_name
    sid = unique_id(slug)
    session_dir = DSM_DIR / sid
    session_dir.mkdir(parents=True)

    # Create worktree if missing
    worktree_path = repo_path / branch
    if not worktree_path.exists():
        print(f"Creating git worktree for branch '{branch}'...")
        create_git_worktree(repo_path, branch)
    else:
        print(f"Using existing worktree: {worktree_path}")

    # Determine command
    command = args.command if args.command else ["claude", "--dangerously-skip-permissions"]

    # Get API key
    anthropic_key = get_anthropic_key()

    # docker run
    docker_cmd = [
        "docker", "run", "-d", "--name", container_name,
        "-v", f"{worktree_path}:/workspace",
        "-w", "/workspace",
    ]
    if anthropic_key:
        docker_cmd.extend(["-e", f"ANTHROPIC_API_KEY={anthropic_key}"])
    else:
        print("Warning: no Anthropic API key found - Claude Code may not work in container", file=sys.stderr)
    docker_cmd.extend([image, "sleep", "infinity"])

    try:
        subprocess.run(docker_cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error: failed to start container: {e}", file=sys.stderr)
        shutil.rmtree(session_dir)
        sys.exit(1)

    print(f"Container '{container_name}' started")

    # Save metadata
    meta = {
        "id": sid,
        "type": "container",
        "title": title,
        "description": "",
        "command": command,
        "cwd": str(repo_path),
        "created_at": datetime.now().isoformat(),
        "modified_at": datetime.now().isoformat(),
        "container": {
            "name": container_name,
            "image": image,
            "repo_path": str(repo_path),
            "branch": branch,
            "worktree_path": str(worktree_path),
        },
    }
    save_meta(session_dir, meta)

    # Exec into container and run command
    exec_cmd = ["docker", "exec", "-it", container_name, "bash", "-lc",
                 f"cd /workspace && {shlex.join(command)}"]
    os.execvp("docker", exec_cmd)


def cmd_list(args):
    if not DSM_DIR.exists():
        print("No sessions.")
        return

    sessions = []
    for d in sorted(DSM_DIR.iterdir()):
        meta = load_meta(d)
        if meta is None:
            continue
        meta["_dir"] = d
        meta["status"] = session_status(d, meta)
        sessions.append(meta)

    if not sessions:
        print("No sessions.")
        return

    id_w = max(len(s["id"]) for s in sessions)
    type_w = max(len(s.get("type", "local")) for s in sessions)
    title_w = max(len(s["title"]) for s in sessions)
    status_w = 6
    cmd_w = max(len(shlex.join(s["command"])) for s in sessions)

    header = (
        f"{'ID':<{id_w}}  {'TYPE':<{type_w}}  {'STATUS':<{status_w}}  {'TITLE':<{title_w}}  "
        f"{'COMMAND':<{cmd_w}}  {'CREATED'}"
    )
    print(header)
    print("-" * len(header))

    for s in sessions:
        created = datetime.fromisoformat(s["created_at"]).strftime("%Y-%m-%d %H:%M")
        cmd_str = shlex.join(s["command"])
        stype = s.get("type", "local")
        print(
            f"{s['id']:<{id_w}}  {stype:<{type_w}}  {s['status']:<{status_w}}  {s['title']:<{title_w}}  "
            f"{cmd_str:<{cmd_w}}  {created}"
        )


def cmd_resume(args):
    session_dir = find_session(args.id)
    meta = load_meta(session_dir)
    stype = meta.get("type", "local")

    if stype == "container":
        cinfo = meta.get("container", {})
        cname = cinfo.get("name", "")
        command = meta.get("command", ["claude", "--dangerously-skip-permissions"])

        if not container_alive(cname):
            print(f"Container '{cname}' is dead. Recreating...", file=sys.stderr)
            # Remove old container if it exists (stopped)
            subprocess.run(["docker", "rm", cname], capture_output=True)
            # Re-run container
            image = cinfo.get("image", "devcontainer:latest")
            worktree_path = cinfo.get("worktree_path", "")
            docker_cmd = [
                "docker", "run", "-d", "--name", cname,
                "-v", f"{worktree_path}:/workspace",
                "-w", "/workspace",
            ]
            anthropic_key = get_anthropic_key()
            if anthropic_key:
                docker_cmd.extend(["-e", f"ANTHROPIC_API_KEY={anthropic_key}"])
            docker_cmd.extend([image, "sleep", "infinity"])
            try:
                subprocess.run(docker_cmd, check=True)
            except subprocess.CalledProcessError as e:
                print(f"Error: failed to recreate container: {e}", file=sys.stderr)
                sys.exit(1)
            print(f"Container '{cname}' recreated")
            save_meta(session_dir, meta)
            # Exec with command
            exec_cmd = ["docker", "exec", "-it", cname, "bash", "-lc",
                         f"cd /workspace && {shlex.join(command)}"]
            os.execvp("docker", exec_cmd)
        else:
            save_meta(session_dir, meta)
            # Attach to running container
            os.execvp("docker", ["docker", "exec", "-it", cname, "bash", "-l"])
    else:
        # local or ssh
        sock = session_dir / "socket"
        if not socket_alive(sock):
            print(f"Session '{meta['id']}' is dead. Recreating...", file=sys.stderr)
            save_meta(session_dir, meta)
            cwd = meta.get("cwd", os.getcwd())
            os.chdir(cwd)
            log_path = str(session_dir / "output.log")
            dtach_exec(str(sock), meta["command"], log_path)
        else:
            save_meta(session_dir, meta)
            os.execvp("dtach", ["dtach", "-a", str(sock), "-z"])


def cmd_tail(args):
    if not args.ids:
        print("Error: at least one session ID required", file=sys.stderr)
        sys.exit(1)

    log_files = []
    for sid in args.ids:
        session_dir = find_session(sid)
        meta = load_meta(session_dir)
        stype = meta.get("type", "local")
        if stype == "container":
            print(f"Tail not supported for container sessions (use 'dsm resume {meta['id']}' instead)", file=sys.stderr)
            sys.exit(1)
        log_path = session_dir / "output.log"
        if not log_path.exists():
            print(f"Error: no output log for session '{meta['id']}' (session may predate output capture)", file=sys.stderr)
            sys.exit(1)
        log_files.append(str(log_path))

    os.execvp("tail", ["tail", "-f"] + log_files)


def cmd_init_worktree(args):
    git_url = args.url
    main_branch = args.branch

    proj_name = Path(git_url).stem
    proj_dir = Path.cwd() / proj_name

    if proj_dir.exists():
        print(f"Error: directory '{proj_dir}' already exists", file=sys.stderr)
        sys.exit(1)

    # Detect default branch if not provided
    if not main_branch:
        print("Detecting default branch from remote...")
        try:
            result = subprocess.run(
                ["git", "ls-remote", "--symref", git_url, "HEAD"],
                capture_output=True, text=True, check=True,
            )
            for line in result.stdout.split("\n"):
                if line.startswith("ref: refs/heads/"):
                    main_branch = line.split("refs/heads/")[1].split()[0]
                    print(f"Default branch is '{main_branch}'")
                    break
        except subprocess.CalledProcessError:
            pass
        if not main_branch:
            print("Could not detect default branch, falling back to 'main'")
            main_branch = "main"

    print(f"Creating project directory: {proj_dir}")
    proj_dir.mkdir(parents=True)
    os.chdir(proj_dir)

    print("Cloning bare repo into .bare...")
    subprocess.run(["git", "clone", "--bare", git_url, ".bare"], check=True)

    print("Writing .git pointer to .bare...")
    with open(".git", "w") as f:
        f.write("gitdir: ./.bare\n")

    print(f"Creating initial '{main_branch}' worktree...")
    subprocess.run(
        ["git", "--git-dir=.bare", "worktree", "add", main_branch, main_branch],
        check=True,
    )

    print(f"""
Git worktree repo initialized at:
  {proj_dir}

Layout:
  .bare/       -> bare repo
  .git         -> points to .bare
  {main_branch}/         -> initial working branch

Worktree usage:
  cd {proj_dir}
  git worktree add -b feature-x feature-x {main_branch}
  git fetch origin
  git worktree add feature-y origin/feature-y
  git worktree remove feature-x
""")


def cmd_alias(args):
    if args.alias_cmd == "set":
        aliases = load_aliases()
        aliases[args.name] = args.target
        save_aliases(aliases)
        print(f"Alias '{args.name}' -> {args.target}")
    elif args.alias_cmd == "ls":
        aliases = load_aliases()
        if not aliases:
            print("No aliases.")
            return
        name_w = max(len(n) for n in aliases)
        for name, target in sorted(aliases.items()):
            print(f"  {name:<{name_w}}  ->  {target}")
    elif args.alias_cmd == "rm":
        aliases = load_aliases()
        if args.name not in aliases:
            print(f"Error: alias '{args.name}' not found", file=sys.stderr)
            sys.exit(1)
        del aliases[args.name]
        save_aliases(aliases)
        print(f"Removed alias '{args.name}'")
    else:
        print("Usage: dsm alias {set,ls,rm}", file=sys.stderr)


def cmd_clean(args):
    if not DSM_DIR.exists():
        print("No sessions.")
        return
    removed = 0
    for d in sorted(DSM_DIR.iterdir()):
        meta = load_meta(d)
        if meta is None:
            continue
        status = session_status(d, meta)
        if status == "dead":
            stype = meta.get("type", "local")
            if stype == "container":
                cname = meta.get("container", {}).get("name", "")
                # Stop and remove container if it still exists (stopped state)
                subprocess.run(["docker", "stop", cname], capture_output=True)
                subprocess.run(["docker", "rm", cname], capture_output=True)
            shutil.rmtree(d)
            print(f"  Removed dead session '{meta['id']}'")
            removed += 1
    if removed == 0:
        print("No dead sessions.")
    else:
        print(f"Cleaned {removed} dead session(s).")


def cmd_rm(args):
    session_dir = find_session(args.id)
    meta = load_meta(session_dir)
    stype = meta.get("type", "local")

    if stype == "container":
        cname = meta.get("container", {}).get("name", "")
        if container_alive(cname):
            print(f"Container '{cname}' is still running. Stop it? [y/N] ", end="", flush=True)
            if input().strip().lower() != "y":
                return
        subprocess.run(["docker", "stop", cname], capture_output=True)
        subprocess.run(["docker", "rm", cname], capture_output=True)
    else:
        sock = session_dir / "socket"
        if socket_alive(sock):
            print(f"Session '{meta['id']}' is still live. Kill it? [y/N] ", end="", flush=True)
            if input().strip().lower() != "y":
                return

    shutil.rmtree(session_dir)
    print(f"Removed session '{meta['id']}'")


# ── Main / argparse ───────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        prog="dsm",
        description="dtach session manager — local, SSH, and container sessions",
        epilog=(
            "examples:\n"
            "  # Local sessions\n"
            "  dsm create -t 'organon' -C ~/projects/organon -- claude\n"
            "  dsm create -t 'Dev server' -- npm run dev\n"
            "\n"
            "  # SSH sessions\n"
            "  dsm ssh prod                               SSH using saved alias\n"
            "  dsm ssh user@10.0.0.1                      SSH directly to host\n"
            "\n"
            "  # Container sessions\n"
            "  dsm container -t mytest /path/to/repo main\n"
            "  dsm con -t mytest /path/to/repo feature-x --image myimg:latest\n"
            "  dsm con -t mytest /path/to/repo main -- bash\n"
            "\n"
            "  # Init worktree repo\n"
            "  dsm init-worktree https://github.com/user/repo.git\n"
            "\n"
            "  # Managing sessions\n"
            "  dsm ls                                     list all sessions\n"
            "  dsm resume organon                         reattach to session\n"
            "  dsm tail organon                           tail session output\n"
            "  dsm rm organon                             remove a session\n"
            "  dsm clean                                  remove all dead sessions\n"
            "\n"
            "  # Aliases\n"
            "  dsm alias set prod user@10.0.0.1\n"
            "  dsm alias ls\n"
            "  dsm alias rm prod\n"
            "\n"
            "workflow:\n"
            "  1. dsm create/ssh/container    create and attach\n"
            "  2. ctrl+\\                      detach (session keeps running)\n"
            "  3. dsm ls                      see all sessions\n"
            "  4. dsm resume <id>             reattach\n"
            "  5. dsm tail <id>               follow output (local/ssh only)\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="cmd")

    # create
    p_create = sub.add_parser(
        "create", aliases=["c"],
        help="Create and attach to a new local session",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_create.add_argument("-t", "--title", required=True, help="Session title (used to generate ID)")
    p_create.add_argument("-d", "--description", default="", help="Optional description")
    p_create.add_argument("-C", "--dir", default="", help="Working directory for the session")

    # ssh
    p_ssh = sub.add_parser(
        "ssh",
        help="Create an SSH session",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_ssh.add_argument("host", help="SSH destination (user@host or alias)")
    p_ssh.add_argument("-t", "--title", default="", help="Session title")
    p_ssh.add_argument("-d", "--description", default="", help="Optional description")
    p_ssh.add_argument("ssh_args", nargs="*", help="Extra SSH args")

    # container
    p_container = sub.add_parser(
        "container", aliases=["con"],
        help="Create a container session with worktree",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_container.add_argument("-t", "--title", default="", help="Session title")
    p_container.add_argument("repo_path", help="Path to git worktree repo")
    p_container.add_argument("branch", help="Branch name")
    p_container.add_argument("--image", default="", help="Docker image (default: devcontainer:latest)")

    # init-worktree
    p_iw = sub.add_parser(
        "init-worktree", aliases=["iw"],
        help="Init a bare-clone worktree repo",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_iw.add_argument("url", help="Git repository URL")
    p_iw.add_argument("branch", nargs="?", default=None, help="Main branch name (auto-detected if omitted)")

    # alias
    p_alias = sub.add_parser("alias", help="Manage remote host aliases")
    alias_sub = p_alias.add_subparsers(dest="alias_cmd")
    p_alias_set = alias_sub.add_parser("set", help="Save an alias")
    p_alias_set.add_argument("name", help="Alias name")
    p_alias_set.add_argument("target", help="SSH destination (user@host)")
    alias_sub.add_parser("ls", help="List aliases")
    p_alias_rm = alias_sub.add_parser("rm", help="Remove an alias")
    p_alias_rm.add_argument("name", help="Alias name to remove")

    # list
    sub.add_parser("list", aliases=["ls"], help="List all sessions")

    # resume
    p_resume = sub.add_parser(
        "resume", aliases=["r"],
        help="Reattach to a session (restarts if dead)",
    )
    p_resume.add_argument("id", help="Session ID (or unique prefix)")

    # tail
    p_tail = sub.add_parser("tail", help="Tail session output logs")
    p_tail.add_argument("ids", nargs="+", help="Session ID(s)")

    # rm
    p_rm = sub.add_parser("rm", help="Remove a session")
    p_rm.add_argument("id", help="Session ID (or unique prefix)")

    # clean
    sub.add_parser("clean", help="Remove all dead sessions")

    # Split on -- to separate dsm args from session command
    argv = sys.argv[1:]
    if "--" in argv:
        split_idx = argv.index("--")
        dsm_args = argv[:split_idx]
        cmd_args = argv[split_idx + 1:]
    else:
        dsm_args = argv
        cmd_args = []

    args = parser.parse_args(dsm_args)
    args.command = cmd_args

    if args.cmd in ("create", "c"):
        cmd_create(args)
    elif args.cmd == "ssh":
        cmd_ssh(args)
    elif args.cmd in ("container", "con"):
        cmd_container(args)
    elif args.cmd in ("init-worktree", "iw"):
        cmd_init_worktree(args)
    elif args.cmd == "alias":
        cmd_alias(args)
    elif args.cmd in ("list", "ls"):
        cmd_list(args)
    elif args.cmd in ("resume", "r"):
        cmd_resume(args)
    elif args.cmd == "tail":
        cmd_tail(args)
    elif args.cmd == "rm":
        cmd_rm(args)
    elif args.cmd == "clean":
        cmd_clean(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
