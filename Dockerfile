FROM phusion/baseimage:noble-1.0.2
COPY --from=ghcr.io/astral-sh/uv:0.8.10 /uv /uvx /bin/

# Use baseimage-docker's init system.
CMD ["/sbin/my_init"]

# Install required packages
RUN apt-get update && apt-get install npm -y

# Install Claude Code CLI
RUN npm install -g @anthropic-ai/claude-code

# Install coder_ui backend
COPY coder_ui/ /opt/coder_ui/
RUN cd /opt/coder_ui && uv pip install --system -e .
ENV DATABASE_URL=sqlite+aiosqlite:////workspace/.coder_ui/coder_ui.db

# Clean up APT when done.
RUN apt-get clean && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*
