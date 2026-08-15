"""
orchestrator.py
---------------
AbaqusOrchestrator: end-to-end pipeline controller.

Pipeline stages:
  1. validate_spec    - schema + structural checks
  2. build_model      - CAE noGUI → .inp
  3. syntaxcheck      - pre-solver syntaxcheck gate
  4. submit_job       - analysis execution
  5. monitor_job      - poll until completion
  6. extract_kpis     - ODB → KPI dict
  7. compare_expected - compare against expected.json (if provided)

All stages return structured dicts. Failures raise AbaqusAgentError
with an ErrorCode and a suggested fix.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Callable

import yaml

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from capsule.store import create_capsule, hash_file, write_capsule
from contracts import evaluate_contracts
from doctor import diagnose_logs
from odb_lens import missing_kpis, normalize_plots, normalize_recipe
from post.export_odb_animation_runner import export_odb_animation
from post.export_odb_images import export_odb_images
from post.export_odb_mesh import export_odb_mesh
from post.extract_kpis import extract_kpis
from runner.build_model import build_model
from runner.monitor_job import JobStatus, monitor_job
from runner.submit_job import submit_job
from runner.syntaxcheck import syntaxcheck_inp
from tools.errors import AbaqusAgentError, ErrorCode
from tools.schema_validator import validate_spec


def _sta_tail(job_name: str, workdir: Path, lines: int = 3) -> str:
    """Last few .sta lines — the solver's own verdict, quoted verbatim."""
    sta = Path(workdir) / ("%s.sta" % job_name)
    if not sta.is_file():
        return "（无 %s.sta）" % job_name
    try:
        text = sta.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return "（读不到 %s.sta: %s）" % (job_name, exc)
    tail = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
    return " / ".join(tail[-lines:]) or "（.sta 为空）"


