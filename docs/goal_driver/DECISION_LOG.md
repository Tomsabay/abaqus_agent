# DECISION_LOG

## 2026-06-03

### Decision
README 声称能力必须按 `Verified by command`、`Covered by tests`、`Supported by source`、`Dry-run only`、`Environment-limited`、`Documentation-only / Unverified`、`Mismatch / Risk` 分级，不直接当作已完成事实。

### Reason
`README-CAPABILITY-AUDIT-001` 确认 install/default pytest/benchmark dry-run 为 Healthy，但真实 Abaqus executable/license/syntaxcheck/solver/ODB KPI 和真实 MCP stdio client 仍未验证。README roadmap `[x]` 同时包含源码支持、测试覆盖、dry-run 和未验证集成能力。

### Alternatives Rejected
- 不把 README roadmap 勾选项直接写入“已验证通过”。
- 不因为 API/UI simulated pipeline 可以完成就宣称真实 Abaqus solver e2e 已验证。
- 不把 mock MCP bridge 或 direct MCP function tests 等同于真实 MCP client 集成。

### Impact
后续规划优先补真实 Abaqus environment validation；README 更新或发布前必须区分源码支持、测试覆盖和真实执行证据。

## 2026-06-03

### Decision
README 中的完成度声明暂时只作为文档声明，不作为已验证项目事实。

### Reason
`INIT-PROGRESS-001` 未读取源码、未运行测试、未验证 benchmark、未验证 Abaqus 环境。

### Alternatives Rejected
- 不直接进入新功能开发。
- 不根据 README 声明直接规划高级功能扩展。

### Impact
下一张 ticket 必须优先验证真实工程 baseline，并将验证结果写入 `CURRENT_STATE.md`。

## 2026-06-03

### Decision
Goal Driver 状态文件应作为 abaqus-agent 项目本地状态来源维护。

### Reason
本 Project 要求项目状态、handoff、ticket、decision log 与其他项目隔离。

### Alternatives Rejected
不使用其他项目经验或外部状态推断 abaqus-agent 当前实现。

### Impact
后续 review 和规划只基于 abaqus-agent repo 内 handoff、状态文件、测试结果和用户提供的信息。

## 2026-06-03

### Decision
README 声称能力必须经过安装、测试、benchmark 或源码级验证后，才能进入 `CURRENT_STATE.md` 的“已验证通过”。

### Reason
`BASELINE-VERIFY-001` 证明 README 中“197 tests”等部分声明可以被收集验证，但 pytest 实际结果为 176 passed / 21 failed，MCP server 能力因缺少 `mcp` dependency 未通过。

### Alternatives Rejected
- 不把 README roadmap 勾选项直接升级为项目事实。
- 不在 baseline 失败时进入新功能开发。

### Impact
下一轮应先修复/确认 test dependency 与 MCP optional extra 的关系，再决定是否进入功能或架构 hardening。

## 2026-06-03

### Decision
默认开发安装 `.[dev]` 必须包含 MCP server 默认测试所需依赖，因此 `dev` extra 包含 `mcp>=1.0`。

### Reason
默认 pytest 套件包含 `tests/test_mcp_server.py`，这些测试直接导入 `mcp_server.py` 并验证 MCP server 工具/资源函数；缺少 `mcp` 会使默认测试以 import error 失败。

### Alternatives Rejected
- 不在默认测试中 skip MCP server 测试，因为项目当前测试合同表明 MCP 测试属于默认 pytest baseline。
- 不修改 `mcp_server.py`，因为安装 `mcp` 后 `mcp.server.fastmcp` 与现有代码兼容，MCP 专项测试通过。

### Impact
后续执行 `pip install -e ".[dev]"` 应能支撑默认 pytest；MCP 仍可作为 runtime optional extra 对用户暴露，但 dev/test 环境默认包含它。
