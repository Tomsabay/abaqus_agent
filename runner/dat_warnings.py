"""Read the .dat for the warnings that mean the model is not the spec's model.

Abaqus writes three kinds of thing to the .dat: notes, warnings about how the
analysis ran, and warnings about what the analysis actually contains. Only the
third kind matters here, and it is the one nothing else in this pipeline looks
at. A `*Tie` whose slave nodes fall outside the position tolerance is left
untied; the job runs, converges, writes a full .odb, and reports COMPLETED. The
only trace is a warning three hundred lines into a file nobody opens.

Measured on this repository's own bearing_block case: a bore tie between two
faceted approximations of the same r=12 cylinder, meshed at different seeds,
dropped enough slave nodes that Abaqus stopped listing them ("SUPPRESSED DUE TO
EXCESSIVE REPORTING"). All three equilibrium identities still passed, because
equilibrium does not care which nodes carry the load. That is the whole problem:
the checks that were in place could not see it, and the run read as clean.

Two design points worth stating:

  * The signatures are matched on the part of the message Abaqus does not vary,
    and the numbers in them are extracted rather than matched. A signature list
    that had to be updated for every node number would be a list that silently
    stops matching.
  * When Abaqus suppresses repeats, the count reported here is a LOWER BOUND and
    says so. Reporting "11 nodes were not tied" when the real number is unknown
    and larger would be a smaller lie than silence, but still a lie.
"""

from __future__ import annotations

import re
from pathlib import Path

# A warning block starts with ***WARNING: and continues on the indented lines
# that follow it. Notes and errors have their own markers.
_START = re.compile(r"^\s*\*\*\*(WARNING|ERROR|NOTE):\s*(.*)$")
_SUPPRESSED = re.compile(r"SUPPRESSED DUE TO EXCESSIVE REPORTING")

# Everything Abaqus varies between two instances of the same warning: node and
# element numbers, set names, counts. Stripped so that a hundred reports of one
# problem group into one finding with a count, instead of a hundred findings.
_VARIABLE = re.compile(r"\b\d+\b")

# Some warnings report one block for many items -- "74 nodes are either missing
# intersection..." is a single block covering 74 nodes. Counting blocks and
# calling it the number of affected nodes understates it by 73. When the message
# opens with its own count, that count is the one to report.
_STATED_TOTAL = re.compile(r"^(\d+)\s+(nodes?|elements?)\b", re.IGNORECASE)


def _normalise(text: str) -> str:
    return _VARIABLE.sub("#", " ".join(text.split())).strip().upper()


# What each recognised signature means, and whether it says the model differs
# from the spec. `integrity` is the distinction that matters: an integrity
# finding means a constraint, a section or a surface did not take effect, and
# every number downstream of it describes a different model than the one the
# spec asked for.
#
# A signature not in this table is still reported -- see `parse_dat_warnings` --
# because "we did not recognise this warning" and "there was no warning" must
# never look the same.
SIGNATURES = (
    {
        "id": "tie_node_outside_tolerance",
        "match": "WILL NOT BE TIED TO THE MASTER",
        "integrity": True,
        "what": "绑定约束有从面节点没被绑上：这些节点到主面的距离超过了 position "
                "tolerance，Abaqus 直接把它们留成自由的，作业照常收敛。",
        "why": "两个面若是同一个曲面的网格离散，刻面弦高会随种子变粗而增大；"
               "种子不同的两侧刻面不重合，间隙可以远大于容差。也可能是零件真的"
               "没对齐。",
        "fix": "先看间隙是刻面造成的还是装配位置造成的：曲面上给两侧都加局部种子"
               "把弦高压下去，再把 position_tolerance 设在弦高之上、真实错位之下。"
               "调大容差而不查原因，等于把这个检查关掉。",
    },
    {
        "id": "nodes_miss_master_intersection",
        "match": "MISSING INTERSECTION WITH THEIR RESPECTIVE",
        "integrity": True,
        "what": "有从面节点在主面上找不到投影点，或落在调整区之外——这些节点"
                "没有参与约束。Abaqus 把它们收进节点集 "
                "WarnNodeMissMasterIntersect，除此之外不再提。",
        "why": "主面比从面小（选面时少选了一块），或者两个面是同一曲面的不同"
               "离散，刻面之间对不上。",
        "fix": "先在 CAE 里显示 WarnNodeMissMasterIntersect 看它们在哪：集中在"
               "边缘说明主面选小了，散布在整个面上说明是刻面问题。",
    },
    {
        "id": "overconstraint_removed",
        "match": "OVERCONSTRAINT CHECKS",
        "integrity": True,
        "what": "有自由度被多个约束同时控制，Abaqus 自行删掉了其中一部分。",
        "why": "同一个面既参与 tie 又参与接触，或者边界条件与 tie 重叠。",
        "fix": "看 .dat 里紧随其后的清单，确认被删掉的是不需要的那一个。",
    },
    {
        "id": "unconnected_regions",
        "match": "UNCONNECTED REGIONS",
        "integrity": True,
        "what": "网格里有互相不连通的区域——模型被分成了几块互不相干的东西。",
        "why": "零件之间只靠几何贴合、没有 tie 或接触把它们连起来。",
        "fix": "检查装配里每一对相接的面是不是都有约束。",
    },
    {
        "id": "elements_without_section",
        "match": "ELEMENTS HAVE MISSING PROPERTY DEFINITIONS",
        "integrity": True,
        "what": "有单元没有截面属性。",
        "why": "截面指派用的集合没覆盖到全部单元。",
        "fix": "截面指派的区域改成整个零件的 cells。",
    },
    {
        "id": "zero_pivot",
        "match": "ZERO PIVOT",
        "integrity": True,
        "what": "刚度矩阵有零主元：模型里有没被约束住的刚体自由度。",
        "why": "某个零件只靠接触或摩擦定位，接触压力为零的那一刻它是自由的。",
        "fix": "在第一个分析步之前把它约束住，或改用位移控制。",
    },
    {
        "id": "excessive_distortion",
        "match": "EXCESSIVE DISTORTION",
        "integrity": False,
        "what": "单元畸变过大。",
        "why": "网格质量不足以承受这一步的变形量。",
        "fix": "加密网格或减小增量步。",
    },
    {
        "id": "distorted_elements",
        "match": "ELEMENTS ARE DISTORTED",
        "integrity": False,
        "what": "有单元形状超出建议范围（等参角或雅可比），集合 "
                "WarnElemDistorted。结果仍然算得出来，精度在这些单元附近下降。",
        "why": "自由网格在薄壁或尖角处生成了瘦长单元。",
        "fix": "在这些位置加局部种子，或换用二次单元。",
    },
)