class AbaqusOrchestrator:
    """
    Orchestrates the full Abaqus agent pipeline.

    Parameters
    ----------
    spec_path       : Path to spec.yaml (or None if spec_dict provided)
    workdir         : Override working directory
    expected_path   : Path to expected.json for regression comparison
    contracts_path  : Path to physics contracts YAML for QA checks
    runner_cfg_path : Path to runner.json (cpus, timeout, etc.)
    on_progress     : Optional callback(stage: str, data: dict)
    spec_dict       : Spec dict directly (alternative to spec_path)
    runner_cfg      : Runner config dict directly (alternative to runner_cfg_path)
    """

    def __init__(
        self,
        spec_path: str | Path | None = None,
        workdir: str | Path | None = None,
        expected_path: str | Path | None = None,
        contracts_path: str | Path | None = None,
        runner_cfg_path: str | Path | None = None,
        on_progress: Callable[[str, dict], None] | None = None,
        spec_dict: dict | None = None,
        runner_cfg: dict | None = None,
        contracts: list[dict] | dict | None = None,
    ):
        if spec_dict:
            self.spec = spec_dict
            self.spec_path = None
        elif spec_path:
            self.spec_path = Path(spec_path).resolve()
            with open(self.spec_path, encoding="utf-8") as f:
                self.spec = yaml.safe_load(f)
        else:
            raise ValueError("Either spec_path or spec_dict must be provided")

        # Library materials are expanded here, before validation and before the
        # run id is taken, so the rest of the pipeline never sees a `library:`
        # key: the schema checks real numbers, the generator emits the same deck
        # a hand-written block would, and the run id changes if the library data
        # ever does. Provenance is kept for the report -- the CC-BY cards this
        # ships with require attribution, and a number whose source is not
        # recorded is a number nobody can check.
        from core.material_library import resolve_spec_materials
        self.spec, self.material_provenance = resolve_spec_materials(self.spec)

        self.workdir      = Path(workdir) if workdir else None
        self.on_progress  = on_progress or (lambda s, d: None)

        # Load runner config (with defaults)
        self.runner_cfg = {
            "cpus": 1,
            "mp_mode": "threads",
            "memory": "90%",
            "timeout_seconds": 1800,
            "allow_license_queue": False,
            "syntaxcheck_first": True,
        }
        if runner_cfg:
            self.runner_cfg.update(runner_cfg)
        elif runner_cfg_path:
            with open(runner_cfg_path, encoding="utf-8") as f:
                self.runner_cfg.update(json.load(f))

        # Load expected KPIs
        self.expected: dict | None = None
        if expected_path and Path(expected_path).exists():
            with open(expected_path, encoding="utf-8") as f:
                self.expected = json.load(f)

        self.contracts = self._load_contracts(contracts_path, contracts)

        # Pipeline result accumulator
        self.result: dict = {
            "spec_path": str(self.spec_path) if self.spec_path else None,
            "started_at": datetime.now().isoformat(),
            "stages": {},
            "kpis": {},
            "regression": {},
            "contracts": {},
            "status": "PENDING",
        }
        if self.material_provenance:
            # Rides in the result rather than a side file so it reaches every
            # consumer that already reads it -- the CLI json, the run record and
            # the report. CC-BY attribution that only exists on disk is
            # attribution nobody sees.
            self.result["materials"] = self.material_provenance
        self._build_result: dict = {}

    def _load_contracts(
        self,
        contracts_path: str | Path | None,
        contracts: list[dict] | dict | None,
    ) -> list[dict]:
        """Load physics contracts from explicit args, spec, or YAML.

        Through contracts.io, which is the one place that decides what a
        contract is. This method used to parse the YAML itself and validate
        nothing, so the two loaders had drifted: contracts.io demanded `type:`
        and raised on cases/cantilever/contracts.yaml, which says `check:`,
        while this one accepted anything including a contract naming no check
        at all -- the evaluator then defaulted it to a range check.
        """
        from contracts.io import load_contracts, normalize_contracts

        raw = contracts
        if raw is None:
            raw = self.spec.get("contracts") or self.spec.get("physics_contracts")
        if raw is None and contracts_path and Path(contracts_path).exists():
            return load_contracts(contracts_path)
        return normalize_contracts(raw)

    # -------------------------------------------------------------------------
    # Main entry point
    # -------------------------------------------------------------------------

    def _preflight(self) -> dict | None:
        """Gate G2: without a resolvable Abaqus there is nothing to solve.

        Delegate to the demo (flow-walkthrough) contract in core.pipeline —
        never fabricate KPIs, never touch the case's runs/ cache dirs. Returns
        a finished result dict to short-circuit run(), or None to proceed.
        Subclasses (CalculiXOrchestrator) replace this with their own gate.
        """
        from core.helpers import check_abaqus
        if not check_abaqus():
            from core.pipeline import run_demo_flow
            return run_demo_flow(
                self.spec,
                spec_path=self.spec_path,
                workdir=self.workdir,
                on_progress=self.on_progress,
            )
        return None

    def run(self) -> dict:
        """Execute the full pipeline. Returns final result dict."""
        preflight = self._preflight()
        if preflight is not None:
            self.result = preflight
            return self.result

        # Check for parametric sweep
        if self._is_parametric():
            return self._run_parametric()

        max_retries = self.spec.get("analysis", {}).get("max_retries", 0)
        attempt = 0

        while attempt <= max_retries:
            try:
                self._stage_validate()
                build_result = self._stage_build()
                inp_path = build_result["inp_path"]

                if self.runner_cfg.get("syntaxcheck_first", True):
                    self._stage_syntaxcheck(inp_path, build_result["workdir"])

                submit_result = self._stage_submit(inp_path, build_result["workdir"])
                self._stage_monitor(submit_result)
                integrity = self._stage_dat_integrity(
                    self.spec["meta"]["model_name"], build_result["workdir"])

                odb_path = build_result["workdir"] / f"{self.spec['meta']['model_name']}.odb"
                kpi_result = self._stage_extract(odb_path)
                self._stage_export_visuals(odb_path)

                if self.expected:
                    self._stage_compare(kpi_result.get("kpis", {}))
                    self._block_regression_on_integrity(integrity)
                else:
                    self._stage_no_baseline()
                self._stage_contracts(kpi_result.get("kpis", {}))

                self.result["status"] = "COMPLETED"
                if attempt > 0:
                    self.result["autorepair"] = {"attempts": attempt, "repaired": True}
                break

            except AbaqusAgentError as e:
                # Try auto-repair if retries remain
                if attempt < max_retries and self._try_autorepair(e, attempt, max_retries):
                    attempt += 1
                    self.on_progress("autorepair", {"attempt": attempt, "max": max_retries})
                    continue

                self.result["status"] = "FAILED"
                self.result["error"] = e.to_dict()
                break
            except Exception as e:
                self.result["status"] = "ERROR"
                self.result["error"] = {"error_code": "UNKNOWN", "message": str(e)}
                break

        self.result["finished_at"] = datetime.now().isoformat()
        self._save_capsule()
        self._save_result()
        return self.result

    def _is_parametric(self) -> bool:
        """Check if this spec has a parametric sweep configuration."""
        parametric = self.spec.get("parametric")
        return bool(parametric and parametric.get("parameters"))

    def _run_parametric(self) -> dict:
        """Run parametric sweep."""
        from features.parametric.aggregator import save_report
        from features.parametric.sweep_engine import run_sweep

        self.on_progress("parametric_sweep", {"status": "starting"})
        workdir = self.workdir or self.spec_path.parent / "runs" / "parametric"

        def sweep_progress(idx, total, status, data):
            self.on_progress("parametric_sweep", {
                "index": idx, "total": total, "status": status})

        sweep_result = run_sweep(
            self.spec,
            workdir=workdir,
            max_parallel=self.spec.get("parametric", {}).get("max_parallel", 4),
            on_progress=sweep_progress,
        )

        save_report(sweep_result, workdir)

        self.result["status"] = "COMPLETED"
        self.result["parametric"] = sweep_result.get("summary", {})
        self.result["kpis"] = sweep_result.get("summary", {}).get("kpi_statistics", {})
        self.result["finished_at"] = datetime.now().isoformat()
        self._save_result()
        return self.result

    def _try_autorepair(self, error: AbaqusAgentError, attempt: int, max_retries: int) -> bool:
        """Attempt auto-repair of a failed job."""
        from features.autorepair.retry_loop import autorepair_hook

        context = {
            "spec": self.spec,
            "workdir": self.workdir,
            "job_name": self.spec.get("meta", {}).get("model_name", ""),
            "error": error,
            "attempt": attempt,
            "max_retries": max_retries,
        }

        context = autorepair_hook(context)

        if context.get("should_retry") and context.get("repaired_spec"):
            self.spec = context["repaired_spec"]
            self.result["stages"]["autorepair"] = context.get("diagnosis", {})

            # Clear cached .inp for rebuild
            if self.workdir:
                model_name = self.spec.get("meta", {}).get("model_name", "")
                inp = Path(self.workdir) / f"{model_name}.inp"
                if inp.exists():
                    inp.unlink()
            return True

        return False

    # -------------------------------------------------------------------------
    # Pipeline stages
    # -------------------------------------------------------------------------

    def _stage_validate(self):
        self.on_progress("validate_spec", {})
        valid, errors = validate_spec(self.spec)
        stage = {"valid": valid, "errors": errors}
        self.result["stages"]["validate_spec"] = stage
        if not valid:
            raise AbaqusAgentError(
                ErrorCode.SPEC_INVALID,
                f"Spec validation failed: {'; '.join(errors)}",
            )
        self._record_mesh_risks()
        self.on_progress("validate_spec", {"ok": True})

    def _record_mesh_risks(self):
        """Warn about element choices that can be silently, hugely wrong. (#72)

        A first-order reduced-integration element has one integration point and
        no resistance to bending in it. Measured twice, on two different
        models: an imported bar under a tip force gave C3D8I within 0.54% of
        the closed form and C3D8R 90.5x it; a bar built from this dialect under
        a side pressure, with one element through the thickness, gave -0.7126152
        against -65.66674, a factor of 92. Both jobs reported COMPLETED. The
        trigger is one string in `mesh.element` -- and, when the key is left
        out entirely, the DEFAULT.

        #72, decided 2026-08-07: warn and put it in the report. Not refuse --
        reduced integration is the correct choice under explicit dynamics with
        enhanced hourglass control, and a model with no bending in it is
        unaffected. No verdict changes and no run_id changes; this only writes
        to channels that already exist.

        Recomputed rather than appended on each attempt: the retry loop runs
        `_stage_validate` again, and an auto-repaired spec may have changed the
        very element this is about.
        """
        from core.element_risk import limitation_entries, spec_hourglass_findings

        findings = spec_hourglass_findings(self.spec)
        self.result["mesh_risks"] = findings
        kept = [entry for entry in self.result.get("limitations", [])
                if not (isinstance(entry, dict)
                        and entry.get("kind") == "hourglass_risk")]
        kept.extend(limitation_entries(findings))
        self.result["limitations"] = kept
        if findings:
            self.on_progress("validate_spec", {
                "warnings": ["%s = %s: %s" % (f["where"], f["element"], f["why"])
                             for f in findings]})

    def _adhoc_workdir(self) -> Path:
        """Where a spec that arrived as text, not as a file, gets built.

        Named by run id, like every other run directory. It used to be
        `mkdtemp(prefix="abaqus_run_")`, so every run started from the
        workbench or POST /api/run/start landed somewhere like
        `...\\Temp\\abaqus_run_mbmomka_`: unrelated to the id the API reported,
        so the evidence could not be found from it, and never reused, so the
        same spec re-solved from scratch every time.

        Still under the temp dir when no run root is configured -- an ad-hoc
        spec belongs to no case, and the repo is not the place for it.
        """
        import tempfile

        from core import config
        from core.helpers import run_id_for_spec

        run_id = run_id_for_spec(self.spec)
        root = config.run_root() or Path(tempfile.gettempdir())
        return root / ("abaqus_run_%s" % run_id)

    def _stage_build(self) -> dict:
        self.on_progress("build_model", {})
        # If no spec_path, write spec to workdir for build_model
        if not self.spec_path:
            if not self.workdir:
                self.workdir = self._adhoc_workdir()
            self.workdir.mkdir(parents=True, exist_ok=True)
            self.spec_path = self.workdir / "spec.yaml"
            self.spec_path.write_text(
                yaml.dump(self.spec, allow_unicode=True, default_flow_style=False),
                encoding="utf-8",
            )
        result = build_model(self.spec_path, self.workdir)
        self.result["stages"]["build_model"] = {k: str(v) for k, v in result.items()}
        self.workdir = result["workdir"]
        self._build_result = result
        progress = {"inp": str(result["inp_path"])}
        # Whether this deck was rebuilt or reused — and on what proof — must
        # reach the user, not stay in a return dict nobody renders.
        if result.get("cache_reason"):
            progress["cached"] = bool(result.get("cached"))
            progress["cache_reason"] = result["cache_reason"]
        self.on_progress("build_model", progress)
        return result

    def _stage_syntaxcheck(self, inp_path: Path, workdir: Path):
        self.on_progress("syntaxcheck", {})
        result = syntaxcheck_inp(inp_path, workdir)
        self.result["stages"]["syntaxcheck"] = result
        if not result["ok"]:
            raise AbaqusAgentError(
                ErrorCode.SYNTAX_ERROR,
                f"syntaxcheck failed: {result['errors'][:3]}",
                workdir=str(workdir),
            )
        self.on_progress("syntaxcheck", {"ok": True, "warnings": len(result["warnings"])})

    def _stage_submit(self, inp_path: Path, workdir: Path) -> dict:
        self.on_progress("submit_job", {})
        result = submit_job(
            inp_path=inp_path,
            workdir=workdir,
            cpus=self.runner_cfg["cpus"],
            mp_mode=self.runner_cfg["mp_mode"],
            memory=self.runner_cfg["memory"],
            background=False,
            interactive=True,
            allow_license_queue=self.runner_cfg["allow_license_queue"],
            timeout_seconds=self.runner_cfg["timeout_seconds"],
            # The spec's `job:` block. It carries what the DECK cannot say --
            # double precision, a user subroutine, a restart source, GPUs --
            # because those are launcher options rather than keywords, so
            # before this there was nowhere in a spec to put them.
            job_options=self.spec.get("job"),
        )
        self.result["stages"]["submit_job"] = {k: str(v) for k, v in result.items()}
        self.on_progress("submit_job", {"status": result.get("status")})
        return result

    def _stage_monitor(self, submit_result: dict):
        """For interactive mode this is already done; for background mode we poll."""
        job_name = submit_result.get("job_name", "")
        workdir  = Path(submit_result.get("workdir", self.workdir))

        if submit_result.get("status") == "completed":
            # "completed" here only means the launcher exited 0 — and the Abaqus
            # launcher exits 0 even when the analysis aborts. Measured on
            # cantilever_plastic: the .sta ended in "THE ANALYSIS HAS NOT BEEN
            # COMPLETED", yet the run was reported COMPLETED and the pipeline
            # went on to extract U_tip = -221.5 mm from a 100 mm beam and grade
            # it a pass. The .sta verdict is the solver's own answer, so read it
            # instead of trusting the exit code.
            verdict = monitor_job(job_name, workdir)
            self.result["stages"]["monitor_job"] = verdict
            self.on_progress("monitor_job", verdict)
            if verdict.get("status") != JobStatus.COMPLETED:
                raise AbaqusAgentError(
                    ErrorCode.JOB_FAILED,
                    "求解器自己说没算完（%s）：%s"
                    % (verdict.get("status"), _sta_tail(job_name, workdir)),
                    log_snippet=str(verdict.get("errors", "")),
                    workdir=str(workdir),
                )
            return

        # Background polling loop
        deadline = time.time() + self.runner_cfg["timeout_seconds"]
        poll_interval = 10
        while time.time() < deadline:
            status = monitor_job(job_name, workdir)
            self.result["stages"]["monitor_job"] = status
            self.on_progress("monitor_job", status)
            if status["status"] in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.ABORTED):
                break
            time.sleep(poll_interval)
            poll_interval = min(poll_interval * 1.5, 60)

        final = self.result["stages"].get("monitor_job", {})
        if final.get("status") not in (JobStatus.COMPLETED,):
            raise AbaqusAgentError(
                ErrorCode.JOB_FAILED,
                f"Job ended with status: {final.get('status')}",
                log_snippet=str(final.get("errors", "")),
                workdir=str(workdir),
            )

    def _stage_dat_integrity(self, job_name: str, workdir: Path) -> dict:
        """Read the .dat for warnings that say the model is not the spec's model.

        The solver's own verdict (`monitor_job`) answers "did it finish", and
        the .sta answers "did it converge". Neither answers "is this the model
        that was asked for", and Abaqus does not raise when the answer is no: a
        `*Tie` whose slave nodes fall outside the position tolerance is left
        untied, the job converges, and a full .odb is written. Measured on this
        repository's bearing_block: 85 nodes silently unconstrained, all three
        equilibrium identities still passing, run reported COMPLETED.

        Reported through `limitations`, which is the channel a degraded run
        already travels on and the one the UI cannot render as a clean run.
        """
        from runner.dat_warnings import limitation_lines, parse_dat_warnings

        report = parse_dat_warnings(workdir / ("%s.dat" % job_name))
        self.result["stages"]["dat_integrity"] = {
            "read": report["read"],
            "integrity_count": report["integrity_count"],
            "findings": report["findings"],
            "unrecognised": report["unrecognised"],
        }
        lines = limitation_lines(report)
        if lines:
            self.result.setdefault("limitations", []).extend(lines)
        self.on_progress("dat_integrity", {
            "integrity_count": report["integrity_count"],
            "findings": [f["id"] for f in report["findings"]],
        })
        return report

    def _stage_extract(self, odb_path: Path) -> dict:
        self.on_progress("extract_kpis", {})
        kpi_spec = normalize_recipe(self.spec.get("outputs", {}).get("kpis", []))
        self.result["odb_lens_recipe"] = kpi_spec
        result = extract_kpis(odb_path, kpi_spec, self.workdir)
        self.result["stages"]["extract_kpis"] = result
        self.result["kpis"] = result.get("kpis", {})
        self._record_missing_kpis(kpi_spec, result)
        if result.get("errors"):
            self.on_progress("extract_kpis", {"warnings": result["errors"]})
        else:
            self.on_progress("extract_kpis", {"kpis": self.result["kpis"]})
        return result

    def _record_missing_kpis(self, kpi_spec: list, result: dict) -> list:
        """Lift "a KPI the spec asked for never came back" to the TOP LEVEL.

        It used to live only in `stages.extract_kpis.errors`, three levels down
        a dict nothing walked, while `result["kpis"]` quietly held fewer
        entries than the spec requested and the run reported COMPLETED. The
        report even printed a KPI count -- of what was delivered, with nothing
        to compare it against, so two of three read exactly like two of two.

        #73(b): this does NOT change the verdict. That was decided deliberately
        -- turning a dropped KPI into a FAILED run would re-grade every shipped
        case and every frozen baseline, which is a different question from
        whether the shortfall is visible.
        """
        missing = missing_kpis(kpi_spec, self.result["kpis"], result.get("errors"))
        self.result["kpis_missing"] = missing
        # Appended, never assigned: the CalculiX subclass has already put its
        # capability caveats in this list by the time extraction runs, and an
        # assignment here would erase them.
        self.result.setdefault("limitations", []).extend(
            {"feature": "KPI", "value": m["name"], "kind": "kpi_not_extracted",
             "reason": "%s 这条 KPI 被 spec 要求了，但结果里没有。%s" % (
                 "(%s)" % m["type"] if m["type"] else "",
                 m["reason"] or "抽取器没有报出提到它的错误，详见 stages.extract_kpis。")}
            for m in missing)
        return missing

    def _stage_export_visuals(self, odb_path: Path) -> dict:
        self.on_progress("export_odb_images", {})
        kpi_spec = self.result.get("odb_lens_recipe") or normalize_recipe(self.spec.get("outputs", {}).get("kpis", []))
        plot_spec = normalize_plots(self.spec, kpi_spec)
        result = export_odb_images(odb_path, plot_spec, self.workdir)
        self.result["stages"]["export_odb_images"] = result
        self.result["visuals"] = result.get("images", [])
        if result.get("errors"):
            self.on_progress("export_odb_images", {"warnings": result["errors"]})
        else:
            self.on_progress("export_odb_images", {"images": result.get("images", [])})

        # Interactive 3D viewport data (best-effort; PNGs above are the fallback)
        mesh_result = export_odb_mesh(odb_path, self.workdir)
        self.result["stages"]["export_odb_mesh"] = mesh_result
        if mesh_result.get("mesh_file"):
            self.result["mesh_file"] = Path(mesh_result["mesh_file"]).name

        # Frame-by-frame animation only makes sense for dynamic steps (best-effort)
        step_type = self.spec.get("analysis", {}).get("step_type")
        if step_type in ("Dynamic_Explicit", "Dynamic_Implicit"):
            anim_result = export_odb_animation(odb_path, self.workdir)
            self.result["stages"]["export_odb_animation"] = anim_result
            self.result["animation"] = {
                "frames": anim_result.get("frames", 0),
                "video": anim_result.get("video"),
            }
            if anim_result.get("errors"):
                self.on_progress("export_odb_animation", {"warnings": anim_result["errors"]})
            else:
                self.on_progress("export_odb_animation", {"frames": anim_result.get("frames", 0)})
        return result

    def _block_regression_on_integrity(self, integrity: dict):
        """A run whose constraints did not all take effect cannot report PASS.

        The KPIs may well be right -- equilibrium holds however the load gets
        carried, so the bearing_block identities all passed while 85 nodes sat
        unconstrained. That is exactly why this exists: `regression.passed` is
        the field a person reads as "the model is correct", and it must not say
        so about a model that is provably not the one the spec described.

        The comparisons are kept verbatim. Nothing is hidden; the verdict on top
        of them is withdrawn, with the reason attached.
        """
        if not integrity or not integrity.get("integrity_count"):
            return
        regression = self.result.get("regression")
        if not isinstance(regression, dict):
            return
        blockers = [f["id"] for f in integrity.get("findings", [])
                    if f.get("integrity")]
        regression["passed"] = False
        regression["blocked_by_integrity"] = {
            "count": integrity["integrity_count"],
            "findings": blockers,
            "note": ("KPI 本身可能是对的——平衡恒等式不在乎载荷是被哪些节点"
                     "承担的。但这个模型里有 %d 个节点上的约束没有生效，它"
                     "已经不是 spec 描述的那个模型，所以这里不给通过。"
                     "详见 stages.dat_integrity 与 limitations。"
                     % integrity["integrity_count"]),
        }

    def _stage_no_baseline(self):
        """No expected.json was supplied, so nothing was graded -- record that.

        `result["regression"]` is initialised to `{}` and, without this, stays
        that way: a finished run carrying an empty dict, which every consumer
        renders as the absence of a problem rather than the absence of a check.
        Measured 2026-08-09: core.pipeline built this orchestrator without
        `expected_path` at all, so every workbench Accept, every
        /api/run/start and every MCP start_run landed here -- the whole set of
        paths a user actually walks -- and none of them said anywhere that no
        number had been compared to anything.

        This is the same shape `_stage_compare` produces when expected.json
        carries no numeric baseline, for the same reason: not compared is not
        passed.
        """
        note = ("本次运行没有提供 expected.json 基准，未做任何数值比对"
                "——这不是通过，是没有检查")
        self.result["regression"] = {
            "passed": None,
            "comparisons": {},
            "not_compared_reason": note,
        }
        self.on_progress("compare_kpis",
                         {"passed": None, "details": {}, "caveat": note})

    def _stage_compare(self, actual_kpis: dict):
        """Compare extracted KPIs against expected.json."""
        expected_kpis = self.expected.get("kpis", {})
        comparison = {}

        for name, expected_def in expected_kpis.items():
            exp_val  = expected_def.get("value")
            rtol     = expected_def.get("rtol", 0.10)
            atol     = expected_def.get("atol", 0.0)
            act_val  = actual_kpis.get(name)

            if act_val is None:
                comparison[name] = {"status": "MISSING", "expected": exp_val, "actual": None}
                continue

            if exp_val is None:
                comparison[name] = {"status": "INFO", "expected": exp_val,
                                    "actual": act_val}
                continue

            abs_err = abs(act_val - exp_val)

            if exp_val == 0:
                # A baseline of exactly zero used to fall into the INFO branch
                # below, and INFO counts as passing — so every symmetry,
                # net-force and residual-drift check written this way passed no
                # matter what came back. Measured: expected 0.0 with atol 1e-6
                # against an actual of 1e9 reported passed: True, and the entry
                # appeared in `comparisons` as though it had been checked.
                # A relative tolerance cannot judge zero, so an absolute one is
                # required and its absence is refused rather than waved through.
                if "atol" not in expected_def:
                    comparison[name] = {
                        "status": "FAIL",
                        "expected": exp_val,
                        "actual": act_val,
                        "abs_err": round(abs_err, 6),
                        "reason": ("基准为 0 时相对容差无意义，必须给 atol。"
                                   "此前这类条目被判 INFO，而 INFO 计入通过，"
                                   "等于任何实际值都算过"),
                    }
                    continue
                comparison[name] = {
                    "status": "PASS" if abs_err <= atol else "FAIL",
                    "expected": exp_val,
                    "actual": act_val,
                    "abs_err": round(abs_err, 6),
                    "atol": atol,
                }
                continue

            # Check within tolerance
            rel_err = abs_err / abs(exp_val)
            passed  = rel_err <= rtol or abs_err <= atol
            comparison[name] = {
                "status": "PASS" if passed else "FAIL",
                "expected": exp_val,
                "actual": act_val,
                "rel_err": round(rel_err, 4),
                "abs_err": round(abs_err, 6),
                "rtol": rtol,
                "atol": atol,
            }

        if not comparison:
            # Nothing was checked, so nothing passed. Reporting True here read
            # as "regression clean" on cantilever_plastic, whose expected.json
            # deliberately carries no numeric baseline because the case is
            # supposed to diverge — the pipeline graded a run it had not
            # compared against anything.
            note = ("expected.json 没有给任何 KPI 基准，本次运行未做任何数值比对"
                    "——这不是通过，是没有检查")
            self.result["regression"] = {
                "passed": None,
                "comparisons": {},
                "not_compared_reason": note,
            }
            self.on_progress("compare_kpis",
                             {"passed": None, "details": {}, "caveat": note})
            return

        all_pass = all(v.get("status") in ("PASS", "INFO") for v in comparison.values())
        self.result["regression"] = {
            "passed": all_pass,
            "comparisons": comparison,
        }
        self.on_progress("compare_kpis", {"passed": all_pass, "details": comparison})

    def _stage_contracts(self, actual_kpis: dict):
        """Evaluate physics contracts against extracted KPIs."""
        if not self.contracts:
            # Zero checks is not a pass. Measured 2026-08-09: 11 of the 12
            # shipped cases reported `{"passed": True, "results": []}` because
            # no contracts file ever reached the orchestrator, and
            # case_memory indexed all of them as contract-passing runs.
            note = ("没有加载到任何 physics contract，本次运行未做契约检查"
                    "——这不是通过，是没有检查")
            self.result["contracts"] = {
                "passed": None,
                "results": [],
                "not_checked_reason": note,
            }
            self.result["stages"]["physics_contracts"] = {
                "passed": None, "checks": 0, "not_checked_reason": note,
            }
            self.on_progress("physics_contracts",
                             {"passed": None, "checks": 0, "caveat": note})
            return

        result = evaluate_contracts(self.contracts, actual_kpis)
        self.result["contracts"] = result
        self.result["stages"]["physics_contracts"] = {
            "passed": result.get("passed", False),
            "checks": len(result.get("results", [])),
        }
        self.on_progress("physics_contracts", {
            "passed": result.get("passed", False),
            "checks": len(result.get("results", [])),
        })

    # -------------------------------------------------------------------------
    # Persistence
    # -------------------------------------------------------------------------

    def _save_result(self):
        if self.workdir:
            result_path = Path(self.workdir) / "result.json"
            try:
                result_path.write_text(
                    json.dumps(self.result, indent=2, default=str),
                    encoding="utf-8",
                )
            except Exception as exc:
                # Still not fatal — the run itself succeeded and the capsule is
                # already on disk — but a silent pass meant a run could report
                # COMPLETED with no result.json behind it and nobody could tell
                # why. Say it out loud and mark the result so any consumer that
                # re-reads this object knows the archive is incomplete.
                import sys
                print("[orchestrator] result.json not written to %s: %s: %s"
                      % (result_path, type(exc).__name__, exc), file=sys.stderr)
                self.result["result_json_error"] = "%s: %s" % (type(exc).__name__, exc)

    def _save_capsule(self):
        if not self.workdir:
            return

        workdir = Path(self.workdir)
        artifacts = self._collect_artifacts(workdir)
        metadata = self._capsule_metadata()
        if self.result.get("error"):
            metadata["error"] = self.result["error"]

        capsule = create_capsule(
            run_id=self._build_result.get("run_id", workdir.name),
            capsule_dir=workdir,
            inputs=self._capsule_inputs(workdir),
            artifacts=artifacts,
            metadata=metadata,
        )

        if self.result.get("contracts"):
            capsule["contracts"] = self.result["contracts"]
            write_capsule(capsule, workdir)

        if self.result.get("status") != "COMPLETED":
            log_paths = [workdir / name for name in artifacts if Path(name).suffix.lower() in {".sta", ".msg", ".log", ".dat"}]
            diagnosis = diagnose_logs(paths=log_paths)
            if diagnosis.get("matched"):
                capsule["diagnosis"] = diagnosis
                write_capsule(capsule, workdir)

        self.result["capsule_path"] = str(workdir / "capsule.json")

    def _capsule_metadata(self) -> dict:
        """Provenance recorded in the capsule. Overridden per backend."""
        return {
            "status": self.result.get("status"),
            "abaqus_release": self.spec.get("meta", {}).get("abaqus_release"),
            "solver_backend": "abaqus",
        }

    def _capsule_inputs(self, workdir: Path) -> dict:
        inputs = {
            "model_name": self.spec.get("meta", {}).get("model_name"),
            "spec_path": str(self.spec_path) if self.spec_path else None,
        }
        spec_copy = workdir / "spec.yaml"
        if spec_copy.exists():
            inputs["spec"] = "spec.yaml"
            inputs["spec_sha256"] = hash_file(spec_copy)

        source_inp = self._build_result.get("source_inp_path")
        if source_inp:
            inputs["source_inp"] = str(source_inp)

        # The build fingerprint makes the capsule self-proving: an archived
        # run can show WHICH source deck, emitted by WHICH generator, on WHICH
        # probed solver produced these numbers.
        manifest_path = workdir / "build_manifest.json"
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                manifest = None
            if manifest:
                for key in ("inp_sha256", "source_inp_sha256",
                            "generator_script_sha256", "abaqus_release_probed"):
                    if manifest.get(key) is not None:
                        inputs[key] = manifest[key]
        return inputs

    def _collect_artifacts(self, workdir: Path) -> dict:
        artifacts = {}
        for path in sorted(workdir.iterdir()):
            if not path.is_file() or path.name == "capsule.json":
                continue
            try:
                artifacts[path.name] = {
                    "path": path.name,
                    "sha256": hash_file(path),
                    "bytes": path.stat().st_size,
                }
            except OSError:
                continue
        return artifacts


