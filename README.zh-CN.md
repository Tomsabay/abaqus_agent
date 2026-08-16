# Abaqus Agent

[English](README.md) | **简体中文**

[![CI](https://github.com/Tomsabay/abaqus_agent/actions/workflows/ci.yml/badge.svg)](https://github.com/Tomsabay/abaqus_agent/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-AGPL--3.0--or--later-blue)](LICENSE)
[![Commercial licence](https://img.shields.io/badge/commercial%20licence-available-FF6B2B)](LICENSING.md)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](pyproject.toml)

**Abaqus 有限元的本地仿真质检与回归框架。**

把每一次 Abaqus 运行变成可复现的实验胶囊：

```text
.inp / spec -> syntaxcheck -> solver -> ODB KPI -> physics contracts -> diff report
```

Abaqus Agent 跑在你自己的 Abaqus 授权环境里。内核是确定性的、可审计的；LLM、MCP 客户端、Codex、Claude Code、网页界面都只是可选前端。

## 60 秒看明白 —— CAE Copilot 工作台

一个 Cursor 风格的 Abaqus/CAE 工作台：用自然语言描述模型（悬臂梁、简支梁三点弯、带孔板拉伸、悬臂梁模态分析），检查生成的动作计划，通过插件桥在 CAE 里执行，模型树、视口截图和报错实时回传。动作失败时给出大白话的报错诊断（15 类 CAE 失败模式），一键让 Copilot 出修复后的计划；求解失败还会自动对作业的 .msg/.sta/.dat 日志跑一遍 Solver Doctor（30+ 已知模式）。每个场景都在真实求解器上用粗网格 demo 做过理论校核：悬臂梁端部位移对 PL^3/3EI、简支梁跨中位移对 PL^3/48EI（都是约 1.3 倍，同一个系统性的网格偏软），带孔板 Kt 2.7 对 Howland 解 3.1，一阶模态频率与 Euler-Bernoulli 解相差 14% 以内，再加上求解失败的诊断链路。

上面这些只是 41 道门禁里的前五道。`python scripts/run_all_real_checks.py` 一条命令全跑完并给出**一个**结论；求解类门禁要 Abaqus，界面类门禁要浏览器，整轮一个多小时。

![CAE Copilot 工作台回放一段真实 Abaqus 会话](docs/assets/copilot_workspace_replay.png)

**看这段 demo 不需要 Abaqus。** 仓库自带一段录好的真实 Abaqus 2021 会话（`evidence/copilot_replay/replay.json` —— 真实的失败、真实的修复、真实的 KPI）：

```bash
pip install -e ".[dev]"
python server.py
# open http://127.0.0.1:8000 -> 01 Abaqus/CAE Copilot -> ▶ 播放真实录像
```

回放走完整个闭环：计划卡片逐字打出、动作状态翻转、模型树生长、真实视口 PNG、一次真实的 stale-lock 失败连同它的诊断卡片、一键修复，以及最终 KPI（最大位移 0.1286 mm，最大 Mises 应力 9.58 MPa）。在装了 Abaqus 的机器上，`python scripts/record_copilot_replay.py` 可以重新实录一遍。

同一个服务还挂着 **workbench**，在
[`http://127.0.0.1:8000/workbench`](http://127.0.0.1:8000/workbench)：直接写或改
spec、看各阶段跑、读 KPI 和 3D 预览。Copilot 那页是对话式的入口，这页是管线本身的
直接视图。

## 为什么做这个

大多数 AI 仿真 demo 盯着"生成一个模型"或"生成一段脚本"。真实的 Abaqus 团队通常卡在更难的问题上：

- 这次运行用的输入文件（.inp）、求解设置、Abaqus 版本、环境，到底对不对？
- ODB 里的 KPI 在不在预期的物理范围内？
- 这次运行和上一版基线相比，变了什么？
- 求解为什么失败？
- 这个结果能不能变成一份可重复产出的报告，交给团队或客户？

Abaqus Agent 要做的，是 Abaqus 工作流里的 `pytest` / CI / diff / 诊断。

## v0.2 方向

现有代码里已经有最早那套 Abaqus 自动化流水线。v0.2 在它之上加一层 Simulation DevOps 内核：

| 能力 | 状态 | 用途 |
|---|---:|---|
| `custom_inp` 优先 | 已实现 | 直接拿客户现成的 `.inp` 进来，不强迫走自然语言/spec 生成。 |
| Experiment Capsule 实验胶囊 | 已实现 | 把输入、产物、哈希、环境和来源信息（provenance）存进 `capsule.json`。 |
| ODB Lens / KPI DSL | MVP 已实现 | 可复用的 KPI 提取配方，为 `.odb` 输出生成 KPI Markdown 报告。 |
| Physics Contracts 物理契约 | MVP 已实现 | 校核 KPI 的区间、方向、相对误差和大小顺序。 |
| Simulation Diff | MVP 已实现 | 对比两次 run/capsule 的输入、KPI、契约、产物和来源信息，给出结构化变更摘要。 |
| Solver Doctor | MVP 已实现 | 从 30+ 已知模式里诊断 `.sta/.msg/.log/.dat` 的失败。 |
| MCP QA Tools | MVP 已实现 | 把 capsule、contract、diff、doctor 内核暴露给 MCP 客户端。 |
| Case Memory 算例记忆 | MVP 已实现 | 按元数据、分面筛选、KPI、契约名/结果、诊断 ID、产物名、相似度信号、按计数排序和最低分阈值，检索并排序本地 run/capsule 历史。 |
| Report Export 报告导出 | MVP 已实现 | 从 capsule、KPI、契约、证据清单和图件产出 Markdown、独立/可打印 HTML、可选 PDF 以及打包 zip 的运行报告，CLI/API/MCP/UI 都能调。 |
| Environment Preflight 环境预检 | MVP 已实现 | 真实验证之前先记录操作系统、Python、Abaqus 命令、release 探测、期望版本是否匹配、工作目录可写性、license 标记和 runner 配置证据，CLI/API/MCP/UI 都能调。 |

项目往哪走，以及"什么时候算从'代码路径存在'变成'支持'"的判定规则，见 [docs/ROADMAP.md](docs/ROADMAP.md)。

## 建模层 —— 通用派发，以及它底下的真值层

上面那四个场景是 Copilot 的场景库，不是引擎的上限。底下是一套描述 `parts` /
`assembly` / `interactions` / `steps` / `conditions` 的 spec 方言，它**不靠一份写死的
支持清单**工作——spec 直接点名要调的 Abaqus 方法和要传的参数：

```yaml
parts:
  - name: Flange
    features:
      - op: sketch
        id: profile
        entities: [ ... ]
      - call: BaseSolidRevolve
        sketch: {sketch: profile}
        angle: 360.0
        flipRevolveDirection: "OFF"
    expect: {volume: 26389.378290154, cells: 1, faces: 4}
```

剩下的交给 `getattr(part, "BaseSolidRevolve")(**kwargs)`。Abaqus 在 `Part` 上暴露
292 个可调对象、在 `ConstrainedSketch` 上 71 个，且每个版本都在长；把它们枚举进
schema，等于这套方言永远只能建别人已经写过分支的形状。

这么做能站得住，前提是底下有东西接着——通用派发交出去的，正是"schema 知道每个调用
**本该**产出什么"。所以换成 `expect:` 块，拿建出来的模型逐项核对：

| 层 | 核对什么 |
|---|---|
| 几何 | 体积、cell 数、面数、圆柱面数、某个特征落在哪 |
| 网格 | 单元数、形状质量准则、以及某准则**没适用到**多少单元 |
| 装配 | 实例数、每个实例最终在哪、新造的零件有没有进分析 |
| 接触 | 接触对那两个面之间的实测间隙 |

这些真值层针对的失败都不是假想的，每一条都是实测出来的拒绝而不是猜测：

- 在没有六面体的实体上设 `elemShape=HEX`，Abaqus **接受**：什么都不划、什么都不报、
  作业照常完成。
- 孔位移出实体的切除操作，什么都不切、返回 0、体积与未切之前逐字节相同。
- 装配布尔造出没人划网的零件：`.inp` 里是空的 `*Part` 配活的 `*Instance`，
  全文件零个 `*Element`。

**完整清单在 [docs/SILENT_FAILURES.md](docs/SILENT_FAILURES.md)** —— 七条实测出来的
「Abaqus 把作业跑完了，还给你一个错答案」，全部带数字。包括那条最贵的：绑定约束
留了 85 个节点没绑上，作业照常收敛，三个平衡恒等式照常通过。这份文档是写给
**不用我们工具的人**看的，每一条你在自己的模型上都能直接用。

这套方言下有五个跑通的算例——`bearing_block`、`two_plate_tie`、`two_plate_contact`、
`block_friction_slide`、`plate_hole_v2`；证明这一层的门禁脚本在
`scripts/run_generic_*_check.py`，其摘要输出提交在
[`evidence/gates/`](evidence/gates/)。方言本身就是
[`schema/spec_schema.json`](schema/spec_schema.json)（每条规则的描述里带着它背后的
实测），最短的完整例子是
[`cases/two_plate_tie/spec.yaml`](cases/two_plate_tie/spec.yaml)。

## 安装

从源码安装：

```bash
git clone https://github.com/Tomsabay/abaqus_agent.git
cd abaqus_agent
pip install -e ".[dev,mcp]"
```

可选 extras：

```bash
pip install -e ".[llm]"  # Anthropic / OpenAI planners
pip install -e ".[all]"  # dev + mcp + llm
```

## 快速上手

### 求解一个算例

```bash
pip install -e ".[dev]"

python agent/orchestrator.py cases/cantilever/spec.yaml \
  cases/cantilever/expected.json \
  cases/cantilever/runner.json
```

版本号是从装好的求解器现场探测出来的，绝不从 spec 里取。Abaqus 不在 `PATH` 上就指给它：

```bash
# Windows
set ABAQUS_AGENT_ABAQUS_CMD=C:\SIMULIA\Commands\abaqus.bat
# Linux
export ABAQUS_AGENT_ABAQUS_CMD=/opt/simulia/Commands/abaqus
```

### 这个工具需要 Abaqus

它驱动的就是 Abaqus。没有 Abaqus 就没有可求解的对象，这时候程序拿这一句话拒绝你，
而不是拿别的东西凑一个近似答案。

2026 年 8 月上过一个 CalculiX 降级后端，两周后删掉了。它是能用的——在冻结的悬臂梁基线上
七位有效数字都对得上——但要让它保持诚实，就得维护一张能力矩阵：逐个功能写清楚第二个
求解器哪些能信、哪些不能，然后把矩阵之外的一切在求解开始之前拒掉。这笔维护费要一直付，
换来的是我们并不想要的覆盖面：手上没有 Abaqus 的人，本来就不是一个 Abaqus 工作台的用户。
演示模式（demo）也一并删了，理由是一样的：一段照着念完七个阶段、最后还亮绿灯的演示，
比直接说"不行"更糟。

活下来的部分本来就跟 CalculiX 无关：没有求解器就绝不产出任何数值；口径与 Abaqus 不同的
KPI 带着出处标签输出、且不参与达标判定，而不是偷偷拿去比对；拒绝的时候一定点名拒的是
spec 里哪个字段。

### 跑测试套件

```bash
pytest -q
```

这套测试是封闭的：Abaqus 会被屏蔽，任何测试都碰不到真求解器。

检查当前机器有没有做真实 Abaqus 验证的条件：

```bash
abaqus-agent validate env --json
abaqus-agent validate env --expected-release 2026 --strict --out validation-preflight.md
abaqus-agent validate env --workdir runs --runner-json '{"cpus":4,"mp_mode":"threads","timeout_seconds":900}' --json
abaqus-agent validate record --environment "Windows 11" --abaqus "Abaqus 2021" --workflow "cantilever" --result PASS --evidence "status=COMPLETED"
```

从一个 run 目录、`capsule.json` 或 `result.json` 导出离线报告：

```bash
abaqus-agent report export runs/my_run --template client_summary --out report.html
abaqus-agent report export runs/my_run --template client_summary --out report.pdf
abaqus-agent report export runs/my_run --template engineering_delivery --out delivery.html
abaqus-agent report export runs/my_run --out report.zip
```

PDF 导出是可选的，走 Playwright 渲染那份独立 HTML 报告：

```bash
pip install "abaqus-agent[pdf]"
playwright install chromium
```

网页界面的 Report 面板也能加载同一个离线来源路径，不用重新起一次分析就能出报告。

不用 Abaqus 校验公开基准 spec：

```bash
python run_benchmark.py --dry-run
```

在装了 Abaqus 的机器上跑完整的一个算例：

```bash
python agent/orchestrator.py cases/cantilever/spec.yaml \
  cases/cantilever/expected.json \
  cases/cantilever/runner.json
```

把现成的 `.inp` 当一等输入用。deck 自带零件、分析步、边界条件和载荷，所以 spec
一样都不描述——`parts`/`assembly`/`steps`/`conditions` 在这里是**拒绝**而不是忽略：
spec 里写了一条 deck 里没有的载荷，等于给读的人一个从没跑过的模型。

```yaml
meta:
  abaqus_release: "2021"
  model_name: "CustomerModel"
deck:
  file: model.inp        # 相对这份 spec 文件
material:
  name: Placeholder
  E: 210000
  nu: 0.3
outputs:
  kpis:
    - name: U_tip
      type: field_min
      component: U2
      location: whole_model
```

从 `.inp` 建一个实验胶囊：

```bash
abaqus-agent capsule init --from-inp model.inp --out runs/model_capsule
```

```python
from capsule.store import init_from_inp

capsule = init_from_inp("model.inp", "runs/model_capsule")
print(capsule["run_id"])
```

评估物理契约：

```python
from contracts import evaluate_contracts

result = evaluate_contracts(
    [
        {"name": "deflects_down", "type": "direction", "kpi": "U_tip", "direction": "negative"},
        {"name": "stress_margin", "type": "range", "kpi": "MISES_MAX", "max": 250.0},
    ],
    {"U_tip": -0.002, "MISES_MAX": 210.0},
)
```

诊断求解器日志：

```bash
abaqus-agent doctor Job-1.msg Job-1.sta
```

```python
from doctor import diagnose_logs

diagnosis = diagnose_logs(paths=["Job-1.msg", "Job-1.sta"])
```

对比 KPI 结果：

```bash
abaqus-agent diff runs/baseline runs/candidate --out diff.md
abaqus-agent diff runs/baseline runs/candidate --tolerances-json '{"MISES": 0.20}' --out diff.md
```

检索本地算例记忆：

```bash
abaqus-agent memory search runs/ --query too_many_attempts --json
abaqus-agent memory search runs/ --similar-to runs/candidate --kpi U_tip --out memory.md
```

```python
from simdiff import diff_runs

diff = diff_runs("runs/baseline", "runs/candidate")
```

归一化一份 ODB Lens 的 KPI 配方，并渲染 KPI 报告：

```yaml
kpis:
  - name: max_mises
    source: odb
    field: S
    invariant: MISES
    region: set:CRITICAL_ZONE
    reducer: max
```

```bash
abaqus-agent lens normalize kpis.yaml --out _kpi_spec.json
abaqus-agent lens report result.json --recipe kpis.yaml --out kpi_report.md
```

## 架构

```text
Codex / Claude Code / ChatGPT / 网页界面 / CLI
        |
        v
意图层（可选 LLM）
        |
        v
Simulation DevOps 内核
  - Experiment Capsule 实验胶囊
  - Physics Contracts 物理契约
  - ODB Lens
  - Solver Doctor
  - Simulation Diff
        |
        v
Abaqus 适配层 / 本地 BYOL runner
  - noGUI
  - syntaxcheck
  - submit
  - monitor
  - ODB 提取
        |
        v
产物：.inp、.cae、.odb、.sta、.msg、.log、报告
```

早期那套自然语言转 spec 的规划器仍然可用，但已经不是产品重心。

## 目录结构

```text
agent/              端到端编排，以及可选的 LLM 规划器
capsule/            实验胶囊清单、哈希与存储辅助
contracts/          物理契约评估
doctor/             求解器日志诊断与模式库
odb_lens/           声明式 KPI 配方与 Markdown KPI 报告
simdiff/            KPI 差异比对与 Markdown 渲染
runner/             Abaqus 建模、syntaxcheck、提交、监控
post/               ODB KPI 提取
tools/              错误定义、schema 校验、静态守卫、Abaqus 命令解析
mcp_server.py       用于 agent 集成的 MCP 服务端
mcp_bridge.py       面向浏览器客户端的 HTTP/SSE 桥
server.py           FastAPI 服务端
cases/              公开基准 spec
features/           可选分析模块：耦合、自适应、参数化、
                    扩展几何、自动修复
```

## 基准状态

目前公开的 spec 覆盖：

| 算例 | 类型 | 求解器 | 关键 KPI |
|---|---|---|---|
| `cantilever` | 三维静力梁 | Standard | `U_tip`、`MISES_MAX` |
| `plate_hole` | 二维平面应力板 | Standard | `MISES_HOLE_EDGE`、`U_X_MAX`、`SCF` |
| `modal` | 固支梁模态 | Standard / Lanczos | `freq_1`、`freq_2`、`freq_3` |
| `explicit_impact` | 动态压缩 | Explicit | `RF_Z_MAX`、`U_Z_MIN` |
| `blast_plate` | 防护爆炸板 demo | Explicit | `U_MAX_DEFLECTION`、`PEEQ_MAX`、`ALLPD_MAX` |

以及 v2 方言下的算例——模型不是从 geometry 类型挑出来的，是一句句派发出来的：

| 算例 | 是什么 | 相互作用 | 关键 KPI |
|---|---|---|---|
| `two_plate_tie` | 一个零件、两个实例，绑在一起 | tie | `U_TIP`、`MISES_MAX` |
| `two_plate_contact` | 同一对，改成接触 | contact | `U_TIP`、`MISES_MAX` |
| `block_friction_slide` | 两个零件、两个静力步：先压后推 | contact + 摩擦 | `FRICTION_FORCE`、`NORMAL_FORCE` |
| `plate_hole_v2` | 带孔板，由 sketch entities 建出来 | — | `HOOP_MAX`、`HOOP_S22`、`FAR_FIELD` |
| `bearing_block` | 三个零件、三个分析步，螺栓预紧，tie 与接触同时在场 | tie + contact | `WEIGHT_TOTAL`、`CLAMP_REACTION`、`FRICTION_FORCE`、`BUSHING_DROP`、`CAP_MISES_MAX` |

说明：

- `python run_benchmark.py --dry-run` 不用 Abaqus 就能校验 spec。
- `abaqus-agent validate env` 和 Environment 面板会在真实验证之前，记录操作系统、Python、Abaqus 命令解析、`abaqus information=release`、期望版本是否匹配、工作目录可写性、license 标记和 runner 配置证据。
- `abaqus-agent validate record` 会在真实的 Windows/Linux/Abaqus 运行之后，往 `docs/VALIDATION_MATRIX.md` 追加一行归一化的证据记录，文件不存在时首次调用会创建它 —— 这个矩阵记的是你自己的环境，不是我们的。
- `abaqus-agent report export`、`/api/report/export`、MCP 桥和 Report 面板，能从离线的运行证据产出 Markdown、独立 HTML、可选 PDF 或打包 zip 的报告。
- 完整回归需要本地装好 Abaqus 并持有 license。
- 每一句"支持"背后的证据，都是你自己能跑的校核脚本：`scripts/run_*_check.py`。
- 目前的本地验证是在 Abaqus 2021 / Windows 上做的。
- 有外部贡献者报告过 Abaqus 2026 的兼容性；原始报告已不随本仓库分发，因此不计入当前的门禁证据。

## 安全与部署

所有生成或处理的工作流，都是按"在用户自己的 Abaqus 授权环境里本地运行"设计的。

推荐的商业部署模式是 BYOL（自带授权）：

- 客户本地 runner
- 客户自有的 Abaqus license
- 产物和 ODB 都留在本地
- 可选的咨询、报告模板、私有配方和团队 runner

不要在没有对 Dassault Systemes 相关授权条款做过明确法务审查的情况下，把第三方的 Abaqus 任务当托管 SaaS 来跑。

## 路线图

- [x] 7 阶段 Abaqus 流水线：validate、build、syntaxcheck、submit、monitor、extract、compare
- [x] Abaqus 子进程调用的 Windows `.bat` 命令解析器
- [x] MCP 服务端与 HTTP 桥
- [x] FastAPI/SSE 网页 API
- [x] `custom_inp` 免 CAE 建模路径
- [x] v0.2 capsule / contract / diff / doctor 内核 MVP
- [x] orchestrator 输出以 capsule 为载体
- [x] Solver Doctor / 契约校核 / KPI diff 的 CLI
- [x] ODB Lens 的 YAML KPI 配方归一化与 KPI Markdown 报告
- [x] Simulation Diff 的 CLI/API/UI，并在真实 Windows Abaqus 上验证过
- [x] Simulation Diff 的结构化变更摘要，覆盖 Markdown/API/UI
- [x] Simulation Diff 逐 KPI 的容差覆盖，覆盖 CLI/API/MCP/UI
- [x] Simulation Diff 的 Markdown 下载接口与界面动作
- [x] Simulation Diff 的结构化产物证据行（哈希/大小/原因），覆盖 Markdown/API/UI
- [x] 面向 capsule 初始化、契约校核、Solver Doctor 和 Simulation Diff 的 MCP 工具
- [x] ODB Lens 直连 Abaqus 提取器，覆盖 frame、region、component、invariant 和 reducer 字段
- [x] Markdown 报告模板
- [x] 面向下游 HTML/PDF 交接的工程交付报告模板
- [x] 交付报告里的证据清单，覆盖 capsule/结果/KPI/回归/契约/产物/doctor 的交接
- [x] Delivery Manifest 章节：工程交接的包体/就绪度/产物内容摘要
- [x] 覆盖 Abaqus 版本与操作系统的验证矩阵
- [x] Case Memory 的确定性本地 capsule 检索
- [x] Case Memory 的 CLI/API/MCP/UI 流程，并用真实 capsule 历史验证过
- [x] Case Memory 的产物、排序方式和最低分控制，覆盖 CLI/API/MCP/UI
- [x] Case Memory 的契约筛选与 KPI/产物计数排序控制，覆盖 CLI/API/MCP/UI
- [x] Case Memory 的自由文本匹配模式控制（`any` / `all`），覆盖 CLI/API/MCP/UI
- [x] Case Memory 的结果分面：状态/几何/求解器/材料/契约结果摘要
- [x] Case Memory 按几何、求解器、材料的分面筛选，覆盖 CLI/API/MCP/UI
- [x] 网页界面里的 Markdown 报告复制/下载动作
- [x] 独立 HTML 报告导出接口与网页界面下载动作
- [x] 面向下游 PDF 交接的浏览器预览/打印模式
- [x] 通过 Playwright 提供的可选 PDF 报告导出，覆盖 CLI/API/MCP 桥/UI
- [x] 报告打包 zip 接口与网页界面下载动作
- [x] Environment Preflight 的 CLI/API/MCP/UI 流程，用于 Linux/Windows/Abaqus 版本验证就绪度
- [x] Environment Preflight 里的期望 Abaqus 版本匹配，覆盖 CLI/API/MCP/UI
- [x] Environment Preflight 里的工作目录、license 标记和 runner 配置就绪检查
- [x] 记录真实运行证据行的验证矩阵证据记录 CLI
- [x] 离线报告导出的 CLI/API/MCP/UI 流程，支持 run 目录、capsule 和 result JSON 文件

## 致谢

- **[@ganansuan647](https://github.com/ganansuan647)（GLY2024）** —— 第一位外部贡献者。在本项目并不持有的一份授权上报告了 Abaqus 2026 兼容性，并贡献了 Windows 命令路径的修复。

## 许可证

**AGPL-3.0-or-later** —— 见 [LICENSE](LICENSE)。

大多数人不需要别的：运行它、修改它、在你自己组织内部商用，在 AGPL 下都是免费的。它多出来的义务很窄 —— 如果你把改过的版本通过网络提供给别人，那些用户必须能拿到你改过的源码。

如果这条不合适（闭源嵌入、专有再分发，或者一个你没法开源的托管服务），可以走**商业授权**，价格公开写在 [LICENSING.md](LICENSING.md) —— 没有"联系我们获取报价"这一套。

有两处刻意留的例外，好让集成这个工具时不会把 AGPL 带进来：

- `schema/`、`cases/` 和 `examples/` 仍然是 **Apache-2.0**
  （[LICENSES/Apache-2.0.txt](LICENSES/Apache-2.0.txt)）—— 它们是集成面，
  任何人都应该能照着实现。
- 2026-03-06 到 2026-06-16 之间发布的版本是 Apache-2.0。那份授权不可撤销，
  这段时间的 fork 可以继续按它使用。

完整细节见 [NOTICE](NOTICE)。贡献仍然是 inbound-Apache-2.0 —— 不签 CLA，
不做版权转让（见 [CONTRIBUTING.md](CONTRIBUTING.md)）。
