"""
ccx_orchestrator.py
-------------------
CalculiXOrchestrator: the fallback pipeline, used when the machine has no Abaqus.

It subclasses AbaqusOrchestrator and swaps ONLY the four solver-bound stages
(build / syntaxcheck / submit+monitor / extract). Everything else — spec
validation, physics contracts, regression comparison, capsule persistence,
result.json — is inherited unchanged, so a CalculiX run lands in exactly the
same shapes the rest of the product already reads.

Three honesty rules are enforced here, not left to the UI:

  * A spec the verified subset cannot cover is REFUSED before anything runs,
    with the offending spec field named in plain Chinese.
  * The run directory is namespaced ``<run_id>-ccx``. run_id hashes the spec
    only (runner/build_model.py:879), so without this a CalculiX run and an
    Abaqus run of the same spec would share a directory and one would overwrite
    the other's frozen baseline.
  * A KPI whose definition is not Abaqus-equivalent (nodal-averaged stress) is
    tagged and EXCLUDED from the pass/fail regression verdict rather than
    graded against an Abaqus-frozen expected.json.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

import yaml

from agent.orchestrator import AbaqusOrchestrator
from core.backends import refusal_messages
from odb_lens import normalize_recipe
from post.extract_kpis_ccx import extract_kpis_ccx
from runner.ccx_deck import write_ccx_deck
from runner.ccx_solve import solve_ccx
from runner.ccx_whitelist import DeckRefused, assert_translatable
from runner.monitor_job import JobStatus
from tools.ccx_cmd import detect_ccx_version
from tools.errors import AbaqusAgentError, ErrorCode

SYNTAXCHECK_SKIP_REASON = (
    "CalculiX 没有 syntaxcheck 预检模式；卡片错误只在正式求解的读入阶段暴露，"
    "所以这一步跳过（不是通过）"
)
NO_VISUALS_REASON = (
    "CalculiX 不产生 .odb，因此这次运行没有云图 / 3D 结果动画；"
    "位移与应力数值来自 .dat / .frd"
)


class CalculiXOrchestrator(AbaqusOrchestrator):
    """Fallback pipeline driving user-installed CalculiX (ccx)."""

    def __init__(self, *args, decision=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.decision = decision
        self.deck_notes: list[str] = []
        self.result["backend"] = decision.as_dict() if decision else {"backend": "calculix"}
        self.result["kpi_provenance"] = {}
        self.result["limitations"] = []
        self._deck_refusal: list[str] | None = None

    def run(self) -> dict:
        """Both gates decline; both must therefore end the same way.

        The capability matrix reads the spec and refuses in ``_preflight``. The
        card-by-card whitelist reads the deck, which does not exist until the
        build stage, so its refusal travels as an exception through the shared
        run loop — which classifies every exception as FAILED. Same verdict,
        two labels: a refused deck would arrive with no ``kpi_notice`` saying
        why there are no numbers, and would read to a caller as a crash.
        """
        result = super().run()
        if self._deck_refusal is not None and result.get("status") == "FAILED":
            self._write_refusal(self._deck_refusal)
            self._save_refusal()
        return result

    # -- gates ---------------------------------------------------------------

    def _preflight(self) -> dict | None:
        """Refuse a spec the verified CalculiX subset cannot cover.

        This is a distinct outcome from demo mode: the user HAS a solver, it
        just cannot do this problem. Saying so beats pretending.
        """
        decision = self.decision
        if decision is None or decision.supported:
            self._record_caveats()
            return None

        reasons = refusal_messages(decision)
        # Reported on validate_spec, not a pseudo-stage: refusing is a verdict
        # on the spec, and the pipeline already marks that stage as the failure
        # site. Inventing a stage id would leave a chip spinning forever.
        self.on_progress("validate_spec", {
            "backend": decision.label,
            "refusals": reasons,
        })
        self.result["backend"] = decision.as_dict()
        self.result["limitations"] = [b.as_dict() for b in decision.blockers]
        self._write_refusal(reasons)
        self._save_refusal()
        return self.result

    def _write_refusal(self, reasons: list[str]) -> None:
        """The one shape a refusal takes, whichever gate produced it."""
        label = self.decision.label if self.decision else "CalculiX"
        self.result.update({
            "status": "REFUSED",
            "kpis": {},
            "kpi_notice": (
                "%s 无法忠实求解这个问题，因此没有输出任何数值 —— 近似糊弄比直接说不行更糟"
                % label
            ),
            "error": {
                "error_code": ErrorCode.BACKEND_UNSUPPORTED.value,
                "message": "；".join(reasons),
                "refusals": reasons,
            },
            "finished_at": datetime.now().isoformat(),
        })

    def _record_caveats(self) -> None:
        if self.decision is None:
            return
        self.result["limitations"] = [c.as_dict() for c in self.decision.caveats]
        for caveat in self.decision.caveats:
            self.on_progress("validate_spec", {"caveat": caveat.reason})

    def _is_parametric(self) -> bool:
        return False  # refused in _preflight; never silently swept

    # -- stages --------------------------------------------------------------

    def _run_id(self) -> str:
        """Spec hash + backend + solver version.

        Deliberately different from runner/build_model._run_id: mixing the
        backend in is what keeps a CalculiX run out of the Abaqus run's cache
        directory, where a frozen baseline lives.
        """
        payload = json.dumps(self.spec, sort_keys=True, default=str)
        version = detect_ccx_version() or "unknown"
        digest = hashlib.sha256(("%s|calculix|%s" % (payload, version)).encode()).hexdigest()
        return digest[:16] + "-ccx"

    def _stage_build(self) -> dict:
        self.on_progress("build_model", {})

        if not self.spec_path:
            if not self.workdir:
                import tempfile
                self.workdir = Path(tempfile.mkdtemp(prefix="ccx_run_"))
            Path(self.workdir).mkdir(parents=True, exist_ok=True)
            self.spec_path = Path(self.workdir) / "spec.yaml"
            self.spec_path.write_text(
                yaml.dump(self.spec, allow_unicode=True, default_flow_style=False),
                encoding="utf-8",
            )

        run_id = self._run_id()
        if self.workdir:
            workdir = Path(self.workdir)
        else:
            from core import config
            root = config.run_root()
            workdir = (root / run_id) if root else Path(self.spec_path).parent / "runs" / run_id
        workdir.mkdir(parents=True, exist_ok=True)

        kpi_spec = normalize_recipe(self.spec.get("outputs", {}).get("kpis", []))
        source_inp = self._source_inp()
        inp_path, notes = write_ccx_deck(self.spec, workdir, kpi_spec, source_inp=source_inp)
        self.deck_notes = notes

        # Refuse-before-run: ccx silently drops load cards it does not know and
        # still exits 0, so the deck is checked card by card BEFORE it is fed in.
        try:
            assert_translatable(inp_path.read_text(encoding="utf-8", errors="replace"))
        except DeckRefused as exc:
            self._deck_refusal = list(exc.reasons)
            raise AbaqusAgentError(
                # A refused card is not a geometry problem, and the remedy is
                # not the geometry list ErrorCode.UNSUPPORTED_GEOMETRY prints.
                # Same code as the capability-matrix refusal above, so both
                # classify identically in the UI.
                ErrorCode.BACKEND_UNSUPPORTED,
                "；".join(exc.reasons),
                workdir=str(workdir),
            )

        preview = None
        try:
            from post.parse_inp import write_parts_mesh
            write_parts_mesh(inp_path, workdir / "preview_mesh.json")
            preview = "preview_mesh.json"
        except Exception as exc:  # pragma: no cover - preview is best-effort
            # Non-fatal by design, but the reason must not evaporate.
            import sys
            print("preview_mesh generation failed for %s: %s: %s"
                  % (inp_path, type(exc).__name__, exc), file=sys.stderr)
            preview = None

        self.workdir = workdir
        result = {
            "workdir": workdir,
            "cae_path": None,
            "inp_path": inp_path,
            "run_id": run_id,
            "cached": False,
            "preview_mesh": preview,
        }
        if source_inp is not None:
            result["source_inp_path"] = source_inp
        self._build_result = result
        self.result["stages"]["build_model"] = {k: str(v) for k, v in result.items()}
        self.result["stages"]["build_model"]["notes"] = notes
        self.on_progress("build_model", {"inp": str(inp_path)})
        for note in notes:
            self.on_progress("build_model", {"deck": note})
        return result

    def _source_inp(self) -> Path | None:
        geo = self.spec.get("geometry", {}) or {}
        if geo.get("type") != "custom_inp":
            return None
        raw = Path(geo["inp_path"])
        src = raw if raw.is_absolute() else Path(self.spec_path).parent / raw
        src = src.resolve()
        if not src.exists():
            raise AbaqusAgentError(ErrorCode.FILE_NOT_FOUND, f"custom_inp source not found: {src}")
        return src

    def _stage_syntaxcheck(self, inp_path: Path, workdir: Path):
        """Report honestly that there is no pre-check, rather than a green tick."""
        self.result["stages"]["syntaxcheck"] = {
            "ok": None,
            "status": "skipped",
            "skipped": True,
            "reason": SYNTAXCHECK_SKIP_REASON,
            "errors": [],
            "warnings": [],
        }
        self.on_progress("syntaxcheck", {"skipped": SYNTAXCHECK_SKIP_REASON})

    def _stage_submit(self, inp_path: Path, workdir: Path) -> dict:
        self.on_progress("submit_job", {})
        result = solve_ccx(
            inp_path,
            workdir,
            timeout_seconds=self.runner_cfg["timeout_seconds"],
            cpus=self.runner_cfg.get("cpus", 1),
        )
        self.result["stages"]["submit_job"] = {k: str(v) for k, v in result.items()}
        self.on_progress("submit_job", {"status": result.get("status")})
        return result

    def _stage_monitor(self, submit_result: dict):
        """solve_ccx blocks until the solver exits, so there is nothing to poll."""
        self.result["stages"]["monitor_job"] = {"status": JobStatus.COMPLETED}
        self.on_progress("monitor_job", {"status": "completed"})

    def _stage_extract(self, odb_path: Path) -> dict:
        """odb_path is ignored — CalculiX writes .dat/.frd, never an .odb."""
        self.on_progress("extract_kpis", {})
        kpi_spec = normalize_recipe(self.spec.get("outputs", {}).get("kpis", []))
        self.result["odb_lens_recipe"] = kpi_spec
        job_stem = Path(self._build_result["inp_path"]).stem
        result = extract_kpis_ccx(job_stem, self.workdir, kpi_spec)
        self.result["stages"]["extract_kpis"] = result
        self.result["kpis"] = result.get("kpis", {})
        self.result["kpi_provenance"] = result.get("kpi_provenance", {})
        self._record_missing_kpis(kpi_spec, result)
        if result.get("errors"):
            self.on_progress("extract_kpis", {"warnings": result["errors"]})
        else:
            self.on_progress("extract_kpis", {"kpis": self.result["kpis"]})
        return result

    def _stage_export_visuals(self, odb_path: Path) -> dict:
        self.result["stages"]["export_odb_images"] = {
            "images": [], "errors": [], "skipped": True, "reason": NO_VISUALS_REASON,
        }
        self.result["visuals"] = []
        self.result["visuals_notice"] = NO_VISUALS_REASON
        self.on_progress("export_odb_images", {"skipped": NO_VISUALS_REASON})
        return {"images": [], "errors": []}

    def _stage_compare(self, actual_kpis: dict):
        """Grade only KPIs whose definition matches the Abaqus baseline.

        cases/*/expected.json is Abaqus-frozen. A nodal-averaged CalculiX stress
        graded against an unaveraged Abaqus stress is an apples-to-oranges
        PASS/FAIL, which is worse than no verdict at all.

        The EXPECTED set is narrowed too, not just the actual one — otherwise
        the excluded KPI comes back as "MISSING" and drags the whole run's
        verdict to FAIL, which is the same wrong answer wearing a different hat.
        """
        provenance = self.result.get("kpi_provenance", {})
        comparable = {
            name: value for name, value in actual_kpis.items()
            if provenance.get(name, {}).get("abaqus_equivalent", True)
        }
        skipped = [name for name in actual_kpis if name not in comparable]

        expected_all = self.expected or {}
        expected_kpis = expected_all.get("kpis", {})
        original_progress = self.on_progress
        self.expected = {
            **expected_all,
            "kpis": {k: v for k, v in expected_kpis.items() if k not in skipped},
        }
        # One corrected event instead of two contradictory ones.
        self.on_progress = lambda stage, data: None
        try:
            super()._stage_compare(comparable)
        finally:
            self.expected = expected_all
            self.on_progress = original_progress

        comparisons = self.result["regression"].setdefault("comparisons", {})
        for name in skipped:
            comparisons[name] = {
                "status": "NOT_COMPARABLE",
                "expected": expected_kpis.get(name, {}).get("value"),
                "actual": actual_kpis[name],
                "reason": provenance.get(name, {}).get(
                    "note", "该 KPI 的定义与 Abaqus 不同，不做达标判定"),
            }
        if skipped:
            self.result["regression"]["not_comparable"] = sorted(skipped)
        self.on_progress("compare_kpis", {
            "passed": self.result["regression"].get("passed"),
            "details": comparisons,
        })

    # -- persistence ---------------------------------------------------------

    def _capsule_metadata(self) -> dict:
        """Never let a CalculiX capsule inherit an Abaqus release string."""
        return {
            "status": self.result.get("status"),
            "solver_backend": "calculix",
            "solver_release": detect_ccx_version(),
            "abaqus_release": None,
        }

    def _save_refusal(self) -> None:
        """A refusal is archived like any other run, so the evidence survives."""
        if not self.workdir:
            import tempfile
            self.workdir = Path(tempfile.mkdtemp(prefix="ccx_refused_"))
        Path(self.workdir).mkdir(parents=True, exist_ok=True)
        self._save_result()
