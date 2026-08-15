"""
export_odb_animation_runner.py
------------------------------
Outer wrapper for post/export_odb_animation.py.

The exporter itself runs INSIDE Abaqus Python 2.7 via `abaqus cae noGUI=...`
and calls main() at module level, so it cannot be imported from Python 3 —
hence this separate runner (unlike export_odb_mesh.py, where inner and outer
layers share one file).

    export_odb_animation(odb_path, workdir) ->
        {"frames": N, "video": "anim.mp4"|None, "out_dir": str, "errors": [...]}

Best-effort: every failure lands in "errors"; this never raises. When frames
export successfully the runner stitches them into <workdir>/anim.mp4 so the
existing /api/run/{id}/artifact/anim.mp4 endpoint can serve it directly.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

FRAME_RATE = 20
FFMPEG_TIMEOUT = 180

# The packaged app no longer bundles ffmpeg (GPLv3, see THIRD_PARTY_NOTICES.md),
# so resolution can legitimately fail on user machines. Keep the hint readable:
# two self-install routes, no traceback.
FFMPEG_INSTALL_HINT = (
    "未找到 ffmpeg（本软件不内置），动画帧已保留但无法拼接为 mp4。"
    "两种解决方式任选其一："
    "① 安装系统 ffmpeg 并确保命令行能运行 `ffmpeg -version`"
    "（如 `winget install Gyan.FFmpeg`，或从 https://ffmpeg.org/download.html 下载后加入 PATH）；"
    "② 已有 ffmpeg.exe 时，把环境变量 IMAGEIO_FFMPEG_EXE 设为它的完整路径。"
)


def _ffmpeg_exe() -> str:
    """Resolve ffmpeg (IMAGEIO_FFMPEG_EXE > bundled > conda > system PATH);
    separate helper so tests can stub it."""
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as e:
        raise RuntimeError(FFMPEG_INSTALL_HINT) from e


def _stitch_video(out_dir: Path, workdir: Path, errors: list) -> str | None:
    """frame_%04d.png -> <workdir>/anim.mp4. Returns the filename or None."""
    try:
        ffmpeg = _ffmpeg_exe()
    except Exception as e:
        errors.append("ffmpeg unavailable, frames only: %s" % e)
        return None

    video_path = workdir / "anim.mp4"
    cmd = [
        ffmpeg, "-y",
        "-framerate", str(FRAME_RATE),
        "-i", str(out_dir / "frame_%04d.png"),
        # yuv420p requires even dimensions; trunc guards odd frame sizes
        "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
        "-pix_fmt", "yuv420p",
        str(video_path),
    ]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(workdir),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=FFMPEG_TIMEOUT,
        )
    except FileNotFoundError:
        errors.append("ffmpeg executable not found: %s" % ffmpeg)
        return None
    except subprocess.TimeoutExpired:
        errors.append("ffmpeg stitch timed out after %ss" % FFMPEG_TIMEOUT)
        return None
    except Exception as e:
        errors.append("ffmpeg stitch failed: %s" % e)
        return None

    if getattr(proc, "returncode", 1) == 0 and video_path.is_file():
        return video_path.name
    errors.append("ffmpeg stitch failed: %s"
                  % ((proc.stderr or proc.stdout or "no output")[-1500:]))
    return None


def export_odb_animation(odb_path, workdir=None, timeout=900):
    """Invoke 'abaqus cae noGUI' to export per-frame contour PNGs, then stitch
    them into anim.mp4 at the workdir root. Best-effort: returns
    {"frames": N, "video": str|None, "out_dir": str, "errors": [...]}."""
    odb_path = Path(odb_path).resolve()
    workdir = Path(workdir).resolve() if workdir else odb_path.parent
    out_dir = workdir / "anim"
    result = {"frames": 0, "video": None, "out_dir": str(out_dir), "errors": []}

    if not odb_path.exists():
        result["errors"].append("ODB not found: %s" % odb_path)
        return result

    inner_script = Path(__file__).resolve().parent / "export_odb_animation.py"
    from tools.abaqus_cmd import get_abaqus_cmd
    try:
        cmd = [get_abaqus_cmd(), "cae", "noGUI=%s" % inner_script]
    except Exception as e:
        result["errors"].append(str(e))
        return result

    env = os.environ.copy()
    env["ABQ_ANIM_ODB"] = str(odb_path)
    env["ABQ_ANIM_OUT"] = str(out_dir)

    try:
        proc = subprocess.run(
            cmd,
            cwd=str(workdir),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout,
            env=env,
        )
    except FileNotFoundError:
        result["errors"].append("'abaqus' not found in PATH")
        return result
    except subprocess.TimeoutExpired:
        result["errors"].append("animation export timed out after %ss" % timeout)
        return result
    except Exception as e:
        result["errors"].append("animation export failed: %s" % e)
        return result

    frames = sorted(out_dir.glob("frame_*.png")) if out_dir.is_dir() else []
    result["frames"] = len(frames)
    if not frames:
        result["errors"].append(
            (proc.stderr or proc.stdout or "no animation frames produced")[-1500:])
        return result

    result["video"] = _stitch_video(out_dir, workdir, result["errors"])
    return result
