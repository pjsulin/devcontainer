# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.0] - 2026-10-05

### Added

- Node.js 22 (NodeSource), replacing apt's node 18
- Claude ACP adapter (`@agentclientprotocol/claude-agent-acp`) for ACP-in-Docker
- make, dtach and lsof for background dev servers

### Changed

- Pin the Claude ACP adapter to 0.85.1 via `ARG CLAUDE_AGENT_ACP_VERSION`, matching
  ion's `transport.acp.adapter.version`; bump both together

## [0.2.2] - 2026-04-09

### Fixed

- Trigger publish workflow on tag push instead of GitHub Release

## [0.2.1] - 2026-04-08

### Fixed

- Add gh CLI to devcontainer for automated releases

## [0.2.0] - 2026-04-07

### Added

- SSH access with key-based authentication
- Docker Hub publish workflow
- Non-root user (uid 1000) for Claude Code compatibility
- uv package manager
- Claude Code CLI
- Base devcontainer with phusion/baseimage

[Unreleased]: https://github.com/pjsulin/devcontainer/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/pjsulin/devcontainer/compare/v0.2.2...v0.3.0
[0.2.2]: https://github.com/pjsulin/devcontainer/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/pjsulin/devcontainer/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/pjsulin/devcontainer/releases/tag/v0.2.0
