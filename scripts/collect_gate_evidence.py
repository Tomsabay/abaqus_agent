#!/usr/bin/env python3
"""Turn a gate script's JSON output into a summary that can be committed.

docs/ROADMAP.md states the rule this project runs on: a capability ships as
"supported" only when a real solver run proves it, the gate is a passing item
in ``scripts/run_*_check.py``, and its output is committed as evidence. The
last clause was true of this repository and false of the published tree, where
the allowlist excludes ``evidence/**`` apart from six Python modules the server
imports. A reader outside got nine gate scripts and not one number.

Committing the raw output is not the fix. A run directory is 178 MB in one
measured case, and the gates' JSON carries absolute paths and the machine's
user name. So this reduces a gate's output to the part that is worth reading
and safe to publish:

    what ran, which items, whether each passed, the identity each item checks,
    the numbers it measured, the Abaqus release, and how long it took.

and drops the rest. Redaction is by allowlist for the same reason the publish
tree is: a deny-list of "keys that carry paths" fails open the moment a gate
adds a field.

RUN:
    python scripts/collect_gate_evidence.py <gate-json> [<gate-json> ...]
        --out evidence/gates

Each input may be a bare .json file or a gate log whose JSON body starts at
the first '{' -- the gates print a human summary first, and this reads both.

Two shapes exist and both are handled explicitly:

  * a gate report, ``{"items": [...]}`` -- one script's items;
  * a harness summary, ``{"gates": [...]}`` -- run_all_real_checks.py's roll-up
    of every gate.

Anything else is REFUSED. That is not pedantry: handed the harness summary,
the items-only version of this script wrote a file that said "0 pass, 0 fail,
0 skipped" and returned 0. An evidence collector that answers "nothing here"
when it did not understand its input is the exact failure this repository
keeps finding elsewhere, and it published it.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Everything else is dropped. Adding a field to a gate does not silently
# publish it.
RUN_KEYS = ("schema", "abaqus_release", "ccx_version", "overall", "seconds")
# The harness roll-up's per-gate row. `script` is a repo-relative path and is
# meant to be readable; `_scrub` leaves it alone and would catch an absolute
# one.
GATE_KEYS = ("name", "script", "solver", "result", "seconds", "reason")
ITEM_KEYS = (
    # `id` is what the solver gates name their items. The six BROWSER gates
    # name them `name` and carry the measurement in `detail`, and neither was
    # listed here -- so every one of their items reduced to {"status": "pass"}
    # and the published file said "9 things passed" without saying which nine.
    # Measured when it was found: pick_ui 20/20 and result_mesh_ui 9/9 items,
    # all hollow, both already committed. An allowlist fails closed by design,
    # which is right, but a key nobody adds is a silent hole rather than a
    # refusal -- hence test_browser_gate_items_keep_their_names below.
    "id", "name", "detail", "status", "identity", "mutation", "note", "reason",
    "theory_volume", "measured_volume", "relative_deviation",
    "expected_elements", "measured_elements", "elements_written",
    "section_written", "predicted", "measured", "force", "k_total",
    "applied_n", "measured_n", "tolerance_mm", "bolts_placed",
    "blind_volume", "correct_volume", "generic_volume", "named_volume",
    "aborted", "cylinders_aborted", "volume_and_counts_passed",
    "count_check_passed", "position_check_aborted", "seconds",
    # The CalculiX backend gate. A refusal item's evidence IS its refusal
    # text: "status: pass" alone does not show that the reason names the
    # offending card rather than saying the solver cannot do it.
    "deck", "spec_shape", "spec_change", "orchestrator_status", "error_code",
    "refusals", "kpis", "measured_u_tip_mm", "reference_u_tip_mm",
    "tolerance_relative", "measured_mises_nodal_averaged",
    "recorded_ccx_value", "abaqus_element_nodal_value", "gap_vs_abaqus_pct",
    # The positioning gate. Same reason: the line the kernel logged is the
    # measurement, and "status: pass" without it is a claim rather than
    # evidence.
    "expected_centroid", "placed_line", "refusal_line",
    # The false-refusal budget. The measured offset against the two tolerances
    # is the whole item: without the number, "the old default refused a correct
    # bore" is an assertion rather than a measurement somebody can check.
    "bore_radius", "stated_centroid", "measured_offset", "old_flat_default",
    "new_default", "correct_position_accepted", "old_default_refused_it",
    "moved_bore_still_refused",
    # The bearing_block gate. Its whole point is a model whose identities pass
    # while 85 constraint findings say the tie did not bind, so the counts and
    # the deviations ARE the item -- "status: pass" without them publishes the
    # conclusion and withholds the measurement.
    "tie_tolerance", "integrity_count", "integrity_ids", "identity_deviations",
    "untied_blocks", "integrity_counts", "deck_lines", "misalignment_mm",
    "datacheck_ok", "caught_by",
    # The keyword-block item. The card being in the deck was exactly the claim
    # that turned out to be worth nothing on its own, so the error count from
    # the input file processor has to ride along with it -- and each of the
    # three refusals is a separate direction the check has been shown to cover.
    "card", "card_in_written_deck", "deck_input_processor_errors",
    "conflict_block_refused", "out_of_range_aborted",
    "refused_when_the_card_is_absent",
    # The dispatch and step-order items, for the same reason as the positioning
    # gate: the refusal text and the ordered step cards are the measurement.
    "banana_refusal", "unbound_refusal", "step_two_tip",
    "beam_theory_step_two_tip", "beam_theory_if_unchanged",
    "step_cards_in_order", "step_order_line",
    # The rest of the dropped-input gate.
    "declared_yield", "elastic_peak", "plastic_peak", "plastic_card_written",
    "stated", "built_with_stated_variables", "built_with_the_old_default",
    "job_completed", "why_the_default_fails", "reported_message",
    "reported_snippet", "reached_line", "set_form_refusal",
    # The geometry import gate. The stated volume against the measured tip is
    # the whole item: a format can hand back the exact right volume and still
    # produce a part that meshes into nothing, so publishing "pass" without
    # both numbers publishes the conclusion and withholds the measurement.
    "stated_volume", "true_volume", "measured_tip", "beam_theory_tip",
    "deck_lines_with_numbers", "faces_only_refusal", "refusal",
    # The reference point gate. One item there passes by demonstrating a
    # SILENT wrong answer -- a control point 50 mm past the end of the bar,
    # 74% out, 0 errors and COMPLETED -- so the offset and the two .dat counts
    # are what make it readable as a hazard rather than as a green tick.
    "offset_mm", "dat_errors", "dat_warnings", "rigid_body_card", "mpc_card",
    # BOTH readings, and this pair was left out of the first cut. The item's
    # whole content is that they come apart -- whole model -0.61471903 against
    # tip face -0.33120051 -- so an evidence file carrying one of them states
    # the conclusion and withholds the measurement it rests on.
    "measured_bar_tip", "named_set_line",
    # The job layer gate. Its first item passes by asserting something
    # UNCOMFORTABLE -- that odb.jobData.precision does not move when the spec
    # asks for double precision -- so the value read is the item, not a
    # detail. And the buckling eigenvalue against the closed form is the only
    # thing separating "a number came back" from "the right number came back".
    "odb_precision", "measured_eigenvalue", "euler_p_cr",
    # The seam gate. Its criterion was written down before the feature was, in
    # one sentence -- a seam that took effect DUPLICATES THE NODES ALONG IT --
    # so the two deck counts ARE the item. A seam on a face that is not shared
    # by two cells is accepted by Abaqus and changes nothing, which means
    # "status: pass" without 27 and 36 side by side is exactly the claim this
    # gate exists to refuse to take on trust.
    "plain_deck_nodes", "seamed_deck_nodes", "seam_line",
    # The orphan mesh gate. Its end-to-end item is the only thing that
    # says a part read out of a deck is a bar rather than 189 points,
    # and its refusals turn on numbers Abaqus reports without objecting:
    # getVolume() answers 0.0 on a part with no cells, and the import
    # drops every set and surface the file carried.
    "source_deck", "import_line", "mesh_line", "true_volume",
    "no_expect_refusal", "mesh_block_refusal",
    # The crack gate. `contours` is the whole point of publishing this one:
    # both broken variants COMPLETED with no warning, so "status: pass" says
    # only that we refused something. What shows WHY is the six numbers --
    # round-off either side of nothing for the unseparated crack, and the
    # correct magnitude with the wrong sign for the reversed one -- next to a
    # `spread` that is identical for the reversed run and the correct one, so
    # a reader can see that convergence alone would have passed it.
    "measured_j", "handbook_j", "error_fraction", "spread", "contours",
    # `reference_j` is the scripted rig's answer, published beside the one the
    # v2 dialect authored. The pair is the item: the handbook gap is -2.1%, so
    # a reader who is given only "pass" cannot tell a matching model from an
    # approximately matching one, and matching to every digit is the claim.
    "reference_j",
    # The material-rebuild gate. `readback` is what the KERNEL said the
    # material had, before and after -- without it the file records that we
    # refused something, not that there was anything to refuse. `deck_written`
    # is how that gate knows a build stopped, because `abaqus cae` exits 0
    # either way.
    "readback", "deck_written",
)

# A note or an identity is free text written by a human, so it is the one place
# a path could still ride along. Measured on this machine: the gates' work_dir
# is under C:\Users\<name>\AppData\Local\Temp.
_PATHISH = re.compile(r"""(?ix)
      [a-z]:[\\/]\S*            # C:\... or D:/...
    | \\\\\S+                   # UNC
    | /(?:home|users|tmp|var)/\S*
