# Contributing to Abaqus Agent

Thanks for your interest in contributing! This guide will help you get started.

## Development Setup

```bash
# Clone the repository
git clone https://github.com/Tomsabay/abaqus_agent.git
cd abaqus_agent

# Install in development mode with all extras
pip install -e ".[dev,mcp]"

# Run tests (no Abaqus required)
pytest tests/ -v

# Run linter
ruff check .
```

## Project Architecture

```
User (NL) --> LLMPlanner --> spec.yaml --> Pipeline --> KPI Report

Key modules:
  core/       - Shared pipeline logic and helpers
  agent/      - LLM planner and orchestrator
  runner/     - Abaqus job execution stages
  post/       - Post-processing and KPI extraction
  tools/      - Validators, error handling, security guards
  premium/    - Premium feature modules (gated)
  server.py   - FastAPI REST API
  mcp_server.py - MCP server for AI agent integration
```

## How to Contribute

### Reporting Bugs

Open a [bug report](https://github.com/Tomsabay/abaqus_agent/issues/new?template=bug_report.yml) with:
- Abaqus version and OS
- Steps to reproduce
- Error output / logs

### Suggesting Features

Open a [feature request](https://github.com/Tomsabay/abaqus_agent/issues/new?template=feature_request.yml).

### Submitting Pull Requests

1. Fork the repo and create a branch from `main`
2. Make your changes
3. Add or update tests as needed
4. Ensure `pytest tests/ -v` passes
5. Ensure `ruff check .` passes
6. Submit your PR

### Good First Issues

Look for issues tagged with [`good first issue`](https://github.com/Tomsabay/abaqus_agent/labels/good%20first%20issue) — these are great starting points for new contributors.

## Code Style

- We use [ruff](https://docs.astral.sh/ruff/) for linting
- Line length: 100 characters
- Target: Python 3.10+

## Testing

- All tests run without Abaqus installed (mocked execution)
- Use `pytest tests/ -v` to run the full suite
- Use `python run_benchmark.py --dry-run` to validate specs

## License

By contributing, you agree that your contributions will be licensed under the Apache 2.0 License.
