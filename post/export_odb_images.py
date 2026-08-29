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
        _dress_viewport(session, viewport)
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


def _image_zoom():
    """How far past fitView to push. Conservative on purpose.

    fitView fits the bounding SPHERE, so how much margin is left depends on
    the model's shape: a long part lying diagonally leaves the corners empty
    and wants zoom, while a wide flat one already fills the frame and gets
    CROPPED by it. Measured both ways on the same value -- 1.35 framed the
    gear shaft well and cut the edges off the 3-storey blast frame. 1.15
    recovers some of the margin without clipping either, and the models that
    want more say so through the env var rather than through a default that
    is wrong for the other half of them.
    """
    try:
        return float(os.environ.get("ABAQUS_AGENT_IMAGE_ZOOM", "1.15"))
    except Exception:
        return 1.15


def _restrict_to_instances(viewport, plot):
    """`only: [names]` -- draw these part instances and nothing else.

    A close-up of a joint cannot be had by zooming: fitView frames the whole
    model, so zooming past it magnifies the middle of the beam, not the end
    of it. Showing only the parts the picture is about moves what fitView
    frames, which is the thing that actually needs to change.

    Instance names are upper-cased because that is how they reach the ODB;
    a spec that says `EndPlate` means the instance the assembly calls
    `ENDPLATE`, and failing on the case would be a puzzle with no clue in it.

    Absent, the whole model is restored -- one viewport serves every plot in
    the run, so a restriction left in place would silently crop the plots
    after it.
    """
    import displayGroupOdbToolset as dgo
    from abaqusConstants import DEFAULT_MODEL

    names = plot.get("only")
    try:
        if names:
            leaf = dgo.LeafFromPartInstance(
                partInstanceName=tuple(str(n).upper() for n in names))
        else:
            leaf = dgo.Leaf(leafType=DEFAULT_MODEL)
        viewport.odbDisplay.displayGroup.replace(leaf=leaf)
    except Exception as e:
        print("display group fallback: {}".format(e))


def _plot_zoom(plot):
    """How far past fitView THIS plot goes, if it says.

    One number for a whole run is right until a run wants both the assembly
    and a detail of one joint out of the same ODB: the assembly needs the
    margin and the detail needs to be close. A plot that says nothing keeps
    the run-wide value.
    """
    zoom = plot.get("zoom")
    if zoom is None:
        return _image_zoom()
    try:
        return float(zoom)
    except (TypeError, ValueError):
        return _image_zoom()


def _set_contour_limits(viewport, plot):
    """Pin the colour scale to `limits: [min, max]`, or leave it automatic.

    Auto-scaling is per picture, which makes two pictures of the same model
    incomparable and hides the field the plot is about. Measured on the
    bolted connection (2026-08-18): nominal bending in the beam is ~41 MPa
    and the peak at the constraint edge is 406, so on the automatic scale the
    entire beam sits in the bottom colour band and the picture says only
    "there is a hot spot at the joint" -- which is the one thing a reader can
    already see from the geometry.

    Values outside the range are not clipped away by this; Abaqus draws them
    in the end colours and the legend keeps saying what the range is, so the
    picture cannot claim a peak lower than the one in the file.

    A plot that states no limits RESTORES the automatic scale rather than
    leaving the previous plot's. One viewport serves every plot in a run, and
    measured on the bolted connection (2026-08-18) the joint close-up
    inherited the load-path plot's 0-120 and drew its own 406 MPa peak as a
    grey out-of-range band -- a picture of the wrong scale with a legend that
    looked right.
    """
    from abaqusConstants import OFF, ON

    limits = plot.get("limits")
    if limits:
        try:
            low, high = float(limits[0]), float(limits[1])
        except (TypeError, ValueError, IndexError) as e:
            print("contour limits ignored: {}".format(e))
            limits = None
    try:
        if limits:
            viewport.odbDisplay.contourOptions.setValues(
                minAutoCompute=OFF, minValue=low,
                maxAutoCompute=OFF, maxValue=high)
        else:
            viewport.odbDisplay.contourOptions.setValues(
                minAutoCompute=ON, maxAutoCompute=ON)
    except Exception as e:
        print("contour limits fallback: {}".format(e))


def _aim_camera(viewport, plot):
    """Point the camera where the plot asked, or leave CAE's default alone.

    There is no good global default and this function does not invent one:
    measured on two models the same day, a long shaft lying diagonally and a
    3-storey frame want opposite viewpoints, and the frame shown from the
    shaft's angle reads as a flat wall. So the spec says it when it matters
    and stays quiet when it does not.

    `view` is the vector FROM the model TO the camera, the same convention
    export_odb_animation.py uses, so a plot and its animation can share one
    number. `up` defaults to +Z.
    """
    view = plot.get("view")
    if not view:
        return
    if isinstance(view, str):
        try:
            view = [float(x) for x in view.split(",")]
        except Exception as e:
            print("view parse fallback: {}".format(e))
            return
    up = plot.get("up") or (0.0, 0.0, 1.0)
    try:
        viewport.view.setViewpoint(viewVector=tuple(view),
                                   cameraUpVector=tuple(up))
    except Exception as e:
        print("setViewpoint fallback: {}".format(e))


