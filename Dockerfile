FROM phusion/baseimage:noble-1.0.2
COPY --from=ghcr.io/astral-sh/uv:0.8.10 /uv /uvx /bin/

# Use baseimage-docker's init system.
CMD ["/sbin/my_init"]

# Install required packages
RUN apt-get update && apt-get install npm openssh-server -y

# Install Claude Code CLI
RUN npm install -g @anthropic-ai/claude-code

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
