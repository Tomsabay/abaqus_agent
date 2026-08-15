"""
workbench/planner.py
--------------------
Chat-driven spec proposal engine for the workbench.

Backends:
  claude_cli - headless `claude -p` call. Uses the local Claude Code login
               (subscription), no API key required.
  template   - keyword template fallback handled by the caller via
               core.spec_generator (offline, deterministic).

The claude_cli functions here are synchronous; callers must wrap them in
asyncio.to_thread (or an executor) to avoid blocking the event loop.
"""

from __future__ import annotations

import difflib
import json
import os
import queue
import re
import shutil
import subprocess
import tempfile
import threading
import time

import yaml

from tools.abaqus_cmd import detect_abaqus_release
from tools.schema_validator import validate_spec
from workbench.planner_dialect import V2_DIALECT as _V2_DIALECT

# Measured (sonnet, 2026-08-11): the modify path runs 50-100 s per call and
# from-scratch cantilever-class 48-150 s, but the bearing-assembly brief needs
# ~225 s for its plan stage and 420-450+ s per draft/repair call. 180 killed
# the plan stage and 480 killed a repair, so the default cap is 600. Raising
# the cap does not slow successful calls — it only delays failure detection.
CLAUDE_TIMEOUT_SECONDS = int(os.environ.get("ABAQUS_AGENT_CLAUDE_TIMEOUT", "600"))
CLAUDE_MODEL = os.environ.get("ABAQUS_AGENT_CLAUDE_MODEL", "sonnet")
# The from-scratch draft/repair calls transcribe a finished design sheet under
# mechanical format rules — a different task profile from the plan call, which
# makes the engineering decisions and keeps CLAUDE_MODEL. Measured on the
# bearing-assembly brief (2026-08-11): haiku finishes these calls in 165-292 s
# (and, with the ring-part and materials-shape prompt rules, passed schema AND
# the v2 generator with zero repairs) where sonnet needs 420-600+ s per call
# and loses a coin flip against any practical timeout. Set the env to override
# — e.g. to CLAUDE_MODEL's value for a single-model setup.
CLAUDE_DRAFT_MODEL = (os.environ.get("ABAQUS_AGENT_CLAUDE_DRAFT_MODEL")
                      or "haiku")
# Streaming lets the timeout distinguish "still writing" from "dead": the wall
# clock above stays the hard budget per call, and this one kills a call that
# produced NOTHING for that long. Not "a few seconds": the stream carries no
# lines at all while the model thinks, and a from-scratch plan call was
# measured 205 s from send to first text delta (and killed at 120 s of
# line-silence on the retake) — so the floor has to clear a long think while
# still beating the 1021 s hang this exists to catch.
STALL_TIMEOUT_SECONDS = int(os.environ.get("ABAQUS_AGENT_CLAUDE_STALL_TIMEOUT", "300"))
MAX_HISTORY_MESSAGES = 6

_SPEC_MARK = "===SPEC==="
_REPLY_MARK = "===REPLY==="

# meta.abaqus_release is a year enum in schema/spec_schema.json (2019..2026), so
# an unmeasured release cannot be sent to the model as "unknown": it would copy
# the word into the spec, validation would fail on both attempts and the user
# would get PlannerError instead of a proposal. Same fallback the template path
# uses (workbench/routes.py), and like it, declared as a fallback in the reply
# rather than passed off as a measurement.
_FALLBACK_RELEASE = "2021"

_RELEASE_MEASURED = "（本机实测值，不要自己编版本号）"
_RELEASE_FALLBACK = (
    "（⚠ 本机没探测到 Abaqus，这个版本号是占位默认值、不是实测值。schema 只收 "
    "2019–2026 的年份，填不了 unknown，所以照填——但必须在 REPLY 里写明它未经探测，"
    "并把「实际用哪个 Abaqus 版本」写进 meta.missing_questions）")