# ---------------------------------------------------------------------------
# Backend-aware factory
# ---------------------------------------------------------------------------

def build_orchestrator(decision=None, **kwargs) -> AbaqusOrchestrator:
    """Return the orchestrator for the chosen backend.

    ``decision`` is a core.backends.BackendDecision (or None = Abaqus, the
    historical behaviour). The CalculiX import is lazy so the Abaqus path never
    pays for it and there is no import cycle through core.backends.
    """
    backend = getattr(decision, "backend", None)
    if backend == "calculix":
        from agent.ccx_orchestrator import CalculiXOrchestrator
        return CalculiXOrchestrator(decision=decision, **kwargs)
    return AbaqusOrchestrator(**kwargs)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python agent/orchestrator.py <spec.yaml> [expected.json] [runner.json] [contracts.yaml]")
        sys.exit(1)

    def _progress(stage, data):
        print(f"  [{stage}] {data}")

    from core.backends import select_backend
    _spec = yaml.safe_load(Path(sys.argv[1]).read_text(encoding="utf-8"))
    _decision = select_backend(_spec)
    print(f"  [backend] {_decision.label} — {_decision.reason}")

    orch = build_orchestrator(
        decision=_decision,
        spec_path=sys.argv[1],
        expected_path=sys.argv[2] if len(sys.argv) > 2 else None,
        runner_cfg_path=sys.argv[3] if len(sys.argv) > 3 else None,
        contracts_path=sys.argv[4] if len(sys.argv) > 4 else None,
        on_progress=_progress,
    )
    result = orch.run()
    print(json.dumps(result, indent=2, default=str))
    sys.exit(0 if result["status"] == "COMPLETED" else 1)
