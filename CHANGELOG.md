# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-03-07

### Added

- 7-stage Abaqus FEA pipeline: validate, build, syntaxcheck, submit, monitor, extract, compare
- MCP (Model Context Protocol) server for AI agent integration
- HTTP-to-MCP bridge for web clients
- FastAPI REST API with SSE streaming for real-time progress
- Web frontend with transport mode toggle (Direct API / MCP)
- NL-to-Spec generation via LLM (Anthropic, OpenAI, or template fallback)
- 5 premium features: multi-physics coupling, mesh adaptivity, parametric sweeps, extended geometry, auto-repair
- Static AST security guard blocking dangerous code in LLM-generated scripts
- Schema validation for problem specifications
- 4 benchmark cases: cantilever, plate_hole, modal, explicit_impact
- Benchmark runner with Markdown report generation
- 197 unit tests (no Abaqus required)
- Structured error codes with recovery suggestions
