"""
export_odb_animation.py
-----------------------
Export every ODB frame as a contour PNG so ffmpeg can stitch a slow-motion
animation. Runs INSIDE Abaqus Python (2.7):

  abaqus cae noGUI=post/export_odb_animation.py

Configured via environment variables (all optional except the ODB):
  ABQ_ANIM_ODB    absolute path to the .odb (required)
  ABQ_ANIM_OUT    output directory for frame_%04d.png (default: <odb dir>/anim)
  ABQ_ANIM_FIELD  primary variable (default "S"; e.g. "U" for displacement)
  ABQ_ANIM_INVAR  invariant name (default "Mises"; "Magnitude" for U)
  ABQ_ANIM_MAXS   fixed contour max in field units (default 500)
  ABQ_ANIM_SCALE  uniform deformation scale factor (default 8; shown in the
                  viewport state block, so the scaling is always disclosed)
  ABQ_ANIM_SIZE   image size WxH (default 1600x900)
  ABQ_ANIM_VIEW   camera vector "x,y,z" pointing from model to camera
                  (default "-0.55,-1.0,0.4", building front-left aerial)

Keeps the legend and state block visible: the state block carries step time
and the deformation scale factor, which is exactly the honesty we want in a
shareable animation. This file must stay Python 2.7 compatible.
"""

from __future__ import print_function

import json
import os


def _env(name, default=None):
    v = os.environ.get(name)
    return v if v else default


def main():
    odb_path = _env("ABQ_ANIM_ODB")
    if not odb_path or not os.path.exists(odb_path):
        raise RuntimeError("ABQ_ANIM_ODB not set or missing: %r" % odb_path)
    out_dir = _env("ABQ_ANIM_OUT", os.path.join(os.path.dirname(odb_path), "anim"))
    max_s = float(_env("ABQ_ANIM_MAXS", "500"))
    def_scale = float(_env("ABQ_ANIM_SCALE", "8"))
    size = _env("ABQ_ANIM_SIZE", "1600x900").lower().split("x")
    img_w, img_h = int(size[0]), int(size[1])
    view_vec = tuple(float(x) for x in _env("ABQ_ANIM_VIEW", "-0.55,-1.0,0.4").split(","))
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)

    field = _env("ABQ_ANIM_FIELD", "S").upper()
    invariant = _env("ABQ_ANIM_INVAR", "Mises")

    import visualization
    from abaqus import session
    from abaqusConstants import (
        CONTOURS_ON_DEF,
        INTEGRATION_POINT,
        INVARIANT,
        NODAL,
        OFF,
        ON,
        PNG,
        UNIFORM,
    )

    odb = visualization.openOdb(path=odb_path)
    # 180mm is the practical viewport width cap; 16:9 to match the PNG size
    vp = session.Viewport(name="AnimViewport", origin=(0, 0), width=180, height=101.25)
    vp.setValues(displayedObject=odb)

    vp.odbDisplay.display.setValues(plotState=(CONTOURS_ON_DEF,))
    position = NODAL if field in ("U", "V", "A", "RF") else INTEGRATION_POINT
    vp.odbDisplay.setPrimaryVariable(
        variableLabel=field,
        outputPosition=position,
        refinement=(INVARIANT, invariant),
    )
    vp.odbDisplay.commonOptions.setValues(
        deformationScaling=UNIFORM,
        uniformScaleFactor=def_scale,
    )
    vp.odbDisplay.basicOptions.setValues(renderBeamProfiles=ON)
    vp.odbDisplay.contourOptions.setValues(
        maxAutoCompute=OFF, maxValue=max_s,
        minAutoCompute=OFF, minValue=0.0,
    )
    small = "-*-verdana-medium-r-normal-*-*-80-*-*-p-*-*-*"
    vp.viewportAnnotationOptions.setValues(
        title=OFF, compass=OFF, triad=OFF, legend=ON, state=ON,
        legendFont=small, stateFont=small, legendBox=OFF,
    )
    try:
        # Lift the state block so the deformation-scale line is never clipped
        vp.viewportAnnotationOptions.setValues(statePosition=(30, 14))
    except Exception as e:
        print("statePosition fallback: %s" % e)

    step_name = list(odb.steps.keys())[-1]
    frames = odb.steps[step_name].frames
    n = len(frames)

    # Frame the camera once, then keep it fixed for every frame.
    fit_spec = _env("ABQ_ANIM_FIT_FRAME", "last")
    fit_idx = n - 1 if fit_spec == "last" else int(fit_spec)
    zoom = float(_env("ABQ_ANIM_ZOOM", "0.92"))
    vp.odbDisplay.setFrame(step=len(odb.steps) - 1, frame=fit_idx)
    try:
        vp.view.setViewpoint(viewVector=view_vec, cameraUpVector=(0, 0, 1))
    except Exception as e:
        print("viewpoint fallback: %s" % e)
    vp.view.fitView()
    vp.view.zoom(zoom)

    session.printOptions.setValues(vpDecorations=OFF)
    session.pngOptions.setValues(imageSize=(img_w, img_h))

    written = []
    for i in range(n):
        vp.odbDisplay.setFrame(step=len(odb.steps) - 1, frame=i)
        base = os.path.join(out_dir, "frame_%04d" % i)
        session.printToFile(fileName=base, format=PNG, canvasObjects=(vp,))
        written.append(base + ".png")

    odb.close()
    manifest = {
        "odb": odb_path,
        "frames": len(written),
        "out_dir": out_dir,
        "field": field,
        "invariant": invariant,
        "contour_max": max_s,
        "deformation_scale": def_scale,
        "image_size": [img_w, img_h],
        "step": step_name,
    }
    with open(os.path.join(out_dir, "anim_manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)
    print("ANIM_EXPORT_DONE: %d frames -> %s" % (len(written), out_dir))


main()
