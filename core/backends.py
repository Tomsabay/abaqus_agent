"""
core/backends.py
----------------
Which solver runs this spec, and what happens when there is none.

Policy (the owner's words): this product drives Abaqus. If the user has Abaqus
we use it — we do not care which version or where it came from. If they do not,
the run is refused with the one sentence that fixes it. There is no second
solver and no walkthrough.

Both used to be here. A CalculiX backend shipped 2026-08-01 and a demo mode
long before it; both were removed 2026-08-15 by the owner's decision. A visitor
with no Abaqus is not a user of an Abaqus workbench, so a verified-subset
fallback bought reach we do not want at the cost of a whole capability matrix to
keep honest — and a walkthrough that narrated seven stages and finished
COMPLETED was, at a glance, indistinguishable from a machine that had solved
something. Nothing here approximates a solver that is absent.

One rule survives it and still shapes this module:

    Refusing is a correct outcome. Silently approximating is a defect.

Leaf-ish module: imports only tools/*, so pytest can exercise the decision
logic without pulling in the runner or the server.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal

from core import messages
from tools.abaqus_cmd import ENV_ABAQUS_CMD, detect_abaqus_release

# auto | abaqus. Kept as a variable rather than dropped: it is the name shown in
# the refusal when someone asks for a backend that no longer exists.
ENV_BACKEND = "ABAQUS_AGENT_SOLVER_BACKEND"

BACKEND_ABAQUS = "abaqus"

Backend = Literal["abaqus"]


@dataclass(frozen=True)
class Limitation:
    """One thing the chosen backend cannot do, in words a user can act on."""

    feature: str          # dotted spec path, e.g. "analysis.step_type"
    value: str            # the offending value
    reason: str           # rendered Chinese: what is wrong and what to do
    kind: str = "blocker"  # "blocker" = refuse the run; "caveat" = run, tag the number
    # The same sentence as a catalogue key, so a run recorded today can be read
    # back in English tomorrow. `reason` above stays Chinese and stays the
    # thing every existing caller reads; this is additive.
    reason_key: str = ""
    suffix_key: str = ""   # appended verbatim; the entry carries its own separator
    reason_params: Mapping[str, str] = field(default_factory=dict, compare=False)

    def localized(self, lang: str | None = None) -> str:
        if not self.reason_key:
            return self.reason
        text = messages.render(self.reason_key, lang, fallback=self.reason,
                               **self.reason_params)
        if self.suffix_key:
            text += messages.render(self.suffix_key, lang, **self.reason_params)
        return text

    def as_dict(self) -> dict:
        return {"feature": self.feature, "value": self.value,
                "reason": self.reason, "kind": self.kind,
                "reason_key": self.reason_key, "suffix_key": self.suffix_key,
                "reason_params": dict(self.reason_params)}


@dataclass(frozen=True)
class BackendDecision:
    backend: Backend
    label: str                                   # e.g. "Abaqus 2021"
    reason: str                                  # why this backend was chosen
    source: str                                  # "auto" | "env" | "runner_cfg"
    version: str | None = None
    blockers: tuple[Limitation, ...] = field(default_factory=tuple)
    caveats: tuple[Limitation, ...] = field(default_factory=tuple)
    # As with Limitation: `reason` stays Chinese for every existing reader,
    # and the key lets a browser render the same sentence in English.
    reason_key: str = ""
    reason_params: Mapping[str, str] = field(default_factory=dict, compare=False)

    @property
    def supported(self) -> bool:
        return not self.blockers

    def as_dict(self) -> dict:
        return {
            "backend": self.backend,
            "label": self.label,
            "reason": self.reason,
            "reason_key": self.reason_key,
            "reason_params": dict(self.reason_params),
            "source": self.source,
            "version": self.version,
            "supported": self.supported,
            "blockers": [b.as_dict() for b in self.blockers],
            "caveats": [c.as_dict() for c in self.caveats],
        }


# ---------------------------------------------------------------------------
# Availability
# ---------------------------------------------------------------------------

def check_abaqus_available() -> bool:
    """Same rule core.helpers.check_abaqus uses; re-exported to avoid a cycle."""
    from core.helpers import check_abaqus
    return check_abaqus()


def backend_label(backend: Backend, version: str | None, lang: str | None = None) -> str:
    return ("Abaqus %s" % version if version
            else messages.render("backend.label.abaqus_unknown_version", lang))


# ---------------------------------------------------------------------------
# Refusals
# ---------------------------------------------------------------------------

def _limit(feature: str, value: str, key: str, *, kind: str = "blocker",
           **params) -> Limitation:
    """Build a refusal that can be read back in either language.

    ``reason`` stays the rendered Chinese, because that is what every existing
    reader — tests, CLI output, archived result.json files — already expects.
    The key rides along so the browser can render the same refusal in English
    without the backend having to know which language this particular reader
    speaks; a refusal outlives the request that produced it.
    """
    return Limitation(feature, value, messages.render(key, "zh", **params),
                      kind, reason_key=key, reason_params=params)



# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------

def select_backend(
    spec: dict | None = None,
    *,
    abaqus_available: bool | None = None,
    override: str | None = None,
) -> BackendDecision:
    """Decide whether this spec can be run, and say why not when it cannot.

    There is one backend. This is an Abaqus agent: without Abaqus there is
    nothing to drive, so the honest answer is a refusal that names the
    environment variable to set — not a second solver, and not a walkthrough
    that looks like a run.

    The returned decision is always ``abaqus``; ``supported`` is False when it
    could not be found, and ``blockers`` carries the sentence to show the user.
    """
    if abaqus_available is None:
        abaqus_available = check_abaqus_available()

    requested = (override or "").strip().lower() or None
    source = "runner_cfg" if requested else "auto"
    if not requested:
        env_value = os.environ.get(ENV_BACKEND, "").strip().lower()
        if env_value and env_value != "auto":
            requested = env_value
            source = "env"

    if requested and requested != BACKEND_ABAQUS:
        return BackendDecision(
            backend=BACKEND_ABAQUS,
            label=backend_label(BACKEND_ABAQUS, None),
            reason=messages.render("backend.select.bad_env_value", "zh",
                                   env=ENV_BACKEND, value=requested),
            reason_key="backend.select.bad_env_value",
            reason_params={"env": ENV_BACKEND, "value": str(requested)},
            source=source,
            blockers=(_limit(ENV_BACKEND, str(requested),
                             "backend.select.bad_env_hint", env=ENV_BACKEND),),
        )

    if not abaqus_available:
        return BackendDecision(
            backend=BACKEND_ABAQUS, label=backend_label(BACKEND_ABAQUS, None),
            reason=messages.render("backend.select.abaqus_not_found", "zh",
                                   env=ENV_ABAQUS_CMD),
            reason_key="backend.select.abaqus_not_found",
            reason_params={"env": ENV_ABAQUS_CMD},
            source=source,
            blockers=(_limit(ENV_BACKEND, BACKEND_ABAQUS,
                             "backend.select.abaqus_not_found",
                             env=ENV_ABAQUS_CMD),),
        )

    release = detect_abaqus_release()
    reason_key = ("backend.select.abaqus_auto" if source == "auto"
                  else "backend.select.abaqus_explicit")
    return BackendDecision(
        backend=BACKEND_ABAQUS,
        label=backend_label(BACKEND_ABAQUS, release),
        reason=messages.render(reason_key, "zh"),
        reason_key=reason_key,
        source=source, version=release,
    )


def refusal_messages(decision: BackendDecision,
                     lang: str | None = None) -> list[str]:
    """Plain-language refusal lines for the console / UI / API error payload."""
    lang = messages.resolve_lang(lang)
    # The separator is part of the sentence, so it has to follow the language:
    # a full-width colon in an English refusal reads as a typo.
    sep = "：" if lang == "zh" else ": "
    return ["%s = %s%s%s" % (b.feature, b.value, sep, b.localized(lang))
            for b in decision.blockers]


def refusal_fields(decision: BackendDecision) -> dict:
    """The run/result fields a refusal sets, in one place.

    core.pipeline and agent.orchestrator both refuse, and they were building
    the same four keys independently — which is how one of them ends up
    carrying a notice the other does not, and a refusal reads differently
    depending on which door the caller came through.
    """
    return {
        "status": "FAILED",
        "backend": decision.as_dict(),
        "limitations": [b.as_dict() for b in decision.blockers],
        "kpi_notice": "；".join(refusal_messages(decision)),
    }