_PROMPT_TEMPLATE = """你是 Abaqus 有限元自动化 planner。根据用户指令，生成或修改 Problem Spec YAML。

spec 有两种方言，schema 二选一，**不许混写**（v2 里出现 geometry 或 bc_load 直接被拒）：
- v1：meta + geometry + material + analysis + bc_load + outputs。四种写死的形状，
  一个零件、一个分析步、一个固定面、一个载荷。
- v2：meta + material + parts + assembly + steps + outputs。零件由特征拼出来，
  装配任意多个实例，多分析步、多条边界条件和载荷，可以有接触和绑定。

## 第一步：选方言
用 v1：题目正好落在 cantilever_block / plate_with_hole / axisymmetric_disk /
  custom_inp 之一，单零件、Static、载荷是 pressure / concentrated_force /
  displacement 三种之一。
用 v2：只要出现下面任何一条 ——
  多于一个零件；有接触或绑定；分析步不是 Static（模态、隐式/显式动力学、传热、屈曲、
  Riks）；载荷 v1 那三种表达不了（力矩、体力、重力、速度边界、预定义温度场…）；
  形状不是那四种（要挖孔、回转、倒圆，任何得自己画出来的零件）。
拿不准就用 v2：v2 能表达 v1 能表达的一切，反过来不成立。

## 公共规则（两个方言都要遵守）
1. meta 只允许 abaqus_release/model_name/units/description/missing_questions。
2. material 只允许 name/E/nu/density/yield/hardening。塑性写 `yield`（**不是** yield_stress），
   hardening 是屈服后的模量（MPa），不能脱离 yield 单独出现。
   conductivity/specific_heat/expansion_coeff/electrical_conductivity **只有 v2 会真的
   写进模型**：v1 的生成器只发 Elastic/Density/Plastic（热物性只在 Coupled_* 步里发，
   而 v1-3 不许用那两种步），schema 却照收——写在 v1 里等于没写，且不报错。
   要热物性就用 v2。
   多材料时顶层 material **仍然必填**（写主材料），其余材料写顶层 materials
   **列表**——不是「材料名到参数」的映射，每项必须带 name（每项也只写上面这些键），
   零件的 section.material 按名字引用。照这个形状写（实测装配 case 的原文）：
     material:
       name: Steel
       E: 210000.0
       nu: 0.3
       density: 7.85e-09
     materials:
       - name: Bronze
         E: 110000.0
         nu: 0.34
         density: 8.80e-09
3. meta.abaqus_release 一律填 "{abaqus_release}"{release_note}，
   model_name 用 CamelCase。
4. 单位默认 mm_MPa_t（力 N、应力 MPa、密度 t/mm^3）。钢默认 E=210000, nu=0.3,
   density=7.85e-9。动力学/模态必须给 material.density。
5. outputs.kpis 至少一条；每条必须有 name 和 type；type 只能用这几种：
     nodal_displacement | field_max | field_min | reaction_force_max
     history_output_max | eigenfrequency | eigenvalue
     derived_stress_concentration | contour_integral_j
   可选 component(U1|U2|U3|S11|S22|S33|RF1|RF2|RF3)、invariant: MISES、
   field_variable、reducer(max|min|sum|mean|last|abs_max)；
   history_output_max 另需 variable(历史变量名，如 ALLPD)；
   eigenvalue 读屈曲特征值（*BUCKLE 步），eigenfrequency 读模态频率，两者别混。
   contour_integral_j 读 `*Contour Integral` 的 J，`location` 写 ContourIntegral
   的名字；裂缝怎么建见上面「二维零件与裂纹」，已经实测通了。
6. 禁止发明 schema 之外的字段（schema 会拒绝），也禁止把表达不了的东西换个"差不多"的
   写法糊过去。这套文法说不出来的要求，就在 REPLY 里直说这一条做不到、缺的是哪个键，
   宁可拒绝也不能给一个自信的错答案。
7. 已有当前 spec 时做最小修改，保留用户之前定下的参数；没有时从头生成。
8. 信息不足就先用合理默认值并在 REPLY 里说明假设，不要拒绝生成。
9. REPLY 里给理论估算必须先列公式、逐步代入当前 spec 的实际数值算一遍再报数；
   数值计算一律用科学计数法逐因子核对指数（例：10^6/(5.25×10^8)=1.9×10^-3 mm），
   指数加减单独验算一遍。心算没把握就只给公式不给数字，报错的数字比不报更伤可信度。

## v1 方言
v1-1. 六个顶层键必须齐全：meta, geometry, material, analysis, bc_load, outputs。
v1-2. geometry.type 只能用：cantilever_block | plate_with_hole | axisymmetric_disk | custom_inp。
   - cantilever_block: L(长) W(宽) H(高) seed_size
   - plate_with_hole:  L(半长) W(半宽) R(孔半径) seed_size
   - axisymmetric_disk: L(高) R(外径) seed_size
v1-3. analysis.step_type 只能用：Static | Frequency | Dynamic_Explicit | Dynamic_Implicit；
   analysis.solver 只能用：standard | explicit；模态分析可给 analysis.num_eigenmodes（整数）。
   analysis 只允许 solver/step_type/cpus/mp_mode/memory/time_period/num_eigenmodes/nlgeom。
v1-4. bc_load.load_type 只能用：pressure | concentrated_force | displacement。
   bc_load.direction 是单个整数自由度 1|2|3（1=X 2=Y 3=Z），不是向量。
   载荷方向的正负放在 value 的符号里（如向下 = direction: 2, value: -1.0）。
   显式给出 fixed_face 和 load_face；cantilever_block 梁轴沿 z，用 "z=0"、"z=L"；
   plate_with_hole 是四分之一对称模型，fixed_face 固定写 "x=0_symmetry"，
   load_face "x=L"，拉伸用 load_type: pressure、value 取负（如 -100 表示 100 MPa 拉）。
v1-5. outputs.kpis 的 location 只能用已知别名：tip_center(悬臂尖端) |
   whole_model(全模型) | mode_N(第N阶模态)，不要自造表达式。

## v2 方言（装配）
v2 顶层：meta, material, parts, assembly, steps, outputs 必写；
interactions, conditions, materials, analysis 可选。
**v2 里不许出现 geometry 和 bc_load。** analysis 可以整块不写（solver 默认 standard）；
写了就只能写 solver（外加 cpus/mp_mode/memory），**绝对不许写 step_type**——
分析步类型由 steps 自己说，两处说同一件事就是两处会打架。

{v2_dialect}

## 输出格式（严格两段，段外不写任何字）
{spec_mark}
<完整 YAML，不要代码围栏——上面示例里的 ```yaml 只是为了让你读清楚>
{reply_mark}
<两三句中文：改了什么、关键假设、预期看什么结果>

## 当前 spec
{current_spec}

## 最近对话
{history}

{selection}## 用户指令
<<<
{instruction}
>>>
"""

