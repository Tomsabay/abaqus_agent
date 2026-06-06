# NEXT_TICKETS

## Ready Local
- 当前显式 Ready Local 队列已清空。若继续 Goal Chain，应先从 `CURRENT_STATE.md` / `CAPABILITY_AUDIT.md` / 用户战略中创建新的产品可见本地票。
- 新票优先加强主功能链路：`existing .inp/spec -> real Abaqus run -> ODB KPI -> Physics Contract -> Simulation Diff -> deliverable report`。
- 不要用状态检查、ledger 记录、重复 diff/status snapshot、低价值 boundary wording、MCP/API/UI parity、更多 gallery/demo-pack 包装或泛前端 polish 填时间，除非它们直接强化上面的主链路。
- 下一批高价值票应优先考虑：真实 Abaqus 多 case / custom_inp 验证、把 compare_expected/Physics Contract 纳入真实 smoke、真实 run capsule 到 diff/report 的闭环、客户可读报告模板。

## Blocked Branches
These are blocked branches, not whole Goal Chain stop conditions. If elapsed
time remains and useful local work exists, record the blocked branch and keep
executing the next local ticket.

- `ABAQUS-ENV-VALIDATION-001`：真实 Abaqus environment validation。需要可见 Abaqus executable/license/version；普通 Mac shell 当前无法完成。目标是在 Abaqus 机器上用 license-aware 最小 case 验证 `build_model`/`syntaxcheck`/`submit_job`/`monitor_job`/`extract_kpis`/`compare_expected` 链路，并记录实际 license 行为和最小 scope evidence。
- Docker compose runtime smoke：当前 shell 没有 `docker` 命令，无法在本机完成 Docker build/compose/API probe。
- GitHub Release creation decision：remote tag `v0.1.0` exists but GitHub Releases list is empty；`RELEASE_INSTRUCTIONS.md` 已按新 Simulation QA 定位和当前证据重写。需要用户确认是否按该清单创建 release。
- PyPI distribution decision：public PyPI API for `abaqus-agent` returns 404；README 已改为 source install。需要决定继续 source-only、发布到 PyPI，或延后到 v0.2.0-dev。
- 本地 checkout 落后于远端 `main`：local HEAD `553de3fc41336f19e601a042a0adce5b9a88f212`，remote `main` `62c3eb541bddc583c01a1e9d86e4409f07260ce2`；且本地有未提交 Goal Chain 改动，因此未 pull/merge。
- `AGENTS.md` 与 `docs/goal_driver/` 是否纳入版本控制需要用户最终确认。
- Default `python` command is absent and default `python3` is below the project requirement; future verification should explicitly use Python 3.11.
- Warning-free TestClient output：`TESTCLIENT-HTTPX-WARNING-AUDIT-001` 已确认剩余 warning 来自 installed Starlette TestClient fallback because `httpx2` is not installed. 后续需要单独决定是评估添加 `httpx2` test dependency，还是显式过滤该外部 warning；本次审计未改依赖。
