FROM phusion/baseimage:noble-1.0.2
COPY --from=ghcr.io/astral-sh/uv:0.8.10 /uv /uvx /bin/

# Use baseimage-docker's init system.
CMD ["/sbin/my_init"]

# Node.js 22 from NodeSource. apt's `npm` pulls node 18.19, which is too old
# for the ACP adapter (it uses JSON import attributes, `import ... with { type:
# "json" }`, needing node >= 18.20). Install a modern node so both the Claude
# CLI and the ACP adapter run.
RUN apt-get update && apt-get install -y curl ca-certificates && \
    curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && \
    apt-get install -y nodejs

# Install required packages. make and dtach run a project's dev servers in
# the background (ion's `make dev`, previewed through a forwarded port);
# lsof is how `make dev-stop` finds them.
RUN apt-get update && apt-get install openssh-server make dtach lsof -y && \
    # GitHub CLI
    curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
      | dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
      | tee /etc/apt/sources.list.d/github-cli.list > /dev/null && \
    apt-get update && apt-get install gh -y

# Install Claude Code CLI
RUN npm install -g @anthropic-ai/claude-code

# Install the ACP adapter so coder_ui can drive Claude over the Agent Client
# Protocol via `docker exec -i` (ACP-in-Docker, sprint-49). Baked here rather
# than fetched at spawn so container tasks start without a network round-trip.
RUN npm install -g @agentclientprotocol/claude-agent-acp

# Enable SSH service (phusion/baseimage uses runit)
RUN rm -f /etc/service/sshd/down

# Configure SSH for key-based auth only
RUN mkdir -p /var/run/sshd && \
    sed -i 's/#PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config && \
    sed -i 's/#PubkeyAuthentication yes/PubkeyAuthentication yes/' /etc/ssh/sshd_config

# Clean up APT when done.
RUN apt-get clean && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Switch to non-root user (uid 1000, already exists as "ubuntu" in base image).
# Claude Code refuses --dangerously-skip-permissions as root;
# running as uid 1000 solves permissions and file ownership in one step.
USER ubuntu