_RETRY_SUFFIX = """

## 上一次输出未通过 schema 校验，错误如下，请修正后按同样格式重新输出
{errors}
"""

# From-scratch generation measured three consecutive failures as ONE call
# (180 s timeout / 900 s read timeout / >11 min no response, 2026-08-11) while
# the modify path finishes in 50-100 s. The difference is not output length —
# both emit a whole spec — it is that modifying transcribes an existing spec
# and from-scratch has to DESIGN one. So design is split out into its own
# small, dialect-free call; the draft call then transcribes the design sheet,
# which is the shape the fast path already has.
_PLAN_TEMPLATE = """你是资深有限元工程师。把下面的用户需求拆成一份**设计清单**——只做工程决策，
不写 spec、不写代码。后续会有第二步照这份清单落成机器可校验的 spec。

## 平台边界（设计时就要避开，否则第二步落不了稿）
- 零件默认形态：XY 平面草图沿 +z 拉伸的实体（零件的"长度"方向是 z）；
  挖切只支持圆孔，没有矩形槽。回转体等其他形状可以用 Abaqus API 通用调用，
  但每个这样的零件必须能报出体积等可核对的量。
- 圆筒/衬套这类圆环截面零件**能表达**：同一张草图画两个同心圆再整体拉伸
  （通用草图实体形式），不要判成「画不出来」。
- 文件导入（STEP/IGES/orphan mesh）**只有用户明确给了文件才许用**；用户没给，
  就必须用草图特征把形状画出来，不许把「请用户提供 CAD 文件」当成解法。
- 零件之间不写连接就是互不相干；绑定（tie，焊死）与接触（可分开、可滑动、可带摩擦）
  都要指明两个面，用「某实例沿某轴 min/max 的面」或「半径 r 的孔壁」这种可定位的说法。
- 每个分析步说清：类型（静力/模态/传热…）、这一步新增的载荷与边界、数值和方向。
- 载荷用总量表述时给出受力面积或节点数，方便换算成压强或每节点力。
- 单位制固定 mm-MPa-t（长度 mm、应力 MPa、密度 t/mm³、力 N），除非用户另有明说。
- 用户没给的信息（材料参数、尺寸、摩擦系数…）：给保守假设，并列入「假设与待确认」。
- 需求若以「已有模型」为前提（改参数、换载荷…）而当前没有任何模型可改，这次就是
  从零新建：把这一点写进【假设与待确认】第一条，能从需求确定的部分照常设计。

## 输出格式（就按这些小节写，不要加别的）
【模型名】一个英文驼峰名
【单位制】
【材料】每种一行：名 / E / nu / density（要算自重或模态才需要 density）
【零件】每个零件：名、外形与尺寸、特征顺序（草图→拉伸→挖孔…）、网格尺寸建议
【装配】每个实例：名、用哪个零件、平移/旋转到哪
【相互作用】每条：类型（tie/接触）、哪两个面、摩擦系数/容差
【分析步】按顺序每步：名、类型、新增载荷（类型/作用面/数值）、边界条件
【输出】要抽的 KPI：名、量（支反力/位移/Mises…）、在哪读、读哪一步
【假设与待确认】用户没说、你替他定了的每一条

## 最近对话
{history}

{selection}## 用户需求
<<<
{instruction}
>>>
"""


