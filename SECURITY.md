# Security Policy

## Reporting a vulnerability

Email **zhaoshaofeng892@gmail.com** with subject `[security]`. Please do not
open a public issue for anything exploitable.

This is a one-person project, so set your expectations accordingly: I aim to
acknowledge within 3 business days and to ship a fix or a documented mitigation
within 30 days. If I cannot meet that, I will tell you rather than go quiet.
Coordinated disclosure is welcome; I will credit you unless you ask me not to.

Supported for fixes: the latest release on `main`. Older tags get nothing.

## Threat model — read this before you deploy it

This program's whole purpose is to turn a natural-language request into a
finite-element model, write files, and launch a solver. That is code execution
by design. Two consequences follow.

**1. There is no authentication, and there is not meant to be.**
Anyone who can reach the HTTP port can create runs, read run directories, and
start solver jobs. It is therefore bound to `127.0.0.1` by default — including
in development. `ABAQUS_AGENT_HOST` will let you bind elsewhere, and the moment
you do, you own the consequences: put it behind a reverse proxy that
authenticates, or behind a VPN. Do not put it on `0.0.0.0` and assume the
network is friendly.

Related defaults, all deliberate:

- CORS is **off**. The workbench is served by the same process, so it is
  same-origin and needs none. `ABAQUS_AGENT_CORS_ORIGINS` takes an explicit
  comma-separated allowlist; there is no wildcard mode.
- Solver binaries are never bundled and never auto-downloaded. Abaqus and
  CalculiX are located via `PATH` or an explicit env var and invoked as
  separate processes.

**2. No model-written code is executed. The language model produces data.**
A language model's job here ends at a spec — a YAML document. That spec is
validated against `schema/spec_schema.json` before anything is built
(`agent/llm_planner.py`, `agent/orchestrator.py`), and the Python script that
`abaqus cae` actually runs is generated from the validated spec by this
repository's own code (`runner/build_v2.py` for the v2 dialect,
`runner/build_model.py` for v1). Nothing a model emits is written to a `.py`
and executed.

Understand what this is and is not. It means prompt injection cannot reach the
filesystem by writing Python, because that path does not exist. It does **not**
mean the spec surface is safe: a spec is an instruction to build and solve a
model, the schema constrains its shape rather than its intent, and there is no
sandbox anywhere in this program. The real boundary remains the one above —
you do not point this at untrusted input.

There is no AST-level allowlist on generated script text, and previous versions
of this file said there was. The tool that would have done it
(`tools/static_guard.py`) was never on the data path, and wiring it up as
written would reject this project's own decks: run against the generated
`bearing_block` deck it returns `passed=False`, `Denied import: 'os' at line
7`, and the deck genuinely needs `os` to write into its own run directory. It
is not shipped in the public tree.

## What is in scope

- Authentication or authorisation bypass in the HTTP or MCP server
- A spec that makes the generator emit a script reaching the filesystem, the
  network, or a shell outside its own run directory — the generic dispatch
  layer turns spec keys into Abaqus API calls, so this is the interesting one
- Path traversal out of a run directory via spec fields, run IDs, or artefact
  download endpoints
- Command injection through solver invocation paths or environment handling
- Secrets leaking into logs, reports, capsules, or exported artefacts

## What is not in scope

- "The server has no login" — that is documented above, not a vulnerability.
  A way to reach it from off-host *when bound to loopback* very much is.
- Denial of service by submitting an expensive simulation. Solving big models
  slowly is the product working.
- Anything requiring you to already have local access to the machine and the
  user's own files.
- Vulnerabilities in Abaqus, CalculiX, or other third-party software. Report
  those to their vendors.
