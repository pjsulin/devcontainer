######################################
# git_wt_init - Set up Git worktree repo
######################################

git_wt_init() {
    local GIT_URL="$1"
    local MAIN_BRANCH="${2:-main}"

    if [[ "$1" == "--help" || -z "$GIT_URL" ]]; then
        echo ""
        echo "Usage:"
        echo "  git_wt_init <git-url> [main-branch]"
        echo ""
        echo "This will:"
        echo "  - Create a directory based on the repo name"
        echo "  - Clone the bare repo into .bare/"
        echo "  - Create a .git pointer"
        echo "  - Check out the initial branch using worktree"
        echo ""
        echo "💡 Worktree usage examples:"
        echo "  cd <project-dir>"
        echo "  git worktree add -b feature-x feature-x main"
        echo "  git fetch origin"
        echo "  git worktree add feature-y origin/feature-y"
        echo "  git worktree remove feature-x"
        echo "  git branch -D feature-x"
        echo "  git push origin --delete feature-x"
        echo "  git worktree prune"
        echo ""
        return 0
    fi

    # Extract project name from Git URL (e.g., foo.git → foo)
    local PROJ_NAME="$(basename "$GIT_URL" .git)"
    local PROJ_DIR="$PWD/$PROJ_NAME"

    if [[ -e "$PROJ_DIR" ]]; then
        echo "❌ Directory '$PROJ_DIR' already exists. Choose a different location or delete it first."
        return 1
    fi

    # Detect default branch if not provided
    if [[ -z "$MAIN_BRANCH" ]]; then
        echo "🔍 Detecting default branch from remote..."
        MAIN_BRANCH="$(git ls-remote --symref "$GIT_URL" HEAD 2>/dev/null | awk '/^ref:/ {sub("refs/heads/", "", $2); print $2}')"
        if [[ -z "$MAIN_BRANCH" ]]; then
            echo "⚠️  Could not detect default branch. Falling back to 'main'."
            MAIN_BRANCH="main"
        else
            echo "📌 Default branch is '$MAIN_BRANCH'"
        fi
    fi

    echo "📁 Creating project directory: $PROJ_DIR"
    mkdir -p "$PROJ_DIR"
    cd "$PROJ_DIR"

    echo "📦 Cloning bare repo into .bare..."
    git clone --bare "$GIT_URL" .bare

    echo "🔗 Writing .git pointer to .bare..."
    echo "gitdir: ./.bare" > .git

    echo "🌱 Creating initial '$MAIN_BRANCH' worktree..."
    git --git-dir=.bare worktree add "$MAIN_BRANCH" "$MAIN_BRANCH"

    echo ""
    echo "✅ Git worktree repo initialized at:"
    echo "  $PROJ_DIR"
    echo ""
    echo "📂 Layout:"
    echo "  .bare/       → bare repo"
    echo "  .git         → points to .bare"
    echo "  $MAIN_BRANCH/ → initial working branch"
    echo ""
    echo "💡 Worktree usage examples:"
    echo "  cd $PROJ_DIR"
    echo "  git worktree add -b feature-x feature-x $MAIN_BRANCH         # create and checkout new local branch"
    echo "  git fetch origin"
    echo "  git worktree add feature-y origin/feature-y                 # check out existing remote branch"
    echo "  git worktree remove feature-x                               # remove folder and detach worktree"
    echo "  git branch -D feature-x                                     # delete local branch"
    echo "  git push origin --delete feature-x                          # delete remote branch"
    echo "  git worktree prune                                          # clean up metadata"
    echo ""
}


######################################
# Completion for git_wt_init
######################################

_git_wt_init_completions() {
    local cur prev
    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"

    case $COMP_CWORD in
        1)
            # Git remote URLs (https or SSH)
            COMPREPLY=( $(compgen -W "$(grep -Eo 'git@[^ ]+|https://[^ ]+' ~/.bash_history 2>/dev/null)" -- "$cur") )
            ;;
        2)
            # Common branch names
            COMPREPLY=( $(compgen -W "main master trunk" -- "$cur") )
            ;;
    esac
}
complete -F _git_wt_init_completions git_wt_init

######################################
# Alias for git worktree
######################################

alias gwt='git worktree'
type __git_complete &>/dev/null && __git_complete gwt git