class PlannerUnavailable(RuntimeError):
    """claude CLI not installed / not on PATH."""


class PlannerError(RuntimeError):
    """claude CLI ran but produced unusable output."""


def claude_cli_available() -> bool:
    return shutil.which("claude") is not None


def build_prompt(instruction: str, current_spec_yaml: str | None,
                 history: list[dict] | None,
                 selection: list[dict] | None = None) -> str:
    """`selection` is the resolved @-mention list from workbench.selection —
    already-fetched spec fragments, never raw refs. The section is injected as
    a format ARGUMENT rather than pasted into the template, so YAML fragments
    containing braces cannot break .format()."""
    lines = []
    for msg in (history or [])[-MAX_HISTORY_MESSAGES:]:
        role = "用户" if msg.get("role") == "user" else "助手"
        text = str(msg.get("text", ""))[:500]
        lines.append(f"[{role}] {text}")
    release = detect_abaqus_release()
    from workbench.selection import prompt_section
    sel_text = prompt_section(selection or [])
    return _PROMPT_TEMPLATE.format(
        spec_mark=_SPEC_MARK,
        reply_mark=_REPLY_MARK,
        v2_dialect=_V2_DIALECT,
        abaqus_release=release or _FALLBACK_RELEASE,
        release_note=_RELEASE_MEASURED if release else _RELEASE_FALLBACK,
        current_spec=current_spec_yaml or "（无——首次生成）",
        history="\n".join(lines) or "（无）",
        selection=sel_text + "\n" if sel_text else "",
        instruction=instruction,
    )


def _kill_tree(proc: subprocess.Popen) -> None:
    """Kill the whole process tree. Killing only the direct child leaves the
    node grandchild of the npm .CMD shim writing into the pipe, and the read
    then blocks on it — a 480 s cap was measured taking 1021 s to come back."""
    if os.name == "nt":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL)
    else:
        proc.kill()


def _spawn_claude(model: str | None, stream: bool) -> subprocess.Popen:
    exe = shutil.which("claude")
    if not exe:
        raise PlannerUnavailable("claude CLI not on PATH")
    cmd = [exe, "-p", "--model", model or CLAUDE_MODEL]
    if stream:
        # stream-json emits one JSON object per line as the model writes;
        # --include-partial-messages adds the token-level text deltas and
        # --verbose is required by the CLI for stream-json output.
        cmd += ["--output-format", "stream-json",
                "--include-partial-messages", "--verbose"]
    try:
        # Prompt goes through stdin: the npm claude.CMD shim mangles multi-line
        # argv on Windows (cmd.exe truncates at the first newline). An explicit
        # input pipe also avoids inheriting any parent stdio handles.
        # cwd is a neutral temp dir so the CLI does not load this repo's
        # project context (CLAUDE.md, skills) into every planning call.
        return subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
            errors="replace",
            cwd=tempfile.gettempdir(),
        )
    except OSError as e:
        raise PlannerUnavailable(f"claude CLI failed to start: {e}") from e


