# Abaqus/CAE Copilot MVP

This MVP is the user-facing "Cursor for Abaqus/CAE" path:

1. Start the local AbaqusAgent server.
2. Open the Copilot sidecar in a browser.
3. Ask for an Abaqus model in natural language.
4. The local Codex app-server turns the request into white-listed actions.
5. The Abaqus plug-in pulls approved actions and executes deterministic Abaqus Python.
6. Abaqus solves the model and writes result JSON.

## Start Server

```bash
.venv/bin/uvicorn server:app --host 0.0.0.0 --port 8000
```

Use `0.0.0.0` when Abaqus/CAE runs on another workstation in the same private
network or Tailscale tailnet.

## Install Plug-in

Choose the Abaqus/CAE plug-ins directory yourself, then copy the plug-in:

```bash
abaqus-agent-copilot-install-plugin --plugin-dir /path/to/abaqus_plugins
```

The command only copies `abaqusAgent_plugin.py`. It does not modify Abaqus,
system environment variables, or license settings. It also writes
`abaqus_agent_config.json` in the plug-in directory so remote Abaqus/CAE can
find the sidecar server without manually setting environment variables.

The sidecar also exposes the same setup path from:

```text
GET /api/copilot/plugin-guide
```

That endpoint returns the current server URL, the install command, the
`ABAQUS_AGENT_SERVER_URL` value for remote Abaqus workstations, and the exact
Abaqus/CAE menu names.

## Use In Abaqus/CAE

1. Restart Abaqus/CAE after installing the plug-in.
2. Open `Plug-ins -> AbaqusAgent Copilot: Open Sidecar`.
3. In the sidecar, enter a request such as:

   ```text
   帮我建一个 200mm 长、20mm 高、20mm 宽的悬臂梁，材料钢，左端固定，
   右端向下 100N，运行并提取最大位移和最大 Mises 应力。
   ```

4. The sidecar writes the active session id to `~/.abaqus_agent_session`.
5. In Abaqus/CAE, run `Plug-ins -> AbaqusAgent Copilot: Run Current Plan`.
   This executes approved actions until the queue is empty.
6. Click `刷新插件状态` in the sidecar to verify `completed_count` increases and
   `pending_count` reaches `0`.

For debugging, use `Plug-ins -> AbaqusAgent Copilot: Execute Next Action` to
run one action at a time, and `Plug-ins -> AbaqusAgent Copilot: Check Session
Status` to print completed/pending counts in the Abaqus message area.

## Plug-in Self-test Manifest

When interactive CAE screenshots are not available, the plug-in can still write
a runtime manifest from Abaqus Python/noGUI:

```python
import abaqusAgent_plugin
abaqusAgent_plugin.write_plugin_manifest("abaqus_agent_plugin_manifest.json")
```

The manifest lists the registered Copilot menu entries, active server URL,
session file, active session id, allowed action names, and default run action.

## Alpha Release Gate

Summarize the current evidence bundle without publishing anything:

```bash
abaqus-agent-copilot-alpha-release-gate --out-dir artifacts/copilot/release_gate
```

Expected current status:

```text
ALPHA_READY_WITH_GUI_BLOCKER
```

Use strict GUI mode for a release gate that must fail until an interactive
Abaqus/CAE screenshot or recording proves the Plug-ins menu path:

```bash
abaqus-agent-copilot-alpha-release-gate --strict-gui \
  --out-dir artifacts/copilot/release_gate_strict
```

## Alpha Package

Build a local ZIP containing the plug-in, install docs, release gate report, and
real Abaqus evidence:

```bash
abaqus-agent-copilot-alpha-package \
  --out-dir artifacts/copilot/alpha_package \
  --server-url http://<server-host>:8000
```

Verify the ZIP before sharing it with an Alpha tester:

```bash
abaqus-agent-copilot-verify-alpha-package \
  artifacts/copilot/alpha_package/abaqus-agent-copilot-alpha.zip
```

Verify the ZIP before handing it to a tester:

```bash
abaqus-agent-copilot-verify-alpha-package \
  artifacts/copilot/alpha_package/abaqus-agent-copilot-alpha.zip
```

The running sidecar also exposes the ZIP directly:

```text
GET /api/copilot/alpha-package.zip
```

For a remote workstation, set:

```bash
ABAQUS_AGENT_SERVER_URL=http://<server-host>:8000
```

Or edit `abaqus_agent_config.json` next to the plug-in:

```json
{
  "server_url": "http://<server-host>:8000",
  "session_id": ""
}
```

If needed, set a session manually:

```bash
echo copilot-xxxxxx > ~/.abaqus_agent_session
```

## Real Smoke

The reproducible remote smoke command is:

```bash
abaqus-agent-copilot-real-smoke \
  --backend codex_strict \
  --remote-host 10.0.0.10 \
  --remote-user ciuser \
  --remote-path D:/code/abaqus_agent \
  --proxy-command '/opt/homebrew/bin/tailscale --socket=/Users/owner/.tailscale/tailscaled.sock nc %h %p' \
  --out-dir artifacts/copilot/real_smoke_cli_codex
```

Latest verified result:

```json
{
  "job_name": "Cantilever_200mm_Static",
  "max_displacement": 0.12858134508132935,
  "max_mises": 9.57726764678955,
  "model": "Copilot_Cantilever",
  "status": "COMPLETED"
}
```
