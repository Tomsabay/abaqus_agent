# AbaqusAgent CAE Copilot Plugin MVP

Copy `abaqusAgent_plugin.py` into the Abaqus/CAE plug-ins directory, start the
local FastAPI server, then run the plug-in from the Abaqus/CAE Plug-ins menu.

Menu entries:

- `AbaqusAgent Copilot: Open Sidecar` opens the local web Copilot.
- `AbaqusAgent Copilot: Run Current Plan` executes the full approved action
  queue for the active session.
- `AbaqusAgent Copilot: Execute Next Action` pulls and executes one approved
-  action from the Copilot session queue for step-by-step debugging.
- `AbaqusAgent Copilot: Check Session Status` prints completed/pending counts.

Configuration:

- `ABAQUS_AGENT_SERVER_URL`: Copilot server URL. Defaults to
  `http://127.0.0.1:8000`.
- `ABAQUS_AGENT_SESSION`: Copilot session id.
- Alternatively, place `abaqus_agent_config.json` next to
  `abaqusAgent_plugin.py`:

  ```json
  {
    "server_url": "http://127.0.0.1:8000",
    "session_id": ""
  }
  ```

- You can also write the session id into `~/.abaqus_agent_session`.

The MVP bridge polls a saved Copilot session and executes only the Abaqus Python
snippet returned by the server-side white-listed action protocol. It is intended
for local workstation use.
