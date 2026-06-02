"""
export_odb_images.py
--------------------
Export ODB contour images through Abaqus/CAE noGUI.

The outer API runs in normal Python. The inner script runs inside Abaqus Python,
so this file intentionally avoids Python 3-only syntax.
"""

from __future__ import print_function

import json
import os
import sys

try:
    from pathlib import Path
except ImportError:
    Path = None


def export_odb_images(odb_path, plot_specs, workdir=None, timeout=300):
    """Invoke Abaqus/CAE noGUI to export contour PNGs from an ODB."""
    import subprocess

    if not plot_specs:
        return {"images": [], "errors": [], "odb_path": str(odb_path)}

    odb_path = Path(odb_path).resolve()
    workdir = Path(workdir) if workdir else odb_path.parent
    if not odb_path.exists():
        return {"images": [], "errors": ["ODB not found: {}".format(odb_path)], "odb_path": str(odb_path)}

    spec_file = workdir / "_odb_plot_spec.json"
    spec_file.write_text(json.dumps(plot_specs, indent=2), encoding="utf-8")
    result_file = workdir / "_odb_plot_result.json"
    this_script = Path(__file__).resolve()

    from tools.abaqus_cmd import get_abaqus_cmd
    cmd = [get_abaqus_cmd(), "cae", "noGUI={}".format(this_script)]
    env = os.environ.copy()
    env.update({
        "ABAQUS_AGENT_ODB_PATH": str(odb_path),
        "ABAQUS_AGENT_PLOT_SPEC": str(spec_file),
        "ABAQUS_AGENT_PLOT_RESULT": str(result_file),
    })

    try:
        proc = subprocess.run(
            cmd,
            cwd=str(workdir),
            capture_output=True,
            text=True,
            errors="replace",
            encoding="utf-8",
            timeout=timeout,
            env=env,
        )
    except FileNotFoundError:
        return {"images": [], "errors": ["'abaqus' not found in PATH"], "odb_path": str(odb_path)}
    except subprocess.TimeoutExpired:
        return {"images": [], "errors": ["ODB image export timed out after {}s".format(timeout)], "odb_path": str(odb_path)}

    if result_file.exists():
        try:
            return json.loads(result_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass

    return {
        "images": [],
        "errors": [proc.stderr[-2000:] or proc.stdout[-2000:] or "No image export result file produced"],
        "odb_path": str(odb_path),
    }


def _inner_main():
    env_args = [
        os.environ.get("ABAQUS_AGENT_ODB_PATH"),
        os.environ.get("ABAQUS_AGENT_PLOT_SPEC"),
        os.environ.get("ABAQUS_AGENT_PLOT_RESULT"),
    ]
    if all(env_args):
        args = env_args
    else:
        args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]

    if len(args) < 3:
        print("Usage: abaqus cae noGUI=export_odb_images.py -- <odb> <plot_spec.json> <result.json>")
        sys.exit(1)

    odb_path = args[0]
    spec_path = args[1]
    result_path = args[2]
    with open(spec_path, "r") as f:
        plot_specs = json.load(f)

    result = {"images": [], "errors": [], "odb_path": odb_path}
    try:
        import visualization
        from abaqus import session

        odb = visualization.openOdb(path=odb_path)
        viewport = session.Viewport(name="AbaqusAgentViewport", origin=(0, 0), width=180, height=135)
        viewport.setValues(displayedObject=odb)
        try:
            viewport.view.fitView()
        except Exception:
            pass

        for plot in plot_specs:
            try:
                image = _export_single_plot(session, viewport, plot, result_path)
                result["images"].append(image)
            except Exception as e:
                result["errors"].append("{}: {}".format(plot.get("name", "odb_plot"), str(e)))

        odb.close()
    except ImportError:
        result["errors"].append("Abaqus visualization modules not available - run via 'abaqus cae noGUI'")
    except Exception as e:
        result["errors"].append("ODB image export failed: {}".format(str(e)))

    with open(result_path, "w") as f:
        json.dump(result, f, indent=2, default=lambda o: float(o) if hasattr(o, "__float__") else str(o))

    print("ODB_IMAGE_RESULT_WRITTEN: " + result_path)


def _export_single_plot(session, viewport, plot, result_path):
    from abaqusConstants import (
        COMPONENT,
        CONTOURS_ON_DEF,
        CONTOURS_ON_UNDEF,
        INTEGRATION_POINT,
        INVARIANT,
        NODAL,
        OFF,
        PNG,
    )

    name = _safe_name(plot.get("name") or "odb_plot")
    field = str(plot.get("field_variable") or plot.get("field") or "S").upper()
    output_position = NODAL if field in ("U", "RF") else INTEGRATION_POINT
    plot_state = CONTOURS_ON_DEF if plot.get("deformed") else CONTOURS_ON_UNDEF
    viewport.odbDisplay.display.setValues(plotState=(plot_state,))

    if plot.get("invariant"):
        viewport.odbDisplay.setPrimaryVariable(
            variableLabel=field,
            outputPosition=output_position,
            refinement=(INVARIANT, _abaqus_invariant_name(plot["invariant"])),
        )
    elif plot.get("component"):
        viewport.odbDisplay.setPrimaryVariable(
            variableLabel=field,
            outputPosition=output_position,
            refinement=(COMPONENT, str(plot["component"]).upper()),
        )
    else:
        viewport.odbDisplay.setPrimaryVariable(variableLabel=field, outputPosition=output_position)

    _set_frame(viewport, plot.get("frame", "last"))
    try:
        viewport.view.fitView()
    except Exception:
        pass

    out_dir = os.path.dirname(result_path)
    file_base = os.path.join(out_dir, name)
    try:
        session.printOptions.setValues(vpDecorations=OFF)
    except Exception:
        pass
    session.printToFile(fileName=file_base, format=PNG, canvasObjects=(viewport,))

    image_path = file_base + ".png"
    return {
        "name": name,
        "path": os.path.basename(image_path),
        "bytes": os.path.getsize(image_path) if os.path.exists(image_path) else 0,
        "field_variable": field,
        "invariant": plot.get("invariant"),
        "component": plot.get("component"),
    }


def _set_frame(viewport, frame_spec):
    try:
        odb = viewport.displayedObject
        step_names = list(odb.steps.keys())
        if not step_names:
            return
        step_idx = len(step_names) - 1
        frames = odb.steps[step_names[step_idx]].frames
        if frame_spec == "last":
            frame_idx = len(frames) - 1
        else:
            frame_idx = int(frame_spec)
        viewport.odbDisplay.setFrame(step=step_idx, frame=frame_idx)
    except Exception:
        pass


def _abaqus_invariant_name(value):
    invariant = str(value).upper()
    if invariant == "MISES":
        return "Mises"
    if invariant == "MAGNITUDE":
        return "Magnitude"
    return str(value)


def _safe_name(value):
    raw = str(value).strip() or "odb_plot"
    return "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in raw)


if __name__ == "__main__":
    _inner_main()
