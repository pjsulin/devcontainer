#!/bin/bash

# Claude Session Manager for Git Worktrees
# Usage: claude_session [session_name] [--attach]
# Alias: cs

claude_session() {
    local session_name=""
    local auto_attach=false
    local custom_name=""
    local list_sessions=false
    local attach_number=""
    local kill_number=""
    
    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --list|-l)
                list_sessions=true
                shift
                ;;
            --kill|-k)
                if [[ -n "$2" && "$2" =~ ^[0-9]+$ ]]; then
                    kill_number="$2"
                    shift 2
                else
                    echo "❌ --kill requires a session number"
                    echo "Use 'cs -l' to see numbered sessions"
                    return 1
                fi
                ;;
            --attach|-a)
                if [[ -n "$2" && "$2" =~ ^[0-9]+$ ]]; then
                    attach_number="$2"
                    shift 2
                else
                    auto_attach=true
                    shift
                fi
                ;;
            --help|-h)
                echo "Usage: claude_session [session_name] [--attach [number]] [--list] [--kill number]"
                echo ""
                echo "Creates a tmux session with Claude Code running"
                echo ""
                echo "Options:"
                echo "  session_name       Custom session name (optional)"
                echo "  --attach, -a       Automatically attach to session after creation"
                echo "  --attach NUM, -a NUM  Attach to session number NUM from list"
                echo "  --list, -l         List all active tmux sessions with numbers"
                echo "  --kill NUM, -k NUM Kill session number NUM from list"
                echo "  --help, -h         Show this help message"
                echo ""
                echo "Session naming logic:"
                echo "  - In git worktree: REPO:BRANCH"
                echo "  - Not in git worktree: FOLDER_NAME"
                echo "  - Custom name overrides automatic naming"
                echo ""
                echo "Examples:"
                echo "  cs                 # Create session with auto-detected name"
                echo "  cs -l              # List all sessions with numbers"
                echo "  cs -a 3            # Attach to session #3 from the list"
                echo "  cs -k 2            # Kill session #2 from the list"
                echo "  cs my-project -a   # Create 'my-project' session and attach"
                return 0
                ;;
            *)
                custom_name="$1"
                shift
                ;;
        esac
    done
    
    # Handle list sessions
    if [[ "$list_sessions" == true ]]; then
        echo "📋 Active tmux sessions:"
        local sessions=($(tmux list-sessions -F "#{session_name}" 2>/dev/null | sort))
        if [[ ${#sessions[@]} -eq 0 ]]; then
            echo "   No active sessions found"
            return 0
        fi
        
        local i=1
        for session in "${sessions[@]}"; do
            local session_info=$(tmux list-sessions | grep "^$session:" | head -1)
            printf "%2d. %s\n" "$i" "$session_info"
            ((i++))
        done
        return 0
    fi
    
    # Handle kill by number
    if [[ -n "$kill_number" ]]; then
        local sessions=($(tmux list-sessions -F "#{session_name}" 2>/dev/null | sort))
        if [[ ${#sessions[@]} -eq 0 ]]; then
            echo "❌ No active sessions found"
            return 1
        fi
        
        if [[ "$kill_number" -lt 1 || "$kill_number" -gt ${#sessions[@]} ]]; then
            echo "❌ Invalid session number: $kill_number"
            echo "📋 Available sessions (1-${#sessions[@]}):"
            claude_session --list
            return 1
        fi
        
        local target_session="${sessions[$((kill_number-1))]}"
        echo "💀 Killing session #$kill_number: $target_session"
        tmux kill-session -t "$target_session"
        if [[ $? -eq 0 ]]; then
            echo "✅ Session killed successfully"
        else
            echo "❌ Failed to kill session"
        fi
        return 0
    fi
    
    # Handle attach by number
    if [[ -n "$attach_number" ]]; then
        local sessions=($(tmux list-sessions -F "#{session_name}" 2>/dev/null | sort))
        if [[ ${#sessions[@]} -eq 0 ]]; then
            echo "❌ No active sessions found"
            return 1
        fi
        
        if [[ "$attach_number" -lt 1 || "$attach_number" -gt ${#sessions[@]} ]]; then
            echo "❌ Invalid session number: $attach_number"
            echo "📋 Available sessions (1-${#sessions[@]}):"
            claude_session --list
            return 1
        fi
        
        local target_session="${sessions[$((attach_number-1))]}"
        echo "🔗 Attaching to session #$attach_number: $target_session"
        tmux attach-session -t "$target_session"
        return 0
    fi
    
    # Continue with normal session creation logic...
    
    # Determine session name
    if [[ -n "$custom_name" ]]; then
        session_name="$custom_name"
        echo "🎯 Using custom session name: $session_name"
    else
        # Check if we're in a git worktree
        if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
            # Get repository name (from remote or folder name)
            local repo_name=""
            local remote_url=$(git remote get-url origin 2>/dev/null)
            
            if [[ -n "$remote_url" ]]; then
                # Extract repo name from remote URL
                repo_name=$(basename "$remote_url" .git)
            else
                # Fallback to git root directory name
                repo_name=$(basename "$(git rev-parse --show-toplevel)")
            fi
            
            # Get current branch name
            local branch_name=$(git branch --show-current 2>/dev/null)
            if [[ -z "$branch_name" ]]; then
                # Fallback for detached HEAD
                branch_name=$(git rev-parse --short HEAD 2>/dev/null || echo "detached")
            fi
            
            session_name="${repo_name}:${branch_name}"
            echo "📁 Git worktree detected: $session_name"
        else
            # Use current directory name
            session_name=$(basename "$PWD")
            echo "📂 Using directory name: $session_name"
        fi
    fi
    
    # Sanitize session name for tmux (tmux converts : to _)
    local original_name="$session_name"
    session_name=$(echo "$session_name" | sed 's/:/_/g' | sed 's/[^a-zA-Z0-9._-]/_/g')
    
    if [[ "$session_name" != "$original_name" ]]; then
        echo "🔧 Sanitized session name: $original_name → $session_name"
    fi
    
    # Check if session already exists
    if tmux has-session -t "$session_name" 2>/dev/null; then
        echo "⚡ Session '$session_name' already exists!"
        read -p "Do you want to [a]ttach, [k]ill and recreate, or [c]ancel? (a/k/c): " choice
        case $choice in
            a|A|"")
                echo "🔗 Attaching to existing session..."
                tmux attach-session -t "$session_name"
                return 0
                ;;
            k|K)
                echo "💀 Killing existing session..."
                tmux kill-session -t "$session_name"
                ;;
            c|C)
                echo "❌ Cancelled"
                return 0
                ;;
            *)
                echo "❌ Invalid choice. Cancelled."
                return 1
                ;;
        esac
    fi
    
    # Create tmux session
    echo "🚀 Creating tmux session: $session_name"
    echo "📍 Directory: $PWD"
    
    # Create detached session in current directory
    tmux new-session -d -s "$session_name" -c "$PWD"
    
    # Give tmux a moment to create the session
    sleep 0.5
    
    # Check if tmux session was created successfully
    if ! tmux has-session -t "$session_name" 2>/dev/null; then
        echo "❌ Failed to create tmux session '$session_name'"
        echo "🔍 Checking if tmux created it with a different name..."
        echo "📋 Current sessions:"
        tmux list-sessions 2>/dev/null
        return 1
    fi
    
    # Configure the session
    tmux send-keys -t "$session_name" "clear" C-m
    tmux send-keys -t "$session_name" "echo '🤖 Starting Claude Code session for: $session_name'" C-m
    tmux send-keys -t "$session_name" "echo '📁 Directory: $PWD'" C-m
    
    # Check if claude command exists
    if ! command -v claude >/dev/null 2>&1; then
        echo "⚠️  Warning: 'claude' command not found"
        echo "   Make sure Claude Code is installed and in your PATH"
        tmux send-keys -t "$session_name" "echo 'Warning: claude command not found. Please install Claude Code.'" C-m
    else
        # Start Claude
        echo "🤖 Starting Claude Code..."
        tmux send-keys -t "$session_name" "claude" C-m
    fi
    
    # Set window name
    tmux rename-window -t "$session_name:0" "claude"
    
    echo "✅ Session created successfully!"
    echo "🔗 Connect with: tmux attach -t '$session_name'"
    
    # Auto-attach if requested
    if [[ "$auto_attach" == true ]]; then
        echo "🔗 Auto-attaching to session..."
        sleep 1  # Brief pause to let Claude start
        tmux attach-session -t "$session_name"
    fi
}

# Convenience aliases
alias cs='claude_session'
alias claude-session='claude_session'

# Helper functions for session management
claude_session_list() {
    claude_session --list
}

claude_session_attach() {
    if [[ -n "$1" ]]; then
        claude_session --attach "$1"
    else
        echo "Usage: claude_session_attach <number>"
        echo "Use 'cs -l' to see numbered session list"
    fi
}

claude_session_kill() {
    if [[ -n "$1" ]]; then
        claude_session --kill "$1"
    else
        echo "Usage: claude_session_kill <number>"
        echo "Use 'cs -l' to see numbered session list"
    fi
}

claude_session_kill_all() {
    # Get all sessions except some known system ones
    local all_sessions=$(tmux list-sessions -F "#{session_name}" 2>/dev/null)
    local claude_sessions=""
    
    # Filter for likely Claude sessions (contains underscore, dash, or "claude")
    while IFS= read -r session; do
        if [[ "$session" =~ (claude|_|-) && "$session" != "crashes" ]]; then
            claude_sessions+="$session"$'\n'
        fi
    done <<< "$all_sessions"
    
    # Remove trailing newline
    claude_sessions=$(echo -n "$claude_sessions")
    
    if [[ -n "$claude_sessions" ]]; then
        echo "💀 Found likely Claude sessions:"
        echo "$claude_sessions" | sed 's/^/   /'
        echo ""
        read -p "Kill these sessions? (y/N): " confirm
        if [[ "$confirm" =~ ^[Yy]$ ]]; then
            echo "$claude_sessions" | xargs -I {} tmux kill-session -t {}
            echo "✅ Sessions terminated"
        else
            echo "❌ Cancelled"
        fi
    else
        echo "ℹ️  No Claude sessions to kill"
    fi
}

# Additional aliases
alias cs-list='claude_session --list'
alias cs-l='claude_session --list'
alias cs-attach='claude_session_attach'
alias cs-kill-all='claude_session_kill_all'