def _dress_viewport(session, viewport):
    """Strip the CAE chrome and render at a size worth looking at.

    Everything here already existed in export_odb_animation.py and was never
    taught to this path, which is the one every report and every screenshot
    actually uses. Measured on the round-4 gear shaft (2026-08-18), the
    untreated render was 660x490 and spent a quarter of its canvas on a boxed
    legend, with the ODB filename, the Abaqus release and a wall-clock
    timestamp burned across the bottom.

    What goes and why:
      * title      -- the ODB path, release and timestamp. Provenance belongs
                      in result.json where it can be read and diffed, not
                      rasterised into a picture. It is also the one piece of
                      Abaqus branding we put into our own output.
      * compass /  -- navigation aids for an interactive session. A still has
        triad         no navigation.
      * legendBox  -- the frame around the legend, not the legend. The numbers
                      stay; the box that crops the model shrinks away.

    The state block STAYS: step name, increment and step time are the answer
    to "which frame am I looking at", and a contour with no frame identity is
    the kind of picture that gets pasted into the wrong report.
    """
    from abaqusConstants import FEATURE, OFF, ON

    small = "-*-verdana-medium-r-normal-*-*-80-*-*-p-*-*-*"
    try:
        viewport.viewportAnnotationOptions.setValues(
            title=OFF, compass=OFF, triad=OFF, legend=ON, state=ON,
            legendFont=small, stateFont=small, legendBox=OFF,
        )
    except Exception as e:
        print("annotation options fallback: {}".format(e))

    # Feature edges, not every element edge. On a fine tet mesh the element
    # wireframe is dense enough to darken the whole part and to read as the
    # dominant object in the picture -- the question a contour answers is
    # where the field is high, and a mesh drawn over it competes with the
    # answer. Mesh density has its own view in the workbench, and the element
    # count is in the report next to the picture.
    try:
        viewport.odbDisplay.commonOptions.setValues(visibleEdges=FEATURE)
    except Exception as e:
        print("visibleEdges fallback: {}".format(e))

    # Beams as their actual sections, not as lines. Measured on the 3-storey
    # blast frame: without this the columns and beams draw as bare blue
    # wireframe, so a moment frame reads as two shell walls with stray lines
    # around them -- the structure the model is ABOUT is the part that does
    # not appear. The animation path has always had this.
    try:
        viewport.odbDisplay.basicOptions.setValues(renderBeamProfiles=ON)
    except Exception as e:
        print("renderBeamProfiles fallback: {}".format(e))

    # The picture and the report have to be about the same number. The
    # report's S_MISES_MAX is the UNAVERAGED element-nodal peak
    # (post/extract_kpis.py::_position_subset); CAE averages at nodes with a
    # 75% threshold before it draws, so the legend says something lower and
    # nothing on either says why. Measured on the round-5 bolted connection
    # (2026-08-18, scripts/probe_contour_averaging.py): averaged 406.34,
    # unaveraged 599.010, report 599.0099. A reader who spots the gap cannot
    # tell which of the two is the bug, and that doubt costs more than the
    # slightly blockier contour at the hot spot.
    #
    # The knob is on basicOptions. commonOptions has no such keyword and
    # answers "keyword error on averageElementOutput" -- inside a try, that
    # is a silent no-op, which is why it was measured rather than recalled.
    try:
        viewport.odbDisplay.basicOptions.setValues(averageElementOutput=OFF)
    except Exception as e:
        print("averageElementOutput fallback: {}".format(e))

    # 4:3, matching the viewport's own 180x135, so nothing is reframed --
    # this is a resolution change and not a crop. The default came out at
    # 660x490, which is soft on any screen bought this decade.
    size = os.environ.get("ABAQUS_AGENT_IMAGE_SIZE", "1600x1200")
    try:
        width, height = [int(n) for n in size.lower().split("x")]
    except Exception:
        width, height = 1600, 1200
    try:
        session.pngOptions.setValues(imageSize=(width, height))
    except Exception as e:
        print("pngOptions fallback: {}".format(e))


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
    _restrict_to_instances(viewport, plot)
    _set_contour_limits(viewport, plot)
    _aim_camera(viewport, plot)
    try:
        viewport.view.fitView()
        # fitView fits the model's bounding SPHERE, so a long part lying
        # diagonally leaves the corners empty -- measured on the round-4 gear
        # shaft, roughly half the canvas was margin. Zooming past the fit
        # trades that margin for pixels on the part. Kept modest because the
        # deformed shape can reach outside the undeformed bounds.
        viewport.view.zoom(_plot_zoom(plot))
    except Exception as e:
        print("framing fallback: {}".format(e))

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