def _parse_stream_line(line: str) -> tuple[str | None, str | None, str | None]:
    """One stream-json line → (text_delta, thinking_delta, final_result).

    Three shapes matter. `stream_event` wraps the raw API stream, which carries
    TWO kinds of delta: `text_delta` is the answer, `thinking_delta` is the
    model reasoning before it. The terminal `result` object repeats the whole
    answer — authoritative, because deltas can be missed if the CLI changes its
    event framing.

    Thinking is forwarded separately and never joined into the answer: it is
    what fills the minutes before the first word (measured on a plan call: 176
    thinking deltas from 6 s to 177 s, then the first text_delta), but it is
    prose about the work, not the work — feeding it to parse_response would
    hand the YAML parser the model's musings.
    """
    try:
        obj = json.loads(line)
    except ValueError:
        return None, None, None
    if not isinstance(obj, dict):
        return None, None, None
    if obj.get("type") == "stream_event":
        event = obj.get("event") or {}
        if event.get("type") == "content_block_delta":
            delta = event.get("delta") or {}
            if delta.get("type") == "text_delta":
                return delta.get("text") or "", None, None
            if delta.get("type") == "thinking_delta":
                return None, delta.get("thinking") or "", None
    if obj.get("type") == "result":
        return None, None, str(obj.get("result") or "")
    return None, None, None


def _stream_claude(prompt: str, model: str | None, on_text, on_think=None) -> str:
    """Run the CLI in stream-json mode, forwarding deltas as they arrive.

    on_text gets the answer; on_think (optional) gets the reasoning that
    precedes it — without the second one the UI has nothing to show for the
    first ~3 minutes of a from-scratch plan, which is most of the wait.

    Reader threads pump stdout/stderr into one queue (a blocked pipe read
    cannot honor any deadline on Windows); the consumer loop enforces both the
    wall-clock budget and the stall budget, and a breach kills the whole tree."""
    proc = _spawn_claude(model, stream=True)
    lines: queue.Queue = queue.Queue()

    def _pump(stream, tag: str) -> None:
        for line in iter(stream.readline, ""):
            lines.put((tag, line))
        lines.put((tag, None))

    threading.Thread(target=_pump, args=(proc.stdout, "out"), daemon=True).start()
    threading.Thread(target=_pump, args=(proc.stderr, "err"), daemon=True).start()

    def _feed() -> None:
        # Its own thread: a pipe write blocks once the ~4 KB buffer fills
        # (prompts measure 32+ KB), so a CLI that hangs before reading stdin
        # would hang the CALLER before either timeout below starts counting.
        # When a timeout kills the tree, this write fails and the thread
        # exits; the consumer loop is the one that reports.
        try:
            proc.stdin.write(prompt)
            proc.stdin.close()
        except OSError:
            pass

    threading.Thread(target=_feed, daemon=True).start()

    deadline = time.monotonic() + CLAUDE_TIMEOUT_SECONDS
    chunks: list[str] = []
    final: str | None = None
    stderr_tail: list[str] = []
    open_streams = 2
    while open_streams:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            _kill_tree(proc)
            raise PlannerError(
                f"claude CLI timed out after {CLAUDE_TIMEOUT_SECONDS}s")
        try:
            tag, line = lines.get(timeout=min(remaining, STALL_TIMEOUT_SECONDS))
        except queue.Empty:
            _kill_tree(proc)
            raise PlannerError(
                f"claude CLI stalled: no output for {STALL_TIMEOUT_SECONDS}s "
                f"({len(chunks)} deltas received before the silence)")
        if line is None:
            open_streams -= 1
            continue
        if tag == "err":
            stderr_tail.append(line)
            del stderr_tail[:-20]
            continue
        delta, thinking, result = _parse_stream_line(line)
        if delta:
            chunks.append(delta)
            on_text(delta)
        if thinking and on_think is not None:
            on_think(thinking)
        if result is not None:
            final = result
    try:
        proc.wait(timeout=15)
        exit_ok = proc.returncode == 0
    except subprocess.TimeoutExpired:
        # Both pipes hit EOF but the process would not exit (node exit hooks,
        # the npm shim's cmd.exe lingering). If the CLI already delivered its
        # terminal `result` event, this is cleanup, not failure — kill the
        # tree and keep the output. Without that event, it IS a failure.
        _kill_tree(proc)
        exit_ok = final is not None
    if not exit_ok:
        detail = ("".join(stderr_tail) or "".join(chunks)).strip()[:400]
        raise PlannerError(f"claude CLI exit {proc.returncode}: {detail}")
    out = (final if final and final.strip() else "".join(chunks)).strip()
    if not out:
        raise PlannerError("claude CLI returned empty output")
    return out


