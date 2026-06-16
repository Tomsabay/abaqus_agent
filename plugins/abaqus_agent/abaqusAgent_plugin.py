"""Abaqus/CAE plug-in bridge for AbaqusAgent Copilot MVP.

Install this file in the Abaqus/CAE plug-ins directory. It intentionally keeps
the first version small: the user enters a local Copilot session id, then the
plug-in pulls one approved action at a time from the FastAPI server.
"""

from __future__ import print_function

import json
import os
import webbrowser

try:
    import urllib2
except ImportError:  # pragma: no cover - Abaqus Python 3
    import urllib.request as urllib2

try:
    from abaqusGui import AFXForm, AFXGuiCommand, getAFXApp
except Exception:  # pragma: no cover - imported only inside Abaqus/CAE
    AFXForm = object
    AFXGuiCommand = None
    getAFXApp = None

PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILENAMES = [
    os.path.join(PLUGIN_DIR, "abaqus_agent_config.json"),
    os.path.expanduser("~/.abaqus_agent_config.json"),
]
SESSION_FILE = os.path.expanduser("~/.abaqus_agent_session")
CONFIG = {}


def _load_config():
    for path in CONFIG_FILENAMES:
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    return json.load(f)
            except Exception as exc:
                print("AbaqusAgent: ignored invalid config %s: %s" % (path, exc))
    return {}


CONFIG = _load_config()
SERVER_URL = (
    os.environ.get("ABAQUS_AGENT_SERVER_URL")
    or CONFIG.get("server_url")
    or "http://127.0.0.1:8000"
).rstrip("/")
ALLOWED_ACTIONS = set(
    [
        "create_cantilever_model",
        "apply_boundary_condition",
        "submit_job_or_prepare_run",
    ]
)
PLUGIN_MENU_ENTRIES = [
    "AbaqusAgent Copilot: Open Sidecar",
    "AbaqusAgent Copilot: Run Current Plan",
    "AbaqusAgent Copilot: Execute Next Action",
    "AbaqusAgent Copilot: Check Session Status",
]


def _get_json(url):
    raw = urllib2.urlopen(url, timeout=10).read()
    if not isinstance(raw, str):
        raw = raw.decode("utf-8")
    return json.loads(raw)


def _post_json(url, payload):
    data = json.dumps(payload).encode("utf-8")
    req = urllib2.Request(url, data, {"Content-Type": "application/json"})
    raw = urllib2.urlopen(req, timeout=10).read()
    if not isinstance(raw, str):
        raw = raw.decode("utf-8")
    return json.loads(raw)


def execute_next_copilot_action(session_id):
    """Pull and execute one server-approved Copilot action."""
    data = _get_json(
        "%s/api/copilot/sessions/%s/next-action" % (SERVER_URL, session_id)
    )
    action = data.get("action")
    if not action:
        print("AbaqusAgent: no pending Copilot actions")
        return {"status": "empty", "session_id": session_id}
    action_name = action.get("action")
    if action_name not in ALLOWED_ACTIONS:
        raise RuntimeError("Blocked unsupported Copilot action: %s" % action_name)
    script = action.get("abaqus_python") or ""
    if not script.strip():
        raise RuntimeError("Copilot action did not include Abaqus Python")
    exec(script, globals(), globals())
    _post_json(
        "%s/api/copilot/sessions/%s/action-result" % (SERVER_URL, session_id),
        {
            "action_index": data.get("action_index", 0),
            "status": "completed",
            "message": "Executed inside Abaqus/CAE",
            "payload": {"action": action_name},
        },
    )
    print("AbaqusAgent: executed %s" % action_name)
    return {
        "status": "completed",
        "session_id": session_id,
        "action": action_name,
        "action_index": data.get("action_index", 0),
    }


def _read_session_id():
    session_id = os.environ.get("ABAQUS_AGENT_SESSION", "").strip()
    if not session_id:
        session_id = str(CONFIG.get("session_id") or "").strip()
    if not session_id and os.path.exists(SESSION_FILE):
        with open(SESSION_FILE, "r") as f:
            session_id = f.read().strip()
    return session_id


def get_plugin_manifest():
    """Return a small self-test manifest for CAE/noGUI validation."""
    return {
        "plugin": "AbaqusAgent CAE Copilot",
        "server_url": SERVER_URL,
        "config_files": CONFIG_FILENAMES,
        "config": CONFIG,
        "session_file": SESSION_FILE,
        "session_id": _read_session_id(),
        "menu_entries": PLUGIN_MENU_ENTRIES,
        "allowed_actions": sorted(ALLOWED_ACTIONS),
        "default_action": "AbaqusAgent Copilot: Run Current Plan",
        "debug_action": "AbaqusAgent Copilot: Execute Next Action",
    }


def write_plugin_manifest(path="abaqus_agent_plugin_manifest.json"):
    """Write plugin self-test metadata from inside Abaqus Python."""
    manifest = get_plugin_manifest()
    with open(path, "w") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
    print("AbaqusAgent: wrote plugin manifest %s" % path)
    return manifest


def execute_next_copilot_action_from_env():
    session_id = _read_session_id()
    if not session_id:
        raise RuntimeError(
            "Set ABAQUS_AGENT_SESSION or write the Copilot session id to %s "
            "before running the AbaqusAgent plug-in action." % SESSION_FILE
        )
    return execute_next_copilot_action(session_id)