def classify(message: str) -> dict | None:
    """The signature a warning matches, or None when none of them do."""
    upper = " ".join(message.split()).upper()
    for signature in SIGNATURES:
        if signature["match"] in upper:
            return signature
    return None


def parse_dat_warnings(dat_path: str | Path) -> dict:
    """Group a .dat's warnings into findings.

    Returns ``{"findings": [...], "unrecognised": [...], "suppressed": bool,
    "integrity_count": int, "dat_path": str, "read": bool}``.

    ``read`` is False when the file is not there. A missing .dat is not an
    absence of warnings and must not be reported as one -- the caller decides
    whether that is expected (a build that never reached the solver) or a
    problem (a solve that claims to have finished).
    """
    path = Path(dat_path)
    empty = {"findings": [], "unrecognised": [], "suppressed": False,
             "integrity_count": 0, "dat_path": str(path), "read": False}
    if not path.exists():
        return empty

    text = path.read_text(encoding="utf-8", errors="replace")
    blocks = _warning_blocks(text)

    grouped: dict = {}
    unrecognised: dict = {}
    # Searched on the whitespace-flattened text, not the raw file. Abaqus wraps
    # this note across two lines -- "SUPPRESSED DUE TO EXCESSIVE" ends one line
    # and "REPORTING" starts the next -- so a search of the raw text finds
    # nothing and the run reports an exact count for something Abaqus stopped
    # counting. Measured on bearing_block: eleven untied nodes were listed and
    # the note sat on line 205.
    suppressed = bool(_SUPPRESSED.search(" ".join(text.split())))

    for message in blocks:
        signature = classify(message)
        key = _normalise(message)
        if signature is None:
            entry = unrecognised.setdefault(
                key, {"count": 0, "example": " ".join(message.split())})
            entry["count"] += 1
            continue
        entry = grouped.setdefault(signature["id"], {
            "id": signature["id"],
            "integrity": signature["integrity"],
            "count": 0,
            "items": 0,
            "example": " ".join(message.split()),
            "what": signature["what"],
            "why": signature["why"],
            "fix": signature["fix"],
        })
        entry["count"] += 1
        stated = _STATED_TOTAL.match(" ".join(message.split()))
        entry["items"] += int(stated.group(1)) if stated else 1

    findings = sorted(grouped.values(),
                      key=lambda f: (not f["integrity"], -f["items"]))
    for finding in findings:
        # Suppression stops the per-node listing, so only a finding reported one
        # block per item loses its total to it. A warning that states its own
        # count states it once and states it in full.
        finding["count_is_lower_bound"] = (
            suppressed and finding["items"] == finding["count"])
    return {
        "findings": findings,
        "unrecognised": sorted(unrecognised.values(),
                               key=lambda e: -e["count"]),
        "suppressed": suppressed,
        "integrity_count": sum(f["items"] for f in findings if f["integrity"]),
        "dat_path": str(path),
        "read": True,
    }


def _warning_blocks(text: str) -> list:
    """Every ***WARNING block, joined back into one line each.

    Abaqus wraps a warning across as many indented lines as it needs, and the
    continuation lines carry the half of the sentence that says what happened.
    Reading only the first line of each would match on "SLAVE NODE 830 INSTANCE
    BUSHING" and miss "WILL NOT BE TIED".
    """
    blocks = []
    current = None
    for line in text.splitlines():
        match = _START.match(line)
        if match:
            if current is not None:
                blocks.append(current)
            current = match.group(2) if match.group(1) == "WARNING" else None
            continue
        if current is None:
            continue
        if line.strip() and line.startswith((" ", "\t")):
            current += " " + line.strip()
        else:
            blocks.append(current)
            current = None
    if current is not None:
        blocks.append(current)
    return blocks


def limitation_lines(report: dict) -> list:
    """One line per integrity finding, for the channel the UI already polls."""
    lines = []
    for finding in report.get("findings", []):
        if not finding.get("integrity"):
            continue
        count = "至少 %d" % finding["items"] if finding.get(
            "count_is_lower_bound") else str(finding["items"])
        lines.append("%s（%s 处）%s 处理办法：%s"
                     % (finding["what"], count,
                        "计数是下限，Abaqus 因重复过多停止了逐条报告。"
                        if finding.get("count_is_lower_bound") else "",
                        finding["fix"]))
    return lines
