"""
build_model.py
--------------
Tool: build_model(spec) -> {workdir, cae_path, inp_path}

Generates a CAE noGUI script from Problem Spec, executes it via
  abaqus cae noGUI=<script> -- <workdir> <spec_path>
and returns the paths to the resulting .cae and .inp files.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

from tools.errors import AbaqusAgentError, ErrorCode

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_model(spec_path: str | Path, workdir: str | Path | None = None) -> dict:
    """
    Build a model from a spec YAML file.

    Returns
    -------
    dict with keys:
        workdir   : Path  - run directory
        cae_path  : Path  - generated .cae file (may not exist for inp-only)
        inp_path  : Path  - generated .inp file
        run_id    : str   - reproducible hash of spec + abaqus_release
    """
    spec_path = Path(spec_path).resolve()
    spec = _load_spec(spec_path)

    run_id = _run_id(spec)
    if workdir:
        # Resolved, not just wrapped: _run_cae_nougui passes the script path to
        # `abaqus cae noGUI=` while running with cwd=workdir, so a relative
        # workdir is re-interpreted relative to itself and CAE reports "The
        # following file(s) could not be located" for a script that is sitting
        # right there. Hit while probing a selector mismatch through
        # `python runner/build_model.py <spec> <relative-dir>`.
        workdir = Path(workdir).resolve()
    else:
        # Default run root is spec-relative (cases/<case>/runs/) in dev. Packaged
        # mode redirects to the user data dir so runs never write into a
        # read-only install directory. Keep the redirect shallow — Abaqus
        # rejects input paths > 256 chars (see submit_job._build_cmd).
        from core import config
        root = config.run_root()
        workdir = (root / run_id) if root else spec_path.parent / "runs" / run_id
    workdir.mkdir(parents=True, exist_ok=True)

    inp_path = workdir / f"{spec['meta']['model_name']}.inp"

    # Reuse is allowed only on PROOF, never on file existence. run_id hashes
    # the spec alone, so "the .inp is already there" proves nothing about it
    # being the deck THIS build would produce: the source .inp of a custom_inp
    # spec can change under an unchanged path, the generator code can change,
    # the probed solver can change. Reproduced before this guard: edit a
    # custom_inp source 100N -> 900N, rerun, cached=True, and the solver ran
    # the 100N deck — COMPLETED, fresh timestamps, stale physics.
    is_custom = _is_deck(spec)
    fingerprint = _build_fingerprint(spec, spec_path, workdir)
    rebuild_reason = None
    if inp_path.exists() and inp_path.stat().st_size > 0:
        miss = _cache_verdict(workdir, inp_path, fingerprint)
        if miss is None:
            # Preview mesh may be missing on cached runs (e.g. cache predates
            # the feature) — regenerate from preview_raw.json without CAE.
            cached_mesh = _write_preview_mesh(workdir, inp_path)
            result = {
                "workdir": workdir,
                "cae_path": workdir / f"{spec['meta']['model_name']}.cae",
                "inp_path": inp_path,
                "run_id": run_id,
                "cached": True,
                "cache_reason": (
                    "构建指纹一致（spec / %s / 求解器版本均未变），复用既有 deck"
                    % ("源 .inp 内容" if is_custom else "生成器脚本")),
                "preview_mesh": cached_mesh.name if cached_mesh else None,
            }
            if is_custom:
                result["custom_inp"] = True
                result["source_inp_path"] = _resolve_custom_src(spec, spec_path)
            return result
        # Fail closed: anything unproven rebuilds.
        rebuild_reason = "重新生成 deck：%s" % miss

    if is_custom:
        result = _build_custom_inp(spec, spec_path, workdir, inp_path, run_id)
        _write_build_manifest(workdir, inp_path, fingerprint)
        if rebuild_reason:
            result["cache_reason"] = rebuild_reason
        return result

    # Generate the CAE noGUI script
    script_path = workdir / "build_model_script.py"
    _write_cae_script(spec, script_path, workdir, spec_path)

    # Execute: abaqus cae noGUI=script -- workdir spec_path
    _run_cae_nougui(script_path, workdir, spec["meta"]["abaqus_release"])

    cae_path = workdir / f"{spec['meta']['model_name']}.cae"
    if not inp_path.exists():
        why, snippet = _why_no_inp(workdir)
        raise AbaqusAgentError(
            ErrorCode.BUILD_FAILED,
            f".inp not generated after CAE run. {why}",
            log_snippet=snippet,
            workdir=str(workdir),
        )

    # Turn the CAE-side preview_raw.json dump into a WBViewport-compatible
    # mesh.json — this is what the workbench 3D preview reads while the user
    # is still iterating on the spec (no ODB needed).
    mesh_path = _write_preview_mesh(workdir, inp_path)

    # After the .inp, never before: a crash in between must leave a cache
    # miss, not a manifest vouching for a deck that was never written.
    _write_build_manifest(workdir, inp_path, fingerprint)

    result = {
        "workdir": workdir,
        "cae_path": cae_path,
        "inp_path": inp_path,
        "run_id": run_id,
        "cached": False,
        "preview_mesh": mesh_path.name if mesh_path else None,
    }
    if rebuild_reason:
        result["cache_reason"] = rebuild_reason
    return result


def _write_preview_mesh(workdir: Path, inp_path: Path | None = None) -> Path | None:
    """Turn the CAE-side dump (or, for custom_inp, the .inp itself) into a
    WBViewport-friendly mesh JSON. Best-effort — never raises.

    Two paths converge into the same output file (preview_mesh.json):
      1. preview_raw.json present (single-part CAE noGUI build) -> legacy
         single-mesh JSON with nodes/tris.
      2. Falls back to parsing inp_path directly -> multi-part JSON with
         parts=[{name, family, nodes, tris|lines, ...}]. Handles both
         custom_inp and any generated .inp with multiple ELSET blocks.
    """
    raw_path = workdir / "preview_raw.json"
    # Path 3 (v2 assemblies): CAE dumped every instance already positioned in
    # assembly space. Preferred over parsing the .inp because the transform is
    # read off the model rather than recomputed from *Instance data lines.
    if raw_path.exists():
        try:
            import json

            raw = json.loads(raw_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raw = None
        if isinstance(raw, dict) and raw.get("format") == "abaqus-agent-preview/instances":
            from post.parse_inp import parts_from_instance_dump
            out = workdir / "preview_mesh.json"
            data = parts_from_instance_dump(raw, source=str(inp_path or raw_path))
            out.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
            return out
    # Path 2: no CAE dump but we have an .inp — parse it into multi-part.
    if not raw_path.exists() and inp_path is not None and inp_path.exists():
        try:
            from post.parse_inp import write_parts_mesh
            out = workdir / "preview_mesh.json"
            write_parts_mesh(inp_path, out)
            return out
        except Exception as exc:
            # Best-effort stays best-effort (a broken preview must not fail a
            # build), but the reason must survive somewhere findable.
            import sys
            print("preview_mesh generation failed for %s: %s: %s"
                  % (inp_path, type(exc).__name__, exc), file=sys.stderr)
            return None
    if not raw_path.exists():
        return None
    try:
        import json

        from post.export_odb_mesh import build_surface

        raw = json.loads(raw_path.read_text(encoding="utf-8"))
        node_coords = {int(lbl): (x, y, z) for lbl, x, y, z in raw["nodes"]}
        elements = [(el_type, tuple(conn)) for el_type, conn in raw["elements"]]
        flat_nodes, flat_tris, _labels = build_surface(node_coords, elements)
        xs, ys, zs = flat_nodes[0::3], flat_nodes[1::3], flat_nodes[2::3]
        mesh = {
            "format": "abaqus-agent-mesh/1",
            "step": "preview",
            "is_modal": False,
            "mode": None,
            "frequency": None,
            "node_count": len(_labels),
            "tri_count": len(flat_tris) // 3,
            "nodes": flat_nodes,
            "tris": flat_tris,
            "fields": {},
            "displacement": [0.0] * (len(_labels) * 3),
            "bbox": [[min(xs), min(ys), min(zs)],
                     [max(xs), max(ys), max(zs)]] if xs else [[0, 0, 0], [0, 0, 0]],
        }
        out = workdir / "preview_mesh.json"
        out.write_text(json.dumps(mesh, separators=(",", ":")), encoding="utf-8")
        return out
    except Exception as _pv_e:
        # Preview is best-effort; don't fail the build. Log it so we can see
        # what went wrong from backend.err.log without wrapping every caller.
        import sys as _sys
        import traceback as _tb
        _sys.stderr.write("[_write_preview_mesh] %s\n" % _pv_e)
        _tb.print_exc(file=_sys.stderr)
        _sys.stderr.flush()
        return None


# ---------------------------------------------------------------------------
# CAE noGUI script writer
# ---------------------------------------------------------------------------

def _is_v2(spec: dict) -> bool:
    """True for the assembly dialect. `parts` is the discriminator the schema
    branches on, so nothing else may be used here or the two would disagree.

    Still asked, with one dialect left, because a `deck:` spec is not it: a deck
    describes no model, so there is nothing for the generator to compile and
    nothing for a caller to dry-build.
    """
    return "parts" in spec


def _write_cae_script(spec: dict, script_path: Path, workdir: Path,
                      spec_path: Path | None = None) -> None:
    if _is_v2(spec):
        from runner.build_v2 import generate_script
        # The spec's own directory is what a `{file:}` path is relative to --
        # the same rule a deck path already uses. None when the caller had no
        # spec on disk, which makes a relative path a refusal rather than a
        # guess.
        spec_dir = spec_path.parent if spec_path is not None else None
        script_path.write_text(generate_script(spec, spec_dir=spec_dir),
                               encoding="utf-8")
        return

    raise AbaqusAgentError(
        ErrorCode.BUILD_FAILED,
        "this spec is neither the assembly dialect (`parts:`) nor a finished "
        "deck (`deck: {file: ...}`), and the enumerated `geometry:` dialect it "
        "looks like was removed on 2026-08-16. Every shape it could name is "
        "expressible in `parts:` -- the seven cases that used to ship in it "
        "were ported and reproduce their baselines. See docs/ENV_TRUTH.md.")


def _why_no_inp(workdir: Path) -> tuple[str, str]:
    """Say what actually stopped the build, instead of naming a file to read.

    Three things are on disk and none of them was being looked at.

    A dispatched call can take the Abaqus kernel down: `FluidPipeSection` with a
    step-scoped region raises EXCEPTION_ACCESS_VIOLATION out of ABQcaeK.exe,
    which is not a Python exception, so the deck's own gates never run and
    selectors.log just stops. The launcher returns 0 either way, so the only
    signal is the missing .inp — and the old message for that was "check the
    log", with an empty snippet and a suggestion to simplify the geometry, which
    is advice for a different problem entirely.

    selectors.log's last line names the feature or condition that was being
    built when it stopped, which is the single most useful thing to say.
    """
    reasons: list[str] = []
    detail: list[str] = []

    log = workdir / "build_model_script.log"
    text = log.read_text(encoding="utf-8", errors="replace") if log.exists() else ""
    fort = workdir / "fort.7"
    kernel = fort.read_text(encoding="utf-8", errors="replace") if fort.exists() else ""
    if "EXCEPTION_ACCESS_VIOLATION" in text or "EXCEPTION_ACCESS_VIOLATION" in kernel:
        reasons.append(
            "the Abaqus kernel crashed (EXCEPTION_ACCESS_VIOLATION in "
            "ABQcaeK.exe). That is a crash inside Abaqus itself, not a bad "
            "spec value — no Python exception is raised and no gate in the "
            "generated deck can catch it")

    selectors = workdir / "selectors.log"
    if selectors.exists():
        lines = [ln.strip() for ln in
                 selectors.read_text(encoding="utf-8", errors="replace").splitlines()
                 if ln.strip()]
        if lines:
            detail.append("selectors.log stops after: %s" % lines[-1])
            reasons.append("it stopped while building %s"
                           % lines[-1].split(":", 1)[-1].strip()[:120])

    if text:
        errors = [ln.strip() for ln in text.splitlines()
                  if "Error" in ln or "error:" in ln]
        if errors:
            detail.append("abaqus said: %s" % errors[-1][:300])

    if not reasons:
        reasons.append("no kernel crash and no refusal in selectors.log, so "
                       "the deck ran to the end without writing the file")
    return ("; ".join(reasons) + ". Full output: %s" % log,
            "\n".join(detail)[-2000:])


def _run_cae_nougui(script_path: Path, workdir: Path, abaqus_release: str) -> None:
    """Execute abaqus cae noGUI=<script> and capture output."""
    log_path = workdir / "build_model_script.log"
    from tools.abaqus_cmd import get_abaqus_cmd
    cmd = [get_abaqus_cmd(), "cae", f"noGUI={script_path}", "--", str(workdir), "spec"]
    try:
        result = subprocess.run(
            cmd,
            cwd=str(workdir),
            capture_output=True,
            text=True, errors='replace', encoding='utf-8',
            # Without this the child inherits the MCP server's protocol pipe and
            # deadlocks on Windows.
            stdin=subprocess.DEVNULL,
            timeout=600,
        )
        log_path.write_text(result.stdout + "\n" + result.stderr, encoding="utf-8")
        if result.returncode != 0:
            raise AbaqusAgentError(
                ErrorCode.BUILD_FAILED,
                f"abaqus cae noGUI returned {result.returncode}. See {log_path}",
                log_snippet=result.stderr[-2000:],
                workdir=str(workdir),
            )
    except subprocess.TimeoutExpired:
        raise AbaqusAgentError(
            ErrorCode.TIMEOUT,
            "abaqus cae noGUI timed out after 600s",
            workdir=str(workdir),
        )
    except FileNotFoundError:
        raise AbaqusAgentError(
            ErrorCode.ABAQUS_NOT_FOUND,
            "'abaqus' executable not found. Check PATH and Abaqus installation.",
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_spec(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# Build identity: what the deck on disk actually depends on
# ---------------------------------------------------------------------------

MANIFEST_NAME = "build_manifest.json"


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _is_deck(spec: dict) -> bool:
    """True when the spec hands over a finished .inp instead of describing one.

    Spelled `deck: {file: ...}`. It used to be `geometry: {type: custom_inp,
    inp_path: ...}` -- a whole-deck passthrough filed under the key that named
    one of four built-in SHAPES, which dragged `analysis` and `bc_load` along as
    required siblings that nothing ever read, because the deck already contains
    its own steps and loads.
    """
    return "deck" in spec


def _resolve_custom_src(spec: dict, spec_path: Path) -> Path:
    raw = Path(spec["deck"]["file"])
    src = raw if raw.is_absolute() else Path(spec_path).parent / raw
    return src.resolve()


def _build_fingerprint(spec: dict, spec_path: Path, workdir: Path) -> dict:
    """Everything the deck depends on, hashed.

    Generator identity is the sha256 of the CAE script this generator emits
    for this spec — NOT a hash of this module's bytes. Comparing emitted
    script bytes catches exactly the code changes that would alter the deck,
    and does not invalidate every cache on a comment or a reformat. The
    script embeds the workdir path, so a moved run directory reads as a miss,
    which is the safe direction. For custom_inp the script is a constant
    placeholder; source_inp_sha256 carries the identity instead.
    """
    from tools.abaqus_cmd import detect_abaqus_release

    fingerprint = {
        "spec_sha256": hashlib.sha256(
            json.dumps(spec, sort_keys=True, default=str).encode()).hexdigest(),
        # Probed, not asserted — and None (no solver on this machine) is a
        # value like any other: it must match None to reuse.
        "abaqus_release_probed": detect_abaqus_release(),
    }
    if _is_deck(spec):
        src = _resolve_custom_src(spec, spec_path)
        fingerprint["source_inp_sha256"] = _sha256_file(src) if src.exists() else None
    else:
        import tempfile

        probe_dir = Path(tempfile.mkdtemp(prefix="abq_fp_probe_"))
        try:
            probe = probe_dir / "probe.py"
            _write_cae_script(spec, probe, workdir, spec_path)
            fingerprint["generator_script_sha256"] = _sha256_file(probe)
        finally:
            shutil.rmtree(probe_dir, ignore_errors=True)
        fingerprint["imported_files_sha256"] = _imported_files_sha256(
            spec, spec_path)
    return fingerprint


def _imported_files_sha256(spec: dict, spec_path: Path) -> dict | None:
    """Hash the CONTENTS of every file a `{file:}` in the spec points at.

    The generated script embeds the resolved path, not the bytes, so a geometry
    file edited in place leaves the script identical and the cache would hand
    back a deck built from the old shape. That is the custom_inp bug this
    module already documents at the top of `build_model` -- source edited
    100N -> 900N, rerun, cached=True, COMPLETED, stale physics -- and an
    `import:` reintroduces it with geometry instead of loads.

    None rather than {} when there is nothing to hash, so a spec that gains its
    first import reads as a miss rather than matching an old manifest.
    """
    if not _is_v2(spec):
        return None
    from runner.build_v2 import imported_files

    try:
        paths = imported_files(spec, spec_path.parent if spec_path else None)
    except Exception:
        # A path that cannot be resolved is a build-time refusal with a proper
        # message; here it just means there is nothing to vouch for.
        return None
    if not paths:
        return None
    return dict((path, _sha256_file(Path(path))) for path in sorted(paths))


def _write_build_manifest(workdir: Path, inp_path: Path, fingerprint: dict) -> None:
    manifest = dict(fingerprint)
    manifest["inp_sha256"] = _sha256_file(inp_path)
    (workdir / MANIFEST_NAME).write_text(
        json.dumps(manifest, indent=2), encoding="utf-8")


def _cache_verdict(workdir: Path, inp_path: Path, fresh: dict) -> str | None:
    """None = proven reuse. Otherwise the plain-Chinese reason to rebuild."""
    manifest_path = workdir / MANIFEST_NAME
    if not manifest_path.exists():
        return "该目录没有构建指纹（旧缓存或外来 deck），无法证明它对应当前 spec"
    try:
        stored = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "构建指纹文件损坏，无法证明缓存对应当前 spec"
    labels = {
        "spec_sha256": "spec 内容",
        "generator_script_sha256": "建模脚本生成器",
        "abaqus_release_probed": "检测到的 Abaqus 版本",
        "source_inp_sha256": "源 .inp 文件内容",
    }
    for key, label in labels.items():
        if (key in fresh or key in stored) and stored.get(key) != fresh.get(key):
            return "%s已变化" % label
    if stored.get("inp_sha256") != _sha256_file(inp_path):
        return "run 目录里的 .inp 与构建指纹不符（deck 被绕过本工具修改过）"
    return None


def _build_custom_inp(spec: dict, spec_path: Path, workdir: Path, inp_path: Path, run_id: str) -> dict:
    """Copy an existing .inp into the run directory without launching Abaqus/CAE."""
    src = _resolve_custom_src(spec, spec_path)
    if not src.exists():
        raise AbaqusAgentError(ErrorCode.FILE_NOT_FOUND, f"deck source not found: {src}")
    if src.suffix.lower() != ".inp":
        raise AbaqusAgentError(ErrorCode.BUILD_FAILED, f"a deck must be a .inp file: {src}")

    if src != inp_path.resolve():
        shutil.copyfile(src, inp_path)
    (workdir / "build_model_script.py").write_text(
        "# custom inp - no CAE script needed\n",
        encoding="utf-8",
    )

    # Same multi-part preview mesh the CAE path produces, so the workbench
    # 3D preview lights up on the first run — not only on cache-hit rebuilds.
    mesh_path = _write_preview_mesh(workdir, inp_path)

    return {
        "workdir": workdir,
        "cae_path": workdir / f"{spec['meta']['model_name']}.cae",
        "inp_path": inp_path,
        "source_inp_path": src,
        "run_id": run_id,
        "cached": False,
        "custom_inp": True,
        "preview_mesh": mesh_path.name if mesh_path else None,
    }


def _run_id(spec: dict) -> str:
    """Deterministic run ID from spec content + release.

    One definition, in core.helpers. This used to be a second copy of the
    hash, and core.helpers.make_run_id had drifted to hashing the raw YAML
    text instead -- so the id the API reported and the directory this creates
    were different strings for the same run.
    """
    from core.helpers import run_id_for_spec
    return run_id_for_spec(spec)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python build_model.py <spec.yaml> [workdir]")
        sys.exit(1)
    spec_file = sys.argv[1]
    wd = sys.argv[2] if len(sys.argv) > 2 else None
    result = build_model(spec_file, wd)
    print(json.dumps({k: str(v) for k, v in result.items()}, indent=2))