def inspect_copilot_session(session_id):
    """Print the active Copilot session status inside the Abaqus message area."""
    data = _get_json("%s/api/copilot/sessions/%s" % (SERVER_URL, session_id))
    print(
        "AbaqusAgent: session %s, completed %s/%s, pending %s"
        % (
            data.get("session_id"),
            data.get("completed_count"),
            data.get("action_count"),
            data.get("pending_count"),
        )
    )
    return data


def inspect_copilot_session_from_env():
    session_id = _read_session_id()
    if not session_id:
        raise RuntimeError(
            "Set ABAQUS_AGENT_SESSION or write the Copilot session id to %s "
            "before checking the AbaqusAgent session." % SESSION_FILE
        )
    return inspect_copilot_session(session_id)


def execute_all_copilot_actions(session_id, max_steps=20):
    """Run approved Copilot actions until the queue is empty."""
    executed = []
    for _ in range(max_steps):
        result = execute_next_copilot_action(session_id)
        if not result or result.get("status") == "empty":
            summary = inspect_copilot_session(session_id)
            print(
                "AbaqusAgent: finished current Copilot plan; completed %s/%s"
                % (summary.get("completed_count"), summary.get("action_count"))
            )
            return {
                "status": "completed",
                "session_id": session_id,
                "executed": executed,
                "summary": summary,
            }
        executed.append(result)
    raise RuntimeError(
        "Stopped after %s Copilot actions to avoid an infinite execution loop." % max_steps
    )


def execute_all_copilot_actions_from_env():
    session_id = _read_session_id()
    if not session_id:
        raise RuntimeError(
            "Set ABAQUS_AGENT_SESSION or write the Copilot session id to %s "
            "before running the AbaqusAgent plug-in plan." % SESSION_FILE
        )
    return execute_all_copilot_actions(session_id)


def open_copilot_sidecar():
    """Open the local Copilot web sidecar from Abaqus/CAE."""
    webbrowser.open(SERVER_URL)
    print("AbaqusAgent: opened Copilot sidecar %s" % SERVER_URL)


class AbaqusAgentCopilotForm(AFXForm):  # pragma: no cover - Abaqus GUI only
    def __init__(self, owner):
        AFXForm.__init__(self, owner)
        self.cmd = AFXGuiCommand(
            mode=self,
            method="execute_next_copilot_action_from_env",
            objectName=__name__,
            registerQuery=False,
        )


class AbaqusAgentOpenSidecarForm(AFXForm):  # pragma: no cover - Abaqus GUI only
    def __init__(self, owner):
        AFXForm.__init__(self, owner)
        self.cmd = AFXGuiCommand(
            mode=self,
            method="open_copilot_sidecar",
            objectName=__name__,
            registerQuery=False,
        )


class AbaqusAgentRunPlanForm(AFXForm):  # pragma: no cover - Abaqus GUI only
    def __init__(self, owner):
        AFXForm.__init__(self, owner)
        self.cmd = AFXGuiCommand(
            mode=self,
            method="execute_all_copilot_actions_from_env",
            objectName=__name__,
            registerQuery=False,
        )


class AbaqusAgentStatusForm(AFXForm):  # pragma: no cover - Abaqus GUI only
    def __init__(self, owner):
        AFXForm.__init__(self, owner)
        self.cmd = AFXGuiCommand(
            mode=self,
            method="inspect_copilot_session_from_env",
            objectName=__name__,
            registerQuery=False,
        )


def registerPlugin():  # pragma: no cover - Abaqus GUI only
    if getAFXApp is None:
        return
    toolset = getAFXApp().getAFXMainWindow().getPluginToolset()
    toolset.registerGuiMenuButton(
        buttonText="AbaqusAgent Copilot: Open Sidecar",
        object=AbaqusAgentOpenSidecarForm(toolset),
        messageId=0,
        icon=None,
        kernelInitString="import abaqusAgent_plugin",
        applicableModules="All",
        version="0.1",
        author="AbaqusAgent",
        description="Open the local AbaqusAgent Copilot sidecar.",
        helpUrl="",
    )
    toolset.registerGuiMenuButton(
        buttonText="AbaqusAgent Copilot: Run Current Plan",
        object=AbaqusAgentRunPlanForm(toolset),
        messageId=0,
        icon=None,
        kernelInitString="import abaqusAgent_plugin",
        applicableModules="All",
        version="0.1",
        author="AbaqusAgent",
        description="Execute the full approved Copilot action queue.",
        helpUrl="",
    )
    toolset.registerGuiMenuButton(
        buttonText="AbaqusAgent Copilot: Execute Next Action",
        object=AbaqusAgentCopilotForm(toolset),
        messageId=0,
        icon=None,
        kernelInitString="import abaqusAgent_plugin",
        applicableModules="All",
        version="0.1",
        author="AbaqusAgent",
        description="Execute one approved Copilot action from the local server.",
        helpUrl="",
    )
    toolset.registerGuiMenuButton(
        buttonText="AbaqusAgent Copilot: Check Session Status",
        object=AbaqusAgentStatusForm(toolset),
        messageId=0,
        icon=None,
        kernelInitString="import abaqusAgent_plugin",
        applicableModules="All",
        version="0.1",
        author="AbaqusAgent",
        description="Print the active Copilot session progress.",
        helpUrl="",
    )


registerPlugin()