def _call_claude(prompt: str, model: str | None = None, on_text=None,
                 on_think=None) -> str:
    if on_text is not None:
        return _stream_claude(prompt, model, on_text, on_think)
    proc = _spawn_claude(model, stream=False)
    try:
        stdout, stderr = proc.communicate(prompt, timeout=CLAUDE_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired as e:
        _kill_tree(proc)
        proc.communicate()
        raise PlannerError(f"claude CLI timed out after {CLAUDE_TIMEOUT_SECONDS}s") from e
    if proc.returncode != 0:
        detail = (stderr or stdout or "").strip()[:400]
        raise PlannerError(f"claude CLI exit {proc.returncode}: {detail}")
    out = (stdout or "").strip()
    if not out:
        raise PlannerError("claude CLI returned empty output")
    return out


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    match = re.match(r"^```[a-zA-Z]*\n(.*?)\n?```$", text, re.DOTALL)
    return match.group(1) if match else text


def parse_response(raw: str) -> tuple[str, str]:
    """Split the two-section response into (spec_yaml, reply)."""
    if _SPEC_MARK not in raw:
        raise PlannerError(f"missing {_SPEC_MARK} marker in output: {raw[:200]}")
    after_spec = raw.split(_SPEC_MARK, 1)[1]
    if _REPLY_MARK in after_spec:
        spec_part, reply_part = after_spec.split(_REPLY_MARK, 1)
    else:
        spec_part, reply_part = after_spec, ""
    spec_yaml = _strip_code_fence(spec_part)
    reply = reply_part.strip() or "已生成 spec 提案。"
    if not spec_yaml.strip():
        raise PlannerError("empty spec section in output")
    return spec_yaml.strip() + "\n", reply


def build_plan_prompt(instruction: str, history: list[dict] | None,
                      selection: list[dict] | None = None) -> str:
    """The design-stage prompt: no dialect doc, no output-format contract —
    the whole point is that this call is small enough to come back."""
    lines = []
    for msg in (history or [])[-MAX_HISTORY_MESSAGES:]:
        role = "用户" if msg.get("role") == "user" else "助手"
        lines.append(f"[{role}] {str(msg.get('text', ''))[:500]}")
    from workbench.selection import prompt_section
    sel_text = prompt_section(selection or [])
    return _PLAN_TEMPLATE.format(
        history="\n".join(lines) or "（无）",
        selection=sel_text + "\n" if sel_text else "",
        instruction=instruction,
    )


def _builder_errors(spec: dict) -> list[str]:
    """v2 specs get the generator's own lint, not just the schema: a measured
    proposal passed the schema with `local_seeds: face@r=12` and was refused
    only when the user tried to use it — the whole class of named [SPEC_INVALID]
    rejections belongs in the repair loop, where a retry can fix it. Pure
    Python (no CAE, no solver), so it is cheap and hermetic."""
    if "parts" not in spec:
        return []
    from runner import build_v2
    try:
        build_v2.generate_script(spec)
    except Exception as e:  # the builder names its refusals; relay verbatim
        return [str(e)[:500]]
    return []


def _generate_validated(prompt: str, attempts: int,
                        notify=lambda stage: None,
                        model: str | None = None,
                        on_text=None, on_think=None) -> tuple[dict, str, str]:
    """Call the CLI, parse, validate; re-ask with the error list on failure.

    Every failed attempt's errors are carried into whatever error finally
    surfaces: a run was measured burning 35 minutes on two invalid drafts plus
    a timeout, and the timeout alone reached the report — the two validation
    error lists, the only clue to WHY the drafts were invalid, were lost."""
    last_errors: list[str] = []
    attempt_log: list[str] = []
    for attempt in range(attempts):
        if attempt:
            notify("repair-%d" % attempt)
        ask = prompt if attempt == 0 else prompt + _RETRY_SUFFIX.format(
            errors="\n".join(f"- {e}" for e in last_errors))
        try:
            raw = _call_claude(ask, model=model, on_text=on_text,
                               on_think=on_think)
        except PlannerError as e:
            if attempt_log:
                raise PlannerError("%s（此前尝试：%s）"
                                   % (e, "；".join(attempt_log))) from e
            raise
        spec_yaml, reply = parse_response(raw)
        try:
            spec = yaml.safe_load(spec_yaml)
        except yaml.YAMLError as e:
            last_errors = [f"YAML parse error: {e}"]
        else:
            if not isinstance(spec, dict):
                last_errors = ["output is not a YAML mapping"]
            else:
                valid, errors = validate_spec(spec)
                if valid:
                    errors = _builder_errors(spec)
                if not errors:
                    return spec, yaml.dump(spec, allow_unicode=True,
                                           default_flow_style=False,
                                           sort_keys=False), reply
                last_errors = errors
        attempt_log.append("第%d次输出未过校验：%s" % (
            attempt + 1, "; ".join(e[:160] for e in last_errors[:3])))
    raise PlannerError("spec failed validation after retry: "
                       + "; ".join(last_errors[:5]))


_STAGED_SUFFIX = ("\n\n## 设计清单（第一步已做完的工程决策，照它落稿；清单没提的"
                  "按方言规则取默认；「假设与待确认」写进 meta.missing_questions——"
                  "schema 上限 5 条，超出就合并同类、保留最重要的 5 条，"
                  "完整清单本来就会原样出现在给用户的回复里）\n")


def plan_with_claude(instruction: str, history: list[dict] | None,
                     selection: list[dict] | None = None,
                     on_text=None, on_think=None) -> str:
    """Stage 1 of from-scratch: the dialect-free design sheet. Split out as its
    own callable so the chat flow can STOP here and let the user read (and
    edit) the sheet before any drafting time is spent on its assumptions."""
    try:
        return _call_claude(build_plan_prompt(instruction, history, selection),
                            on_text=on_text, on_think=on_think).strip()
    except PlannerError as e:
        raise PlannerError("规划（plan）阶段失败：%s" % e) from e


def draft_with_claude(instruction: str, plan: str,
                      history: list[dict] | None,
                      selection: list[dict] | None = None,
                      progress=None, on_text=None,
                      on_think=None) -> tuple[dict, str, str]:
    """Stage 2: transcribe a (possibly user-edited) design sheet into a spec
    under the full dialect rules, with the validation-repair budget."""
    notify = progress or (lambda stage: None)
    notify("draft")
    prompt = build_prompt(instruction + _STAGED_SUFFIX + plan,
                          None, history, selection)
    try:
        spec, spec_yaml, reply = _generate_validated(
            prompt, attempts=3, notify=notify, model=CLAUDE_DRAFT_MODEL,
            on_text=on_text, on_think=on_think)
    except PlannerError as e:
        raise PlannerError("落稿（draft）阶段失败：%s" % e) from e
    return spec, spec_yaml, "【设计清单】\n%s\n\n【落稿说明】\n%s" % (plan, reply)


def propose_with_claude(instruction: str, current_spec_yaml: str | None,
                        history: list[dict] | None,
                        selection: list[dict] | None = None,
                        progress=None, on_text=None,
                        on_think=None) -> tuple[dict, str, str]:
    """
    Returns (spec_dict, spec_yaml, reply). Raises PlannerUnavailable/PlannerError.

    With a current spec this is one call plus one validation retry — measured
    fast. From scratch it is staged (plan → draft → repair) and auto-chained:
    this entry point never pauses, which is what the non-interactive callers
    (the check script, the plain POST endpoint) want. The interactive SSE flow
    calls plan_with_claude / draft_with_claude itself so the user can confirm
    the design sheet in between. `progress` gets a stage name before each CLI
    call; `on_text` gets every streamed answer delta and `on_think` every
    reasoning delta.
    """
    notify = progress or (lambda stage: None)
    if current_spec_yaml:
        notify("draft")
        prompt = build_prompt(instruction, current_spec_yaml, history, selection)
        return _generate_validated(prompt, attempts=2, notify=notify,
                                   on_text=on_text, on_think=on_think)

    notify("plan")
    plan = plan_with_claude(instruction, history, selection, on_text=on_text,
                            on_think=on_think)
    return draft_with_claude(instruction, plan, history, selection,
                             progress=progress, on_text=on_text,
                             on_think=on_think)


def make_diff(old_yaml: str | None, new_yaml: str) -> str:
    old_lines = (old_yaml or "").splitlines(keepends=True)
    new_lines = new_yaml.splitlines(keepends=True)
    diff = difflib.unified_diff(
        old_lines, new_lines,
        fromfile="当前 spec", tofile="提案 spec", lineterm="\n",
    )
    return "".join(diff)