""")


def _scrub(value):
    if isinstance(value, str):
        return _PATHISH.sub("<path>", value)
    if isinstance(value, list):
        return [_scrub(v) for v in value]
    if isinstance(value, dict):
        return dict((k, _scrub(v)) for k, v in value.items())
    return value


def _load(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    start = text.find("{")
    if start < 0:
        raise ValueError("%s holds no JSON object" % path)
    return json.loads(text[start:])


class UnknownShape(ValueError):
    """The input is neither a gate report nor a harness summary."""


def summarise(raw: dict, source: str) -> dict:
    if "items" in raw:
        return _summarise_items(raw, source)
    if "gates" in raw:
        return _summarise_gates(raw, source)
    raise UnknownShape(
        "no `items` and no `gates` key, so this is not a gate report "
        "(scripts/run_*_check.py) or a harness summary "
        "(scripts/run_all_real_checks.py). Keys present: %s"
        % (", ".join(sorted(map(str, raw))) or "(none)"))


def _summarise_items(raw: dict, source: str) -> dict:
    items = []
    for item in raw.get("items", []):
        row = dict((k, _scrub(item[k])) for k in ITEM_KEYS if k in item)
        # Not the problem text -- a failure's message is where a path is most
        # likely to be. The count is what a reader needs.
        problems = item.get("problems") or []
        if problems:
            row["problem_count"] = len(problems)
        items.append(row)
    out = dict((k, raw[k]) for k in RUN_KEYS if k in raw)
    out["source"] = source
    out["items"] = items
    out["counts"] = {
        "total": len(items),
        "pass": sum(1 for i in items if i.get("status") == "pass"),
        "fail": sum(1 for i in items if i.get("status") == "fail"),
        "skipped": sum(1 for i in items if i.get("status") == "skipped"),
    }
    return out


def _summarise_gates(raw: dict, source: str) -> dict:
    """The harness roll-up: one line per gate, verdict and wall clock.

    The per-gate `items` counts are kept because "PASS" alone does not say
    whether a gate ran ten checks or was silently reduced to one.
    """
    gates = []
    for gate in raw.get("gates", []):
        row = dict((k, _scrub(gate[k])) for k in GATE_KEYS if k in gate)
        counts = gate.get("items")
        if isinstance(counts, dict):
            row["items"] = dict((k, counts[k]) for k in
                                ("total", "pass", "fail", "skipped")
                                if k in counts)
        gates.append(row)
    out = dict((k, raw[k]) for k in RUN_KEYS if k in raw)
    out.setdefault("schema", "real_check_gate_summary/1")
    out["source"] = source
    if raw.get("total_seconds") is not None:
        out["total_seconds"] = raw["total_seconds"]
    out["counts"] = {
        "total": len(gates),
        "pass": sum(1 for g in gates if g.get("result") == "PASS"),
        "skipped": sum(1 for g in gates if g.get("result") == "SKIPPED"),
        "fail": sum(1 for g in gates
                    if g.get("result") not in ("PASS", "SKIPPED")),
    }
    out["gates"] = gates
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--out", type=Path, default=Path("evidence/gates"))
    parser.add_argument("--name", action="append", default=None,
                        help="output stem per input; defaults to the input's")
    args = parser.parse_args(argv)

    args.out.mkdir(parents=True, exist_ok=True)
    failed = 0
    for i, path in enumerate(args.inputs):
        try:
            raw = _load(path)
        except Exception as exc:
            print("%s: %s: %s" % (path, type(exc).__name__, exc))
            failed += 1
            continue
        stem = (args.name[i] if args.name and i < len(args.name)
                else path.stem)
        try:
            summary = summarise(raw, stem)
        except UnknownShape as exc:
            # Refuse rather than write an empty summary over a real one. The
            # target file is left exactly as it was.
            print("%s: %s" % (path, exc))
            failed += 1
            continue
        target = args.out / (stem + ".json")
        target.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")
        counts = summary["counts"]
        print("%-34s -> %s  (%d pass, %d fail, %d skipped)"
              % (path.name, target, counts["pass"], counts["fail"],
                 counts["skipped"]))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
