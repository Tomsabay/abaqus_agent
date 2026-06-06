# CODEX_RUN_LEDGER

## Ticket ID
V0.2-FRONTEND-LOCAL-SMOKE-NESTED-VERIFY-STATIC-TEST-001

### Date
2026-06-05

### Status
Done

### Summary
Extended the frontend static contract tests to cover the immediate `运行 CLI Smoke` result panel, ensuring `renderLocalCliSmokeResult()` continues to read `bundle_verification.copied_demo_pack_verification` and render the nested copied demo pack verification line.

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check tests/test_frontend_static_contracts.py`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_frontend_static_contracts.py -q`: first run failed because one marker did not match the actual source string; rerun after correcting the marker passed, 2 passed.
- `git diff --check`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed; 355 passed, 1 warning.

### Files Changed
- `tests/test_frontend_static_contracts.py`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Focused frontend static contract tests and full local regression passed. The remaining pytest warning is the known external Starlette TestClient/httpx fallback warning.

### Scope Check
Only the frontend static contract test and Goal Driver records were modified. No runtime frontend behavior, server/API/MCP/bridge behavior, verifier schema, smoke generation semantics, package publish, real Abaqus executable/license, ODB extraction, Docker, GitHub/PyPI work, commit/push, or real Abaqus validation was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
V0.2-FRONTEND-VAULT-SMOKE-NESTED-VERIFY-STATIC-TEST-001

### Date
2026-06-05

### Status
Done

### Summary
Added a pytest static frontend contract for the Evidence Vault stored `local-cli-smoke` verify detail, ensuring `renderEvidenceVaultBundleVerification()` keeps the nested `copied_demo_pack_verification` summary markers and the smoke vault-row verify trigger.

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_frontend_static_contracts.py -q`: passed, 1 passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check tests/test_frontend_static_contracts.py`: first run failed on import block formatting; rerun after `ruff --fix` passed.
- `git diff --check`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed; 354 passed, 1 warning.

### Files Changed
- `tests/test_frontend_static_contracts.py`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Focused static frontend contract pytest and focused ruff now pass. Full local regression passed. The remaining pytest warning is the known external Starlette TestClient/httpx fallback warning.

### Scope Check
Only a frontend static contract test and Goal Driver records were modified. No runtime frontend behavior, server/API/MCP/bridge behavior, verifier schema, smoke generation semantics, package publish, real Abaqus executable/license, ODB extraction, Docker, GitHub/PyPI work, commit/push, or real Abaqus validation was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
V0.2-FRONTEND-VAULT-SMOKE-NESTED-VERIFY-DETAIL-001

### Date
2026-06-05

### Status
Done

### Summary
Frontend Evidence Vault verification detail now includes a compact nested `copied_demo_pack_verification` summary when a stored `local-cli-smoke` vault row `VERIFY` response returns one. This lets the same vault detail panel show both the outer smoke ZIP verification and the inner copied demo pack verification status/count.

### Commands
- Static frontend marker probe for `renderEvidenceVaultBundleVerification`, `copied_demo_pack_verification`, `nestedDemoPack.checked_file_count`, `nestedDemoPack.zip_path`, and `data-vault-verify-smoke-id`: passed.
- Extracted JS syntax probe with `node --check /tmp/abaqus-agent-frontend-check.js`: passed.
- `git diff --check`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed; 353 passed, 1 warning.

### Files Changed
- `frontend/index.html`
- `README.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Static source and extracted JS syntax probes passed. Full local regression passed. Browser automation remained unavailable in the current tool environment, so no browser screenshot smoke was run. The remaining pytest warning is the known external Starlette TestClient/httpx fallback warning.

### Scope Check
Only frontend bundle verification detail rendering and documentation were modified. No server/API/MCP/bridge behavior, verifier schema, smoke generation semantics, package publish, real Abaqus executable/license, ODB extraction, Docker, GitHub/PyPI work, commit/push, or real Abaqus validation was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
V0.2-FRONTEND-VAULT-SMOKE-VERIFY-ACTION-001

### Date
2026-06-05

### Status
Done

### Summary
Frontend Evidence Vault rows for `local-cli-smoke` entries now show a `VERIFY` action. The action calls Direct API `POST /api/evidence/vault/{vault_id}/verify-smoke` and renders PASS/FAIL plus checked manifest file data in the existing vault detail panel.

### Commands
- Static frontend source marker probe for `data-vault-verify-smoke-id`, `verifyEvidenceVaultSmoke`, verify-smoke route, `renderEvidenceVaultSmokeVerification`, and `Smoke ZIP verify`: passed.
- Extracted JS syntax probe with `node --check /tmp/abaqus-agent-frontend-check.js`: passed.
- `git diff --check`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed; 341 passed, 1 warning.

### Files Changed
- `frontend/index.html`
- `README.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Static source and extracted JS syntax probes passed. Full local regression passed. Browser automation remained unavailable through current tools, so no browser screenshot smoke was run. The remaining pytest warning is the known external Starlette TestClient/httpx fallback warning.

### Scope Check
No server/MCP/bridge behavior change, smoke generation semantics change, broad frontend redesign, package publish, real Abaqus executable/license, ODB extraction, Docker, GitHub/PyPI work, commit/push, or real Abaqus validation was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
V0.2-LOCAL-CLI-SMOKE-DEEP-VERIFY-SURFACES-001

### Date
2026-06-05

### Status
Done

### Summary
把 nested `copied_demo_pack_verification` 合同锁到 Direct API、MCP stdio、vault MCP stdio、HTTP-to-MCP bridge 的 smoke ZIP verification 测试中，确保 surface 返回外层 smoke ZIP PASS 的同时也返回 copied demo pack PASS / 31 checked files。

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check tests/test_server_api_smoke.py tests/test_mcp_server.py tests/test_mcp_stdio_client.py tests/test_mcp_bridge_real_subprocess.py`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_server_api_smoke.py tests/test_mcp_server.py tests/test_mcp_stdio_client.py tests/test_mcp_bridge_real_subprocess.py -q`: passed, `45 passed, 1 warning`.

### Files Changed
- `tests/test_server_api_smoke.py`
- `tests/test_mcp_server.py`
- `tests/test_mcp_stdio_client.py`
- `tests/test_mcp_bridge_real_subprocess.py`
- `README.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
- Focused ruff passed.
- Focused API/MCP/bridge tests passed with `45 passed, 1 warning`.
- Full verification passed: `git diff --check`, full `ruff check .`, and full pytest `353 passed, 1 warning`.

### Scope Check
Only tests and documentation were modified. No runtime behavior, API/schema, frontend, smoke generation/verifier semantics, real Abaqus/ODB execution, Docker, package publish, GitHub push/merge, or external service work were performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
V0.2-FRONTEND-LOCAL-CLI-SMOKE-NESTED-VERIFY-001

### Date
2026-06-05

### Status
Done

### Summary
Frontend `renderLocalCliSmokeResult()` now displays nested `copied_demo_pack_verification` returned by Direct API smoke ZIP verification, showing copied demo pack status and checked file count alongside the outer smoke ZIP verification.

### Commands
- Static frontend marker probe for `copied_demo_pack_verification`, `copied demo pack verify`, `nestedVerify.checked_file_count`, `zip verify:`, and `renderLocalCliSmokeResult`: passed.
- Extracted JS syntax probe with `node --check /tmp/abaqus-agent-frontend-check.js`: passed.

### Files Changed
- `frontend/index.html`
- `README.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
- Static source marker probe passed.
- Extracted frontend JavaScript syntax check passed.
- Browser automation remained unavailable through current tools, so no browser screenshot smoke was run.
- Full verification passed: `git diff --check`, full `ruff check .`, and full pytest `353 passed, 1 warning`.

### Scope Check
Only frontend local CLI smoke rendering and documentation were modified. No API/server/MCP/bridge behavior, smoke generation/verifier schema, real Abaqus/ODB execution, Docker, package publish, GitHub push/merge, or external service work were performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
V0.2-LOCAL-CLI-SMOKE-DEEP-DEMO-PACK-VERIFY-001

### Date
2026-06-05

### Status
Done

### Summary
Local CLI smoke ZIP verifier 现在会深度校验嵌套的 `copied-local-demo-pack.zip`：先验证外层 `local_cli_smoke_manifest.json`，再验证 copied demo pack 内部 `local-demo-pack-manifest.json`，并返回 `copied_demo_pack_verification`。

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check scripts/verify_local_demo_pack_bundle.py scripts/verify_local_cli_smoke_bundle.py tests/test_local_cli_smoke.py tests/test_local_demo_pack_verify.py`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_local_cli_smoke.py tests/test_local_demo_pack_verify.py -q`: passed, `12 passed`.
- Installed verifier probe after `abaqus-agent-local-cli-smoke`: first shell pipeline form failed because JSON was sent to `python -`; rerun with `python -c` passed, outer `checked_file_count=4`, nested demo pack `checked_file_count=31`.

### Files Changed
- `scripts/verify_local_demo_pack_bundle.py`
- `scripts/verify_local_cli_smoke_bundle.py`
- `tests/test_local_cli_smoke.py`
- `tests/test_local_demo_pack_verify.py`
- `README.md`
- `RELEASE_INSTRUCTIONS.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
- Focused ruff passed.
- Focused verifier tests passed with `12 passed`.
- Installed smoke verifier probe passed after correcting shell pipeline usage.
- Full verification passed: `git diff --check`, full `ruff check .`, and full pytest `353 passed, 1 warning`.

### Scope Check
Only verifier logic, focused verifier tests, and documentation were modified. No smoke generation semantics, server/MCP/bridge/frontend endpoint behavior, real Abaqus/ODB execution, Docker, package publish, GitHub push/merge, or external service work were performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
V0.2-FRONTEND-VAULT-DEMO-PACK-VERIFY-ACTION-001

### Date
2026-06-05

### Status
Done

### Summary
Frontend Evidence Vault 为 `local-demo-pack` rows 新增 `VERIFY` action，调用 Direct API `POST /api/evidence/vault/{vault_id}/verify-demo-pack`，并通过共享 bundle verification renderer 在 vault detail panel 中显示 workflow/status/checked files。

### Commands
- Static frontend marker probe for `data-vault-verify-demo-pack-id`, `verifyEvidenceVaultDemoPack`, `/verify-demo-pack`, `renderEvidenceVaultBundleVerification`, `Demo Pack ZIP verify`, and existing smoke verify markers: passed.
- Extracted JS syntax probe with `node --check /tmp/abaqus-agent-frontend-check.js`: passed.

### Files Changed
- `frontend/index.html`
- `README.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
- Static source marker probe passed.
- Extracted frontend JavaScript syntax check passed.
- Browser automation remained unavailable through current tools, so no browser screenshot smoke was run.
- Full verification passed: `git diff --check`, full `ruff check .`, and full pytest `352 passed, 1 warning`.

### Scope Check
Only frontend Vault-row action/rendering and documentation were modified. No server/MCP/bridge behavior change, demo pack artifact semantics, real Abaqus/ODB execution, Docker, package publish, GitHub push/merge, or external service work were performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
V0.2-EVIDENCE-VAULT-DIRECT-API-DEMO-PACK-VERIFY-001

### Date
2026-06-05

### Status
Done

### Summary
Direct API 新增 `POST /api/evidence/vault/{vault_id}/verify-demo-pack`，按 vault id 校验 server Evidence Vault 内的 `local-demo-pack.zip` embedded manifest，并返回 verifier JSON 加 `vault_id`、`filename`、`source_path`。

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_server_api_smoke.py -q`: passed, `6 passed, 1 warning`.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check server.py tests/test_server_api_smoke.py`: first run failed on import order, rerun passed.

### Files Changed
- `server.py`
- `tests/test_server_api_smoke.py`
- `README.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
- Focused TestClient smoke passed with `6 passed, 1 warning`.
- Focused ruff passed after an import-order fix.
- Full verification passed: `git diff --check`, full `ruff check .`, and full pytest `352 passed, 1 warning`.

### Scope Check
Only Direct API endpoint, API smoke test, and documentation were modified. No MCP/bridge/frontend changes, vault schema changes, demo pack artifact semantics, real Abaqus/ODB execution, Docker, package publish, GitHub push/merge, or external service work were performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
V0.2-EVIDENCE-VAULT-BRIDGE-DEMO-PACK-VERIFY-001

### Date
2026-06-05

### Status
Done

### Summary
HTTP-to-MCP bridge 新增 `POST /mcp/api/evidence/vault/{vault_id}/verify-demo-pack`，通过 MCP stdio `verify_evidence_vault_demo_pack_bundle_tool` 校验 vault-stored `local-demo-pack.zip` 的 embedded manifest。

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check mcp_bridge.py tests/test_mcp_bridge_real_subprocess.py`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_mcp_bridge_real_subprocess.py -q`: passed, `1 passed, 1 warning`.

### Files Changed
- `mcp_bridge.py`
- `tests/test_mcp_bridge_real_subprocess.py`
- `README.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
- Focused ruff passed.
- Focused real bridge subprocess smoke passed with `1 passed, 1 warning`.
- Full verification passed: `git diff --check`, full `ruff check .`, and full pytest `352 passed, 1 warning`.

### Scope Check
Only HTTP-to-MCP bridge endpoint, bridge subprocess test, and documentation were modified. No Direct API/frontend changes, vault schema changes, demo pack artifact semantics, real Abaqus/ODB execution, Docker, package publish, GitHub push/merge, or external service work were performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
V0.2-EVIDENCE-VAULT-MCP-DEMO-PACK-VERIFY-001

### Date
2026-06-05

### Status
Done

### Summary
MCP stdio 新增 `verify_evidence_vault_demo_pack_bundle_tool`，可通过 vault id/root 解析并校验 vault-stored `local-demo-pack.zip`，返回 demo pack verifier JSON 加 `vault_id`、`filename`、`vault_root`、`source_path`。

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check mcp_server.py tests/test_mcp_server.py tests/test_mcp_stdio_client.py`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_mcp_server.py tests/test_mcp_stdio_client.py -q`: passed, `38 passed`.

### Files Changed
- `mcp_server.py`
- `tests/test_mcp_server.py`
- `tests/test_mcp_stdio_client.py`
- `README.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
- Focused ruff passed.
- Focused MCP direct/stdio pytest passed with `38 passed`.
- Full verification passed: `git diff --check`, full `ruff check .`, and full pytest `352 passed, 1 warning`.

### Scope Check
Only MCP stdio wrapper, MCP tests, and documentation were modified. No Direct API/bridge/frontend endpoint changes, vault schema changes, demo pack artifact semantics, real Abaqus/ODB execution, Docker, package publish, GitHub push/merge, or external service work were performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
V0.2-EVIDENCE-VAULT-CLI-DEMO-PACK-VERIFY-001

### Date
2026-06-05

### Status
Done

### Summary
Evidence Vault no-server CLI 新增 `verify-demo-pack <vault_id>`，默认校验 vault entry 内的 `local-demo-pack.zip`。命令通过现有 vault path validation 解析文件，然后复用 local demo pack ZIP verifier，返回 `vault_id`、`filename`、`source_path` 和 manifest 校验结果。

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_evidence_vault.py -q`: passed, `11 passed`.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check scripts/inspect_evidence_vault.py tests/test_evidence_vault.py`: first run failed on import order, rerun passed.
- Installed `abaqus-agent-vault --root /tmp/abaqus-agent-vault-demo-pack-verify-cli/vault verify-demo-pack <vault_id>` probe: passed, `overall_status=PASS`, `checked_file_count=31`.

### Files Changed
- `scripts/inspect_evidence_vault.py`
- `tests/test_evidence_vault.py`
- `README.md`
- `RELEASE_INSTRUCTIONS.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
- Focused vault CLI pytest passed with `11 passed`.
- Focused ruff passed after an import-order fix.
- Installed vault verifier probe passed.
- Full verification passed: `git diff --check`, full `ruff check .`, and full pytest `352 passed, 1 warning`.

### Scope Check
Only Evidence Vault CLI verification, focused tests, and documentation were modified. No vault schema changes, server/MCP/bridge/frontend endpoint changes, demo pack artifact semantics, real Abaqus/ODB execution, Docker, package publish, GitHub push/merge, or external service work were performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
V0.2-LOCAL-DEMO-PACK-BUNDLE-VERIFY-MCP-001

### Date
2026-06-05

### Status
Done

### Summary
MCP stdio 新增 `verify_local_demo_pack_bundle_tool`，让 agent 客户端可直接校验本地 `local-demo-pack.zip` 的 embedded manifest，不必 shell out 到 CLI。该工具复用 no-extraction `scripts.verify_local_demo_pack_bundle.verify_demo_pack_bundle`。

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check mcp_server.py tests/test_mcp_server.py tests/test_mcp_stdio_client.py`: first run failed on import order, rerun passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_mcp_server.py tests/test_mcp_stdio_client.py -q`: passed, `38 passed`.

### Files Changed
- `mcp_server.py`
- `tests/test_mcp_server.py`
- `tests/test_mcp_stdio_client.py`
- `README.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
- Focused pytest passed with `38 passed`.
- Focused ruff passed after an import-order fix.
- Full verification passed: `git diff --check`, full `ruff check .`, and full pytest `350 passed, 1 warning`.

### Scope Check
Only MCP stdio wrapper, MCP tests, and documentation were modified. No Direct API/bridge/frontend endpoints, vault-id verifier, demo pack artifact semantics, real Abaqus/ODB execution, Docker, package publish, GitHub push/merge, or external service work were performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
V0.2-LOCAL-DEMO-PACK-BUNDLE-VERIFY-001

### Date
2026-06-05

### Status
Done

### Summary
新增 no-server `local-demo-pack.zip` verifier：`scripts/verify_local_demo_pack_bundle.py` 和 console command `abaqus-agent-verify-local-demo-pack` 可直接读取 ZIP 内 `local-demo-pack-manifest.json`，逐项校验 bundled artifact 的 size/SHA-256，不需要解压、不调用 Abaqus。

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check scripts/verify_local_demo_pack_bundle.py tests/test_local_demo_pack_verify.py tests/test_cli_entrypoints.py`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_local_demo_pack_verify.py tests/test_cli_entrypoints.py -q`: passed, `10 passed`.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pip install -e ".[dev]"`: passed.
- Generated `/tmp/abaqus-agent-demo-pack-verify-cli/local-demo-pack.zip` with `scripts/run_local_demo_pack.py`, then ran `/tmp/abaqus-agent-audit-venv/bin/abaqus-agent-verify-local-demo-pack ... --json`: passed, `overall_status=PASS`, `checked_file_count=31`.

### Files Changed
- `scripts/verify_local_demo_pack_bundle.py`
- `tests/test_local_demo_pack_verify.py`
- `tests/test_cli_entrypoints.py`
- `pyproject.toml`
- `README.md`
- `RELEASE_INSTRUCTIONS.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
- Focused ruff passed.
- Focused verifier/entrypoint pytest passed with `10 passed`.
- Editable install plus installed CLI probe passed.
- Full verification passed: `git diff --check`, full `ruff check .`, and full pytest `350 passed, 1 warning`.

### Scope Check
Only no-server verifier, entry point metadata, tests, and documentation were modified. No server/MCP/frontend endpoint changes, real Abaqus/ODB execution, Docker, package publish, GitHub push/merge, or external service work were performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
V0.2-LOCAL-DEMO-PACK-ZIP-MANIFEST-001

### Date
2026-06-05

### Status
Done

### Summary
为主 `local-demo-pack.zip` 增加 `local-demo-pack-manifest.json`，记录每个打包源文件的 size/SHA-256，提升核心 no-Abaqus 便携 demo artifact 的可校验性。manifest 写入 demo pack 输出目录、ZIP、以及本地 Evidence Vault 文件表，但不把 manifest 自身纳入哈希列表，避免循环校验。

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check scripts/run_local_demo_pack.py tests/test_offline_evidence_slice.py tests/test_server_api_smoke.py tests/test_mcp_server.py tests/test_mcp_stdio_client.py tests/test_mcp_bridge_real_subprocess.py`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_offline_evidence_slice.py tests/test_server_api_smoke.py tests/test_mcp_server.py tests/test_mcp_stdio_client.py tests/test_mcp_bridge_real_subprocess.py -q`: passed, `50 passed, 1 warning`.
- Actual CLI probe generated `/tmp/abaqus-agent-local-demo-pack-manifest`: passed, `overall_status=PASS`, manifest present in ZIP, 31 manifest file entries, sampled hashes matched ZIP payloads.

### Files Changed
- `scripts/run_local_demo_pack.py`
- `tests/test_offline_evidence_slice.py`
- `tests/test_server_api_smoke.py`
- `tests/test_mcp_server.py`
- `tests/test_mcp_stdio_client.py`
- `tests/test_mcp_bridge_real_subprocess.py`
- `README.md`
- `RELEASE_INSTRUCTIONS.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
- Focused ruff passed.
- Focused local/API/MCP direct/MCP stdio/real bridge tests passed with `50 passed, 1 warning`.
- Actual CLI probe verified generated ZIP manifest membership and sample SHA-256 values.
- Full verification passed: `git diff --check`, full `ruff check .`, and full pytest `341 passed, 1 warning`.

### Scope Check
Only local demo pack artifact metadata, tests, and documentation were modified. No real Abaqus/ODB execution, Docker, package publish, GitHub push/merge, or frontend/server/MCP endpoint behavior changes were performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
V0.2-FRONTEND-LOCAL-CLI-SMOKE-VERIFY-001

### Date
2026-06-05

### Status
Done

### Summary
Frontend Evidence workspace now verifies the local CLI smoke ZIP after `运行 CLI Smoke` succeeds. It calls Direct API `POST /api/evidence/vault/{smoke_vault_id}/verify-smoke`, then renders ZIP verification status, checked file count, and per-file manifest status/hash alongside smoke artifact links and step results.

### Commands
- Static frontend source probe: first run failed once because the probe incorrectly required an MCP tool name in frontend source; corrected probe passed.
- Extracted JS syntax probe: first run failed once because `node --check` was pointed at `frontend/index.html`; corrected extraction to `/tmp/abaqus-agent-frontend-check.js` passed.
- `tool_search` for Browser automation exposed no callable Browser tool in this turn; no browser screenshot smoke was run.
- `git diff --check`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed; 341 passed, 1 warning.

### Files Changed
- `frontend/index.html`
- `README.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Static source markers verify the Direct API verify-smoke route, `bundle_verification` assignment, `zip verify` rendering, and `checked_file_count` handling. Extracted frontend JS syntax check passed. Full local regression passed. Browser automation was unavailable; the remaining pytest warning is the known external Starlette TestClient/httpx fallback warning.

### Scope Check
No server/MCP/bridge behavior change, smoke generation semantics change, broad frontend redesign, package publish, real Abaqus executable/license, ODB extraction, Docker, GitHub/PyPI work, commit/push, or real Abaqus validation was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
V0.2-EVIDENCE-VAULT-DIRECT-API-SMOKE-VERIFY-001

### Date
2026-06-05

### Status
Done

### Summary
Direct API now exposes `POST /api/evidence/vault/{vault_id}/verify-smoke`, letting local HTTP clients verify a server-vault `local_cli_smoke.zip` against its embedded manifest after triggering `POST /api/evidence/local-cli-smoke`.

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check server.py tests/test_server_api_smoke.py`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_server_api_smoke.py -q`: passed; 6 passed, 1 warning.
- `git diff --check`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed; 341 passed, 1 warning.

### Files Changed
- `server.py`
- `tests/test_server_api_smoke.py`
- `README.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Direct API TestClient smoke posts `/api/evidence/local-cli-smoke`, downloads the smoke ZIP, then posts `/api/evidence/vault/{smoke_vault_id}/verify-smoke` and verifies PASS with 4 checked manifest files. Full local regression passed. The remaining warning is the known external Starlette TestClient/httpx fallback warning.

### Scope Check
No frontend/MCP/bridge change, vault schema change, smoke generation semantics change, package publish, real Abaqus executable/license, ODB extraction, Docker, GitHub/PyPI work, commit/push, or real Abaqus validation was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
V0.2-EVIDENCE-VAULT-BRIDGE-SMOKE-VERIFY-001

### Date
2026-06-05

### Status
Done

### Summary
HTTP-to-MCP bridge now exposes `POST /mcp/api/evidence/vault/{vault_id}/verify-smoke`, allowing HTTP agent clients to trigger local CLI smoke through the bridge and verify the resulting vault-stored `local_cli_smoke.zip` through the bridge path.

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check mcp_bridge.py tests/test_mcp_bridge_real_subprocess.py`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_mcp_bridge_real_subprocess.py -q`: passed; 1 passed, 1 warning.
- `git diff --check`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed; 341 passed, 1 warning.

### Files Changed
- `mcp_bridge.py`
- `tests/test_mcp_bridge_real_subprocess.py`
- `README.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Real HTTP-to-MCP bridge subprocess smoke posts `/mcp/api/evidence/local-cli-smoke`, then posts `/mcp/api/evidence/vault/{smoke_vault_id}/verify-smoke` with the returned `vault_root` and verifies PASS with 4 checked manifest files. Full local regression passed. The remaining warning is the known external Starlette TestClient/httpx fallback warning.

### Scope Check
No Direct API/frontend change, vault schema change, smoke generation semantics change, MCP verifier algorithm change, package publish, real Abaqus executable/license, ODB extraction, Docker, GitHub/PyPI work, commit/push, or real Abaqus validation was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
V0.2-EVIDENCE-VAULT-MCP-SMOKE-VERIFY-001

### Date
2026-06-05

### Status
Done

### Summary
MCP stdio now exposes `verify_evidence_vault_smoke_bundle_tool`, letting agent clients verify a `local-cli-smoke` vault entry's `local_cli_smoke.zip` by vault id and optional vault root without copying the ZIP or reconstructing its local path.

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check mcp_server.py tests/test_mcp_server.py tests/test_mcp_stdio_client.py`: first run failed once because an internal import block needed sorting; passed after formatting the import block.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_mcp_server.py tests/test_mcp_stdio_client.py -q`: passed; 38 passed.
- `git diff --check`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed; 341 passed, 1 warning.

### Files Changed
- `mcp_server.py`
- `tests/test_mcp_server.py`
- `tests/test_mcp_stdio_client.py`
- `README.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Direct MCP and real MCP stdio client tests generate a local CLI smoke ZIP, then verify the stored `local-cli-smoke` vault entry with `verify_evidence_vault_smoke_bundle_tool`. Full local regression passed. The remaining warning is the known external Starlette TestClient/httpx fallback warning.

### Scope Check
No vault storage schema change, smoke generation semantics change, HTTP bridge/frontend/API change, package publish, real Abaqus executable/license, ODB extraction, Docker, GitHub/PyPI work, commit/push, or real Abaqus validation was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
V0.2-EVIDENCE-VAULT-CLI-SMOKE-VERIFY-001

### Date
2026-06-05

### Status
Done

### Summary
Evidence Vault no-server CLI now supports `verify-smoke <vault_id>`, so a stored `local-cli-smoke` vault entry can verify its `local_cli_smoke.zip` against the embedded manifest without first copying the ZIP out of the vault.

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check scripts/inspect_evidence_vault.py tests/test_local_cli_smoke.py tests/test_evidence_vault.py`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_local_cli_smoke.py tests/test_evidence_vault.py -q`: passed; 11 passed.
- `/tmp/abaqus-agent-audit-venv/bin/abaqus-agent-vault --root /tmp/abaqus-agent-installed-cli-smoke-manifest/evidence-vault verify-smoke local-cli-smoke-20260605T071051Z-09a71283`: passed; returned PASS with 4 checked manifest files.
- `git diff --check`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed; 341 passed, 1 warning.

### Files Changed
- `scripts/inspect_evidence_vault.py`
- `tests/test_local_cli_smoke.py`
- `README.md`
- `RELEASE_INSTRUCTIONS.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Focused local smoke/vault tests verify a generated `local-cli-smoke` vault entry can be verified with `verify-smoke`. Installed `abaqus-agent-vault` probe verified the prior installed smoke vault ZIP and returned PASS for all manifest entries. Full local regression passed. The remaining warning is the known external Starlette TestClient/httpx fallback warning.

### Scope Check
No vault storage schema change, smoke generation semantics change, MCP/server/frontend/API change, package publish, real Abaqus executable/license, ODB extraction, Docker, GitHub/PyPI work, commit/push, or real Abaqus validation was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
V0.2-LOCAL-CLI-SMOKE-BUNDLE-VERIFY-MCP-001

### Date
2026-06-05

### Status
Done

### Summary
MCP stdio now exposes `verify_local_cli_smoke_bundle_tool`, so agent clients can verify a local `local_cli_smoke.zip` path against its embedded manifest without shelling out. The tool returns the same verifier JSON used by the no-server CLI verifier.

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check mcp_server.py tests/test_mcp_server.py tests/test_mcp_stdio_client.py`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_mcp_server.py tests/test_mcp_stdio_client.py -q`: passed; 38 passed.
- `git diff --check`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed; 341 passed, 1 warning.

### Files Changed
- `mcp_server.py`
- `tests/test_mcp_server.py`
- `tests/test_mcp_stdio_client.py`
- `README.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Direct MCP test verifies `verify_local_cli_smoke_bundle_tool` returns PASS for a ZIP generated by `run_local_cli_smoke_tool`. Real MCP stdio client smoke verifies the tool is listed and returns PASS after generating the ZIP over stdio transport. Full local regression passed. The remaining warning is the known external Starlette TestClient/httpx fallback warning.

### Scope Check
No verifier algorithm redesign, HTTP bridge/frontend/API change, smoke generation semantics change, vault schema change, package publish, real Abaqus executable/license, ODB extraction, Docker, GitHub/PyPI work, commit/push, or real Abaqus validation was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
V0.2-LOCAL-CLI-SMOKE-BUNDLE-VERIFY-001

### Date
2026-06-05

### Status
Done

### Summary
Added a no-server verifier for portable local CLI smoke ZIP bundles. Users and agents can now run `abaqus-agent-verify-local-cli-smoke path/to/local_cli_smoke.zip --json` to check the embedded `local_cli_smoke_manifest.json` against ZIP member sizes and SHA-256 hashes without extracting files.

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check scripts/verify_local_cli_smoke_bundle.py pyproject.toml tests/test_local_cli_smoke.py tests/test_cli_entrypoints.py`: first run failed once due an unused `sys` import; passed after removing it.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_local_cli_smoke.py tests/test_cli_entrypoints.py -q`: passed; 3 passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pip install -e ".[dev]"`: passed after adding the console entry point.
- `/tmp/abaqus-agent-audit-venv/bin/abaqus-agent-verify-local-cli-smoke /tmp/abaqus-agent-installed-cli-smoke-manifest/local_cli_smoke.zip --json`: passed; returned PASS with 4 checked manifest files.
- `git diff --check`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed; 341 passed, 1 warning.

### Files Changed
- `scripts/verify_local_cli_smoke_bundle.py`
- `pyproject.toml`
- `tests/test_local_cli_smoke.py`
- `tests/test_cli_entrypoints.py`
- `README.md`
- `RELEASE_INSTRUCTIONS.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Focused tests verify generated bundle PASS and tampered Markdown member FAIL. Installed CLI probe verified the previous installed smoke ZIP and reported PASS for JSON, Markdown, HTML, and copied demo pack ZIP manifest entries. Full local regression passed. The remaining warning is the known external Starlette TestClient/httpx fallback warning.

### Scope Check
No smoke generation semantics change, server/MCP/frontend change, vault schema change, package publish, real Abaqus executable/license, ODB extraction, Docker, GitHub/PyPI work, commit/push, or real Abaqus validation was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
V0.2-INSTALLED-LOCAL-CLI-SMOKE-MANIFEST-E2E-001

### Date
2026-06-05

### Status
Done

### Summary
Source-installed `abaqus-agent-local-cli-smoke` evidence was refreshed after the manifest ZIP change. The installed command now proves the user-facing console entry emits 11 PASS steps, JSON/Markdown/HTML/manifest/ZIP artifacts, a self-contained ZIP, and manifest size/SHA-256 entries that match disk files.

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/abaqus-agent-local-cli-smoke --out-dir /tmp/abaqus-agent-installed-cli-smoke-manifest --json`: passed; returned `overall_status=PASS`, 11 PASS steps, `manifest_path`, `zip_path`, and `smoke_vault_files` including `local_cli_smoke_manifest.json`.
- `/tmp/abaqus-agent-audit-venv/bin/python` artifact probe over `/tmp/abaqus-agent-installed-cli-smoke-manifest`: passed; verified generated JSON/Markdown/HTML/manifest/ZIP files, ZIP members, workflow/status/vault identity, and SHA-256/size matches for bundled files.

### Files Changed
- `README.md`
- `RELEASE_INSTRUCTIONS.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Installed command E2E and artifact integrity probe passed without changing runtime code. Probe verified ZIP members `copied-local-demo-pack.zip`, `local_cli_smoke.html`, `local_cli_smoke.json`, `local_cli_smoke.md`, and `local_cli_smoke_manifest.json`; manifest entries for bundled files have matching `size_bytes` and 64-character SHA-256 hashes.

### Scope Check
No package publish, wheel build/release upload, server/MCP/frontend behavior change, smoke semantics change, real Abaqus executable/license, ODB extraction, Docker, GitHub/PyPI work, commit/push, or real Abaqus validation was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
V0.2-LOCAL-CLI-SMOKE-ZIP-MANIFEST-001

### Date
2026-06-05

### Status
Done

### Summary
`local_cli_smoke.zip` 现在包含 `local_cli_smoke_manifest.json`。该 manifest 为 bundled smoke reports 和 `copied-local-demo-pack.zip` 记录 `filename`、`size_bytes`、`sha256`，并随 `local-cli-smoke` vault entry 一起持久化，portable no-server smoke evidence 更容易复核完整性。

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check scripts/run_local_cli_smoke.py tests/test_local_cli_smoke.py tests/test_server_api_smoke.py tests/test_mcp_server.py tests/test_mcp_stdio_client.py tests/test_mcp_bridge_real_subprocess.py`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_local_cli_smoke.py tests/test_server_api_smoke.py tests/test_mcp_server.py tests/test_mcp_stdio_client.py tests/test_mcp_bridge_real_subprocess.py -q`: first run failed once because `smoke_vault_files` content was correct but the ordered-list assertion did not match sorted output; passed after switching to set membership, with 46 passed, 1 warning.
- `git diff --check`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed; 340 passed, 1 warning.

### Files Changed
- `scripts/run_local_cli_smoke.py`
- `tests/test_local_cli_smoke.py`
- `tests/test_server_api_smoke.py`
- `tests/test_mcp_server.py`
- `tests/test_mcp_stdio_client.py`
- `tests/test_mcp_bridge_real_subprocess.py`
- `README.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Focused local/API/MCP smoke tests verify `local_cli_smoke_manifest.json` appears in `local_cli_smoke.zip` and the smoke vault file list. The manifest content is checked for workflow/vault identity, bundled `copied-local-demo-pack.zip`, and 64-character SHA-256 fields. Full local regression passed. The remaining warning is the known external Starlette TestClient/httpx fallback warning.

### Scope Check
No new smoke steps, server/MCP/frontend behavior refactor, real Abaqus executable/license, ODB extraction, Docker, PyPI/GitHub Release, pull/merge/commit/push, or real Abaqus validation was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
V0.2-LOCAL-CLI-SMOKE-SELF-CONTAINED-ZIP-001

### Date
2026-06-05

### Status
Done

### Summary
`local_cli_smoke.zip` 现在是自包含 smoke bundle：除 JSON/Markdown/HTML smoke reports 外，还包含通过 `evidence-vault-copy` 导出的 `copied-local-demo-pack.zip`。smoke vault entry 也记录该 copied demo pack ZIP，便于单独下载。

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check scripts/run_local_cli_smoke.py tests/test_local_cli_smoke.py tests/test_server_api_smoke.py tests/test_mcp_server.py tests/test_mcp_stdio_client.py tests/test_mcp_bridge_real_subprocess.py`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_local_cli_smoke.py tests/test_server_api_smoke.py tests/test_mcp_server.py tests/test_mcp_stdio_client.py tests/test_mcp_bridge_real_subprocess.py -q`: passed; 46 passed, 1 warning.
- `git diff --check`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed; 340 passed, 1 warning.

### Files Changed
- `scripts/run_local_cli_smoke.py`
- `tests/test_local_cli_smoke.py`
- `tests/test_server_api_smoke.py`
- `tests/test_mcp_server.py`
- `tests/test_mcp_stdio_client.py`
- `tests/test_mcp_bridge_real_subprocess.py`
- `README.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Focused local/API/MCP smoke tests verify `local_cli_smoke.zip` includes `copied-local-demo-pack.zip`, `local_cli_smoke.json`, `local_cli_smoke.md`, and `local_cli_smoke.html`. Full local regression passed. The remaining warning is the known external Starlette TestClient/httpx fallback warning.

### Scope Check
No new smoke steps, server/MCP/frontend behavior refactor, real Abaqus executable/license, ODB extraction, Docker, PyPI/GitHub Release, pull/merge/commit/push, or real Abaqus validation was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
V0.2-EVIDENCE-VAULT-MCP-COPY-001

### Date
2026-06-05

### Status
Done

### Summary
MCP stdio 增加 `copy_evidence_vault_file_tool`，agent clients 现在可以把 Evidence Vault artifact 复制到指定本地路径，包括 ZIP 等二进制 evidence bundle，不需要 shell CLI 或 HTTP server。

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check mcp_server.py tests/test_mcp_server.py tests/test_mcp_stdio_client.py`: first run failed once due undefined `tmp_path` in stdio test; passed after using existing `vault_dir`.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_mcp_server.py tests/test_mcp_stdio_client.py -q`: first run failed once for the same undefined `tmp_path`; passed after fix with 38 passed.
- `git diff --check`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed; 340 passed, 1 warning.

### Files Changed
- `mcp_server.py`
- `tests/test_mcp_server.py`
- `tests/test_mcp_stdio_client.py`
- `README.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Direct MCP test verifies ZIP artifact copy/export through `copy_evidence_vault_file_tool`. Real MCP stdio smoke verifies the new tool is listed, copies `evidence.json` over stdio transport, creates parent directories, and preserves content. Full local regression passed. The remaining warning is the known external Starlette TestClient/httpx fallback warning.

### Scope Check
No CLI/server/bridge/frontend changes, vault schema changes, destructive delete/mutate operations, real Abaqus executable/license, ODB extraction, Docker, PyPI/GitHub Release, pull/merge/commit/push, or real Abaqus validation was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
V0.2-LOCAL-CLI-SMOKE-VAULT-COPY-STEP-001

### Date
2026-06-05

### Status
Done

### Summary
Local CLI smoke 现在包含 `evidence-vault-copy` 步骤，通过 `scripts/inspect_evidence_vault.py copy` 从生成的 vault 导出 `local-demo-pack.zip`。no-server smoke 现在证明证据包可生成、可入库、也可从 vault 导出；CLI/API/MCP surfaces 报告 11 个 PASS steps。

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check scripts/run_local_cli_smoke.py tests/test_local_cli_smoke.py tests/test_server_api_smoke.py tests/test_mcp_server.py tests/test_mcp_stdio_client.py tests/test_mcp_bridge_real_subprocess.py`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_local_cli_smoke.py tests/test_server_api_smoke.py tests/test_mcp_server.py tests/test_mcp_stdio_client.py tests/test_mcp_bridge_real_subprocess.py -q`: passed; 46 passed, 1 warning.
- `git diff --check`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed; 340 passed, 1 warning.

### Files Changed
- `scripts/run_local_cli_smoke.py`
- `tests/test_local_cli_smoke.py`
- `tests/test_server_api_smoke.py`
- `tests/test_mcp_server.py`
- `tests/test_mcp_stdio_client.py`
- `tests/test_mcp_bridge_real_subprocess.py`
- `README.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Focused local/API/MCP smoke tests verify the new 11-step smoke count, all steps PASS, copied `local-demo-pack.zip` exists in the smoke output, and ZIP bundle surfaces still work through Direct API, MCP stdio, and HTTP-to-MCP bridge. Full local regression passed. The remaining warning is the known external Starlette TestClient/httpx fallback warning.

### Scope Check
No new report file types, server/MCP/frontend behavior refactor, real Abaqus executable/license, ODB extraction, Docker, PyPI/GitHub Release, pull/merge/commit/push, or real Abaqus validation was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
V0.2-EVIDENCE-VAULT-CLI-COPY-001

### Date
2026-06-05

### Status
Done

### Summary
Evidence Vault no-server CLI 增加 `copy <vault_id> <filename> --out <path>`，通过现有 vault path validation 导出文本或二进制 artifact，包括 `local_cli_smoke.zip` 这类 portable evidence bundle。

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check scripts/inspect_evidence_vault.py tests/test_evidence_vault.py`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_evidence_vault.py -q`: passed; 9 passed.
- `git diff --check`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed; 340 passed, 1 warning.

### Files Changed
- `scripts/inspect_evidence_vault.py`
- `tests/test_evidence_vault.py`
- `README.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Focused vault CLI test verifies `read` still rejects ZIP as text, then `copy` exports `local-demo-pack.zip` to a nested output path, creates parent directories, returns JSON metadata, and preserves file content. Full local regression passed. The remaining warning is the known external Starlette TestClient/httpx fallback warning.

### Scope Check
No server/MCP/frontend changes, vault schema changes, delete/mutate operations, real Abaqus executable/license, ODB extraction, Docker, PyPI/GitHub Release, pull/merge/commit/push, or real Abaqus validation was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
V0.2-LOCAL-CLI-SMOKE-MCP-ZIP-001

### Date
2026-06-05

### Status
Done

### Summary
MCP stdio `run_local_cli_smoke_tool` 现在显式返回 `zip_path` 和 `smoke_vault_files`，HTTP-to-MCP bridge 也通过同一返回体暴露 smoke ZIP。Direct MCP、real MCP stdio、real bridge subprocess tests 都验证 `local_cli_smoke.zip` 存在并包含 JSON/Markdown/HTML reports。

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check mcp_server.py tests/test_mcp_server.py tests/test_mcp_stdio_client.py tests/test_mcp_bridge_real_subprocess.py`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_mcp_server.py tests/test_mcp_stdio_client.py tests/test_mcp_bridge_real_subprocess.py -q`: passed; 39 passed, 1 warning.
- `git diff --check`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed; 340 passed, 1 warning.

### Files Changed
- `mcp_server.py`
- `tests/test_mcp_server.py`
- `tests/test_mcp_stdio_client.py`
- `tests/test_mcp_bridge_real_subprocess.py`
- `README.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Direct MCP test, real MCP stdio client smoke, and HTTP-to-MCP bridge subprocess smoke verify `zip_path`, `smoke_vault_files`, and ZIP membership for `local_cli_smoke.json`, `local_cli_smoke.md`, and `local_cli_smoke.html`. Full local regression passed. The remaining warning is the known external Starlette TestClient/httpx fallback warning.

### Scope Check
No new smoke step semantics, Direct API/frontend changes, real Abaqus executable/license, ODB extraction, Docker, PyPI/GitHub Release, pull/merge/commit/push, or real Abaqus validation was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
V0.2-LOCAL-CLI-SMOKE-ZIP-BUNDLE-001

### Date
2026-06-05

### Status
Done

### Summary
Local CLI smoke 现在生成 `local_cli_smoke.zip`，把 JSON/Markdown/HTML smoke report 打成一个可分享证据包，并持久化到 `local-cli-smoke` vault entry。Direct API smoke URLs 与 frontend Evidence/Vault/Case Memory rows 现在都能暴露这个 ZIP。

### Commands
- Static frontend JS parse/source probe for `local_cli_smoke.zip`, `SMOKE ZIP`, `btn-evidence-cli-smoke`, and `renderLocalCliSmokeResult`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check scripts/run_local_cli_smoke.py server.py tests/test_local_cli_smoke.py tests/test_server_api_smoke.py`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_local_cli_smoke.py tests/test_server_api_smoke.py -q`: passed; 7 passed, 1 warning.
- `git diff --check`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed; 340 passed, 1 warning.

### Files Changed
- `scripts/run_local_cli_smoke.py`
- `tests/test_local_cli_smoke.py`
- `tests/test_server_api_smoke.py`
- `frontend/index.html`
- `README.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Focused local CLI smoke test verifies `local_cli_smoke.zip` exists, contains `local_cli_smoke.json`, `local_cli_smoke.md`, and `local_cli_smoke.html`, and that bundled JSON carries the final smoke vault id. Focused TestClient smoke downloads the ZIP through `/api/evidence/vault/.../local_cli_smoke.zip` and verifies ZIP members. Full local regression passed. The remaining warning is the known external Starlette TestClient/httpx fallback warning.

### Scope Check
No new smoke step semantics, MCP stdio/bridge refactor, real Abaqus executable/license, ODB extraction, Docker, PyPI/GitHub Release, pull/merge/commit/push, or real Abaqus validation was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
V0.2-LOCAL-CLI-SMOKE-FRONTEND-001

### Date
2026-06-05

### Status
Done

### Summary
Frontend Evidence workspace 增加 `运行 CLI Smoke`，通过 Direct API `POST /api/evidence/local-cli-smoke` 触发 no-server local CLI smoke，并渲染 PASS/step/vault/report links。Direct API response 同时增加 `smoke_vault_urls`，让前端能打开 smoke JSON/Markdown/HTML vault artifacts。

### Commands
- Static frontend JS parse/source probe for `btn-evidence-cli-smoke`, `/api/evidence/local-cli-smoke`, `renderLocalCliSmokeResult`, `local_cli_smoke.html`, `smoke_vault_urls`, and `local-cli-smoke`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check server.py tests/test_server_api_smoke.py`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_server_api_smoke.py -q`: passed; 6 passed, 1 warning.
- Local HTTP probe against `127.0.0.1:8037/api/evidence/local-cli-smoke`: passed; returned `local-cli-smoke PASS 10` and smoke vault report URLs.
- `git diff --check`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed; 340 passed, 1 warning.

### Files Changed
- `server.py`
- `tests/test_server_api_smoke.py`
- `frontend/index.html`
- `README.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Focused TestClient smoke verifies `smoke_vault_urls["local_cli_smoke.html"]` and downloads the generated HTML report. Static frontend probe verifies the button, Direct API call, renderer, report filenames, and filter kind. Browser automation was attempted through Node/Python Playwright but blocked because Playwright/browser tooling is unavailable in this tool environment. Full local regression passed. The remaining warning is the known external Starlette TestClient/httpx fallback warning.

### Scope Check
No MCP stdio/bridge changes, real Abaqus executable/license, ODB extraction, Docker, PyPI/GitHub Release, pull/merge/commit/push, or real Abaqus validation was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
V0.2-LOCAL-CLI-SMOKE-DIRECT-API-001

### Date
2026-06-05

### Status
Done

### Summary
Direct API 增加 `POST /api/evidence/local-cli-smoke`，复用本地 CLI smoke collector，并显式使用 server 当前 Evidence Vault root。local HTTP clients 现在不经过 MCP 也能触发同一套 no-server product smoke evidence。

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check server.py tests/test_server_api_smoke.py`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_server_api_smoke.py -q`: passed; 6 passed, 1 warning.
- `git diff --check`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed; 340 passed, 1 warning.

### Files Changed
- `server.py`
- `tests/test_server_api_smoke.py`
- `README.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Focused TestClient smoke verifies the endpoint returns `workflow=local-cli-smoke`, `overall_status=PASS`, 10 PASS steps, generated JSON/Markdown/HTML paths/content, and a `local-cli-smoke-*` smoke vault id discoverable through Direct API Vault and Case Memory search. Full local regression passed. The remaining warning is the known external Starlette TestClient/httpx fallback warning.

### Scope Check
No frontend/browser, MCP stdio/bridge changes, real Abaqus executable/license, ODB extraction, Docker, PyPI/GitHub Release, pull/merge/commit/push, or real Abaqus validation was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
V0.2-LOCAL-CLI-SMOKE-MCP-BRIDGE-001

### Date
2026-06-05

### Status
Done

### Summary
HTTP-to-MCP bridge 增加 `POST /mcp/api/evidence/local-cli-smoke`，通过真实 `MCPConnection` 调用 MCP stdio `run_local_cli_smoke_tool`。HTTP agent clients 现在可触发同一套 no-server local CLI smoke evidence。

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check mcp_bridge.py tests/test_mcp_bridge_real_subprocess.py`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_mcp_bridge_real_subprocess.py -q`: passed; 1 passed, 1 warning.
- `git diff --check`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed; 340 passed, 1 warning.

### Files Changed
- `mcp_bridge.py`
- `tests/test_mcp_bridge_real_subprocess.py`
- `README.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Real bridge subprocess test verifies the endpoint returns `workflow=local-cli-smoke`, `overall_status=PASS`, 10 PASS steps, smoke vault id, report paths, report Markdown, and report HTML. Full local regression passed. No Direct API/frontend/browser, real Abaqus executable/license, or ODB was invoked. The remaining warning is the known external Starlette TestClient/httpx fallback warning.

### Scope Check
No Direct API, frontend, browser, real Abaqus/ODB execution, new smoke semantics, Docker, PyPI/GitHub Release, pull/merge/commit/push, or real Abaqus validation was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
V0.2-LOCAL-CLI-SMOKE-MCP-STDIO-001

### Date
2026-06-05

### Status
Done

### Summary
MCP stdio 增加 `run_local_cli_smoke_tool(out_dir="")`，让 agent clients 可以直接触发 no-server local CLI smoke，返回 PASS/step summaries、vault ids、JSON/Markdown/HTML report paths 和 report 内容。

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check mcp_server.py tests/test_mcp_server.py tests/test_mcp_stdio_client.py`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_mcp_server.py tests/test_mcp_stdio_client.py -q`: passed; 38 passed.
- `git diff --check`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed; 340 passed, 1 warning.

### Files Changed
- `mcp_server.py`
- `tests/test_mcp_server.py`
- `tests/test_mcp_stdio_client.py`
- `README.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Direct MCP server test verifies `run_local_cli_smoke_tool` returns PASS, 10 PASS steps, smoke vault id, JSON/Markdown/HTML paths, and report content. Real MCP stdio client smoke lists and calls the tool successfully. Full local regression passed. No Direct API/MCP bridge/frontend/server/browser, real Abaqus executable/license, or ODB was invoked. The remaining warning is the known external Starlette TestClient/httpx fallback warning.

### Scope Check
No Direct API, MCP bridge, frontend, server/browser, real Abaqus/ODB execution, new smoke semantics beyond calling the existing collector, Docker, PyPI/GitHub Release, pull/merge/commit/push, or real Abaqus validation was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
V0.2-RELEASE-LOCAL-CLI-SMOKE-CHECKLIST-001

### Date
2026-06-05

### Status
Done

### Summary
更新 `RELEASE_INSTRUCTIONS.md`，把 installed no-server CLI smoke 纳入 Local Verification、release highlights、verified audit evidence、install command examples，并明确它不是真实 Abaqus 执行证明。

### Commands
- `git diff --check`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed; 339 passed, 1 warning.

### Files Changed
- `RELEASE_INSTRUCTIONS.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Release checklist update is documentation/launch-readiness only. Full local regression passed. No GitHub release creation, PyPI publishing, remote mutation, server/browser, real Abaqus executable/license, Docker, or ODB was invoked. The remaining warning is the known external Starlette TestClient/httpx fallback warning.

### Scope Check
No GitHub Release creation, PyPI publishing, remote state mutation, version/tag change, code behavior change, real Abaqus/Docker execution, pull/merge/commit/push, or real Abaqus validation was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
V0.2-INSTALLED-LOCAL-CLI-SMOKE-E2E-001

### Date
2026-06-05

### Status
Done

### Summary
验证安装后的 `abaqus-agent-local-cli-smoke` 命令能完整跑通 no-server 产品 smoke。命令输出 `workflow=local-cli-smoke`、`overall_status=PASS`、10 个 step 全 PASS，并生成 JSON/Markdown/HTML 和 `local-cli-smoke-*` vault entry。

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/abaqus-agent-local-cli-smoke --out-dir /tmp/abaqus-agent-installed-cli-smoke --json`: passed; returned `overall_status=PASS`, 10 PASS steps, and `smoke_vault_id=local-cli-smoke-20260605T060031Z-ba034542`.
- Artifact probe over `/tmp/abaqus-agent-installed-cli-smoke/local_cli_smoke.json` / `.md` / `.html` and vault-stored HTML: passed; returned `workflow=local-cli-smoke`, `overall_status=PASS`, `step_count=10`.
- `git diff --check`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed; 339 passed, 1 warning.

### Files Changed
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Installed console command E2E smoke generated the full no-server product evidence bundle from the command entry point. Full local regression passed. No code changes were needed. No server, browser, package publish, real Abaqus executable/license, or ODB was invoked. The remaining warning is the known external Starlette TestClient/httpx fallback warning.

### Scope Check
No code behavior changes, server/browser/real Abaqus/ODB execution, package publishing/version bump, Docker, PyPI/GitHub Release, pull/merge/commit/push, or real Abaqus validation was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
V0.2-NO-SERVER-CLI-INSTALL-SMOKE-001

### Date
2026-06-05

### Status
Done

### Summary
验证 no-server CLI entry points 的真实 editable install 路径。`pip install -e ".[dev]"` 成功，5 个新 console commands 都能返回 `--help`，`abaqus-agent-kpi-recipes list --case modal --kpi-type eigenfrequency` 返回 JSON `workflow=kpi-recipe-gallery` / `total=1`。

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m pip install -e ".[dev]"`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/abaqus-agent-local-cli-smoke --help`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/abaqus-agent-vault --help`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/abaqus-agent-case-memory --help`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/abaqus-agent-kpi-recipes --help`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/abaqus-agent-doctor-patterns --help`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/abaqus-agent-kpi-recipes list --case modal --kpi-type eigenfrequency`: passed; returned `workflow=kpi-recipe-gallery`, `total=1`.
- `git diff --check`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed; 339 passed, 1 warning.

### Files Changed
- `README.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Editable install and console command smoke verified installed entry points without starting a server or requiring any vault data for the JSON probe. Full local regression passed. No package publish, browser, real Abaqus executable/license, or ODB was invoked. The remaining warning is the known external Starlette TestClient/httpx fallback warning.

### Scope Check
No code behavior changes, package publishing/version bump, server/API/MCP/frontend change, real Abaqus/ODB execution, Docker, PyPI/GitHub Release, pull/merge/commit/push, or real Abaqus validation was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
V0.2-NO-SERVER-CLI-ENTRYPOINTS-001

### Date
2026-06-05

### Status
Done

### Summary
No-server local CLI tools 现在有 pyproject console entry points：`abaqus-agent-local-cli-smoke`、`abaqus-agent-vault`、`abaqus-agent-case-memory`、`abaqus-agent-kpi-recipes`、`abaqus-agent-doctor-patterns`。`scripts` 也纳入 wheel package 配置，source install 后可作为命令使用。

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check tests/test_cli_entrypoints.py scripts/__init__.py`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_cli_entrypoints.py -q`: passed; 1 passed.
- `git diff --check`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed; 339 passed, 1 warning.

### Files Changed
- `pyproject.toml`
- `scripts/__init__.py`
- `tests/test_cli_entrypoints.py`
- `README.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Focused test parses `pyproject.toml`, verifies all no-server CLI command targets, imports each target module, checks the target `main` callable, and confirms `scripts` is listed in wheel packages. Full local regression passed. No package publish/install, server, browser, real Abaqus executable/license, or ODB was invoked. The remaining warning is the known external Starlette TestClient/httpx fallback warning.

### Scope Check
No package publishing/version bump, command behavior change, server/API/MCP/frontend change, real Abaqus/ODB execution, Docker, PyPI/GitHub Release, pull/merge/commit/push, or real Abaqus validation was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
V0.2-LOCAL-CLI-SMOKE-HTML-001

### Date
2026-06-05

### Status
Done

### Summary
Local CLI smoke report 增加 `local_cli_smoke.html`，并把 HTML 与 JSON/Markdown 一起持久化到 `local-cli-smoke` Evidence Vault entry。Demo/handoff review 可以直接打开 HTML 查看总体状态、vault id、step table 和 no-real-Abaqus boundary。

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check scripts/run_local_cli_smoke.py tests/test_local_cli_smoke.py`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_local_cli_smoke.py -q`: passed; 1 passed.
- `git diff --check`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed; 338 passed, 1 warning.

### Files Changed
- `scripts/run_local_cli_smoke.py`
- `tests/test_local_cli_smoke.py`
- `README.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Focused test verifies `local_cli_smoke.html` exists, includes title, step table, smoke vault id, and no-real-Abaqus boundary, and that the smoke vault entry records HTML/JSON/Markdown report files. Full local regression passed. No server, browser, real Abaqus executable/license, or ODB was invoked. The remaining warning is the known external Starlette TestClient/httpx fallback warning.

### Scope Check
No server startup/browser automation, real Abaqus/ODB execution, new smoke semantics, API/MCP/frontend changes, CSS framework/assets, Docker, PyPI/GitHub Release, pull/merge/commit/push, or real Abaqus validation was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
V0.2-LOCAL-CLI-SMOKE-VAULT-ENTRY-001

### Date
2026-06-05

### Status
Done

### Summary
Local CLI smoke report 现在会把自身 JSON/Markdown 结果持久化为 `local-cli-smoke` Evidence Vault entry。Smoke 完成后，Vault 和 Case Memory inspect CLI 可以直接搜索到这次 no-server 产品 smoke 证据。

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check scripts/run_local_cli_smoke.py tests/test_local_cli_smoke.py`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_local_cli_smoke.py -q`: passed; 1 passed.
- `git diff --check`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed; 338 passed, 1 warning.

### Files Changed
- `scripts/run_local_cli_smoke.py`
- `tests/test_local_cli_smoke.py`
- `README.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Focused test verifies the smoke report includes `smoke_vault_id`, the report Markdown includes that id, and both Evidence Vault CLI and Case Memory CLI can find the `local-cli-smoke` entry by `local_cli_smoke.md` with PASS status. Full local regression passed. No server, browser, real Abaqus executable/license, or ODB was invoked. The remaining warning is the known external Starlette TestClient/httpx fallback warning.

### Scope Check
No server startup/browser automation, real Abaqus/ODB execution, new smoke semantics beyond report persistence, API/MCP/frontend changes, Docker, PyPI/GitHub Release, pull/merge/commit/push, or real Abaqus validation was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
V0.2-LOCAL-CLI-SMOKE-REPORT-001

### Date
2026-06-05

### Status
Done

### Summary
新增 no-server 本地 CLI smoke report。脚本生成 Local Demo Pack，写入临时 Evidence Vault，再用真实子进程调用 Evidence Vault、Case Memory、KPI Recipe、Solver Doctor Pattern inspect CLIs，最后输出 `local_cli_smoke.json` / `local_cli_smoke.md` 作为本地产品面证据。

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check scripts/run_local_cli_smoke.py tests/test_local_cli_smoke.py`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_local_cli_smoke.py -q`: passed; 1 passed.
- `git diff --check`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed; 338 passed, 1 warning.

### Files Changed
- `scripts/run_local_cli_smoke.py`
- `tests/test_local_cli_smoke.py`
- `README.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Focused test runs the smoke script, verifies PASS report status, generated report files, temporary vault/demo pack artifacts, all expected CLI smoke steps, exported KPI spec, nested Case Memory diff report, and no-real-Abaqus boundary text. Full local regression passed. No server, browser, real Abaqus executable/license, or ODB was invoked. The remaining warning is the known external Starlette TestClient/httpx fallback warning.

### Scope Check
No server startup/browser automation, real Abaqus/ODB execution, new product semantics beyond smoke orchestration, API/MCP/frontend changes, Docker, PyPI/GitHub Release, pull/merge/commit/push, or real Abaqus validation was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
V0.2-SOLVER-DOCTOR-PATTERNS-CLI-001

### Date
2026-06-05

### Status
Done

### Summary
Solver Doctor Pattern Catalog 增加 no-server 本地 CLI。用户可不启动 FastAPI、MCP bridge 或 MCP stdio，直接按 category/severity 列出诊断 pattern，并按稳定 pattern id 查看 source file、regex、severity、explanation、recommendation 和 no-real-env boundary。

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check scripts/inspect_solver_doctor_patterns.py tests/test_solver_doctor_patterns_cli.py`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_solver_doctor_patterns_cli.py -q`: passed; 2 passed.
- `git diff --check`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed; 337 passed, 1 warning.

### Files Changed
- `scripts/inspect_solver_doctor_patterns.py`
- `tests/test_solver_doctor_patterns_cli.py`
- `README.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Focused subprocess tests cover category/severity filtered list, detail by pattern id, and missing-id JSON error. Full local regression passed. No diagnostic semantics or parser patterns were changed; no real Abaqus executable/license/ODB/log corpus validation was invoked. The remaining warning is the known external Starlette TestClient/httpx fallback warning.

### Scope Check
No diagnostic semantic rewrites, new parser patterns, LLM repair planner, real Abaqus/log corpus validation claims, frontend/API/MCP changes, Docker, PyPI/GitHub Release, pull/merge/commit/push, or real Abaqus validation was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
V0.2-KPI-RECIPES-CLI-EXPORT-001

### Date
2026-06-05

### Status
Done

### Summary
ODB Lens KPI Recipes 增加 no-server 本地 CLI。用户可不启动 FastAPI、MCP bridge 或 MCP stdio，直接 `list` / `detail` 内置 recipes，并通过 `export` 写出可交给 `post/extract_kpis.py` 的 `kpi_spec` JSON；该命令只导出 spec，不运行 Abaqus/ODB。

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check scripts/inspect_kpi_recipes.py tests/test_kpi_recipes_cli.py`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_kpi_recipes_cli.py -q`: passed; 2 passed.
- `git diff --check`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed; 335 passed, 1 warning.

### Files Changed
- `scripts/inspect_kpi_recipes.py`
- `tests/test_kpi_recipes_cli.py`
- `README.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Focused subprocess tests cover filtered list, detail boundary metadata, export file content, command hint, and missing-recipe JSON error. Full local regression passed. No real Abaqus executable/license/ODB was invoked. The remaining warning is the known external Starlette TestClient/httpx fallback warning.

### Scope Check
No new KPI extraction semantics, ODB/Abaqus execution, recipe authoring/mutation, frontend/API/MCP changes, auth/storage work, Docker, PyPI/GitHub Release, pull/merge/commit/push, or real Abaqus validation was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
V0.2-CASE-MEMORY-CLI-INSPECT-001

### Date
2026-06-05

### Status
Done

### Summary
Case Memory 增加 no-server 本地 CLI inspector。用户可不启动 FastAPI、MCP bridge 或 MCP stdio，直接通过 `search` / `detail` / `diff` 检查并比较本地证据记忆；`diff` 复用现有 Case Memory diff 服务，支持 safe nested `evidence.json` / `diff.json` 文件名并写出本地 `diff.json` / `diff.md`。

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check scripts/inspect_case_memory.py tests/test_case_memory.py`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_case_memory.py -q`: passed; 2 passed.
- `git diff --check`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed; 333 passed, 1 warning.

### Files Changed
- `scripts/inspect_case_memory.py`
- `tests/test_case_memory.py`
- `README.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Focused subprocess tests cover search/detail/diff and unsafe nested filename rejection through existing vault safety checks. Full local regression passed. No real Abaqus executable/license/ODB was invoked. The remaining warning is the known external Starlette TestClient/httpx fallback warning.

### Scope Check
No mutation/delete/edit command, embeddings/vector database, auth/multi-user storage, schema migration, frontend/API/MCP changes, Docker, PyPI/GitHub Release, pull/merge/commit/push, or real Abaqus validation was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
V0.2-EVIDENCE-VAULT-CLI-INSPECT-001

### Date
2026-06-05

### Status
Done

### Summary
Evidence Vault 增加 no-server 本地 CLI inspector。用户可不启动 FastAPI、MCP bridge 或 MCP stdio，直接通过 `list` / `detail` / `read` 检查本地持久证据；`list` 支持 `query` / `kind` / `status` / `limit`，`read` 只读取安全文本证据并拒绝 ZIP/未知后缀。

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check scripts/inspect_evidence_vault.py tests/test_evidence_vault.py`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_evidence_vault.py -q`: passed; 9 passed.
- `git diff --check`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed; 331 passed, 1 warning.

### Files Changed
- `scripts/inspect_evidence_vault.py`
- `tests/test_evidence_vault.py`
- `README.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Focused tests run the CLI as a real subprocess for list/detail/read and unsupported ZIP read. Full local regression passed. No real Abaqus executable/license/ODB was invoked. The remaining warning is the known external Starlette TestClient/httpx fallback warning.

### Scope Check
No mutation/delete/edit command, auth/multi-user storage, schema migration, frontend/API/MCP changes, Docker, PyPI/GitHub Release, pull/merge/commit/push, or real Abaqus validation was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
V0.2-EVIDENCE-VAULT-MCP-FILE-READ-001

### Date
2026-06-05

### Status
Done

### Summary
Evidence Vault 增加 MCP stdio 安全文本文件读取工具。Agent clients 在找到 vault record 后，可读取 `.json` / `.md` / `.html` 证据内容；ZIP/未知后缀和 unsafe filename 返回结构化错误。

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check mcp_server.py tests/test_mcp_server.py tests/test_mcp_stdio_client.py`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_mcp_server.py tests/test_mcp_stdio_client.py -q`: passed; 37 passed.
- `git diff --check`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed; 330 passed, 1 warning.

### Files Changed
- `mcp_server.py`
- `tests/test_mcp_server.py`
- `tests/test_mcp_stdio_client.py`
- `README.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Direct MCP tests cover normal/truncated/unsupported/unsafe reads. Real MCP stdio client smoke calls `read_evidence_vault_file_tool` on a stored `evidence.json`. No real Abaqus executable/license/ODB was invoked. The remaining warning is the known external Starlette TestClient/httpx fallback warning.

### Scope Check
No binary transfer/download transport, file mutation/delete/edit, auth/multi-user storage, schema migration, Direct API/MCP bridge/frontend changes, Docker, PyPI/GitHub Release, pull/merge/commit/push, or real Abaqus validation was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
V0.2-EVIDENCE-VAULT-MCP-STDIO-001

### Date
2026-06-05

### Status
Done

### Summary
Evidence Vault list/search/detail 暴露到 MCP stdio。Agent clients 现在可通过 resource 和 tools 检查本地持久证据，而不依赖 Direct API 或 HTTP bridge。

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check mcp_server.py tests/test_mcp_server.py tests/test_mcp_stdio_client.py`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_mcp_server.py tests/test_mcp_stdio_client.py -q`: passed; 37 passed.
- `git diff --check`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed; 330 passed, 1 warning.

### Files Changed
- `mcp_server.py`
- `tests/test_mcp_server.py`
- `tests/test_mcp_stdio_client.py`
- `README.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Direct MCP tool/resource tests cover Vault search/detail/resource. Real MCP stdio client smoke lists the new tools/resource, reads `evidence-vault://entries`, calls `search_evidence_vault_tool`, and calls `get_evidence_vault_record_tool`. No real Abaqus executable/license/ODB was invoked. The remaining warning is the known external Starlette TestClient/httpx fallback warning.

### Scope Check
No mutation/delete/edit endpoints, auth/multi-user storage, schema migration, frontend redesign, Direct API/MCP bridge changes, Docker, PyPI/GitHub Release, pull/merge/commit/push, or real Abaqus validation was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
V0.2-EVIDENCE-VAULT-DETAIL-001

### Date
2026-06-05

### Status
Done

### Summary
Evidence Vault 增加单条记录详情。Direct API、MCP bridge 和前端都能打开某个 vault record，查看 summary 和文件列表；旧的 unsafe nested path 400 边界保持不变。

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check evidence/vault.py server.py mcp_bridge.py tests/test_evidence_vault.py tests/test_server_api_smoke.py tests/test_mcp_bridge_real_subprocess.py`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_evidence_vault.py tests/test_server_api_smoke.py tests/test_mcp_bridge_real_subprocess.py -q`: passed; 15 passed, 1 warning.
- Static frontend script/source probe: passed for Evidence Vault detail button, detail request, and detail render hooks.
- Browser smoke on `127.0.0.1:8036`: passed; generated Demo Pack, searched `local-demo-pack.zip`, clicked `详情`, and verified detail text contains `kind=local-demo-pack`, `overall_status=PASS`, and `local-demo-pack.zip`. Screenshot saved to `/tmp/abaqus-agent-vault-detail-smoke.png`.
- `git diff --check`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed; 328 passed, 1 warning.

### Files Changed
- `evidence/vault.py`
- `server.py`
- `mcp_bridge.py`
- `frontend/index.html`
- `tests/test_evidence_vault.py`
- `tests/test_server_api_smoke.py`
- `tests/test_mcp_bridge_real_subprocess.py`
- `README.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
No real Abaqus executable/license/ODB was invoked. Detail lookup is read-only local vault metadata inspection. The remaining warning is the known external Starlette TestClient/httpx fallback warning.

### Scope Check
No mutation/delete/edit endpoints, vault schema migration, auth/multi-user storage, broad frontend redesign, Docker, PyPI/GitHub Release, pull/merge/commit/push, or real Abaqus validation was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
V0.2-EVIDENCE-VAULT-TEXT-SEARCH-001

### Date
2026-06-05

### Status
Done

### Summary
Evidence Vault 主列表增加文本搜索，可按 vault id、kind、title、derived status、summary JSON 和存储文件名查找记录，并可与 kind/status 过滤组合使用。

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check evidence/vault.py server.py mcp_bridge.py tests/test_evidence_vault.py tests/test_server_api_smoke.py tests/test_mcp_bridge_real_subprocess.py`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_evidence_vault.py tests/test_server_api_smoke.py tests/test_mcp_bridge_real_subprocess.py -q`: passed; 15 passed, 1 warning.
- Static frontend script/source probe: passed for Evidence Vault text search controls and query/kind/status request wiring.
- Browser smoke on `127.0.0.1:8035`: passed; verified `query=local-demo-pack.zip` isolates the pack row and `query=case-memory-diff&kind=case-memory-diff&status=FAIL` isolates the diff row, with no browser console errors. Screenshot saved to `/tmp/abaqus-agent-vault-search-smoke.png`.
- `git diff --check`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed; 328 passed, 1 warning.

### Files Changed
- `evidence/vault.py`
- `server.py`
- `mcp_bridge.py`
- `frontend/index.html`
- `tests/test_evidence_vault.py`
- `tests/test_server_api_smoke.py`
- `tests/test_mcp_bridge_real_subprocess.py`
- `README.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
No real Abaqus executable/license/ODB was invoked. Search is a lightweight local record scan, not a full-text database, semantic/vector search, or multi-user storage feature. The remaining warning is the known external Starlette TestClient/httpx fallback warning.

### Scope Check
No vault schema migration, auth/multi-user storage, broad frontend redesign, Docker, PyPI/GitHub Release, pull/merge/commit/push, or real Abaqus validation was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
V0.2-EVIDENCE-VAULT-FILTERS-001

### Date
2026-06-05

### Status
Done

### Summary
Evidence Vault 主列表增加 kind/status 过滤。Vault service、Direct API、MCP bridge、frontend Evidence Vault 面板都能按证据类型和 summary-derived status 定位本地证据记录。

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check evidence/vault.py server.py mcp_bridge.py tests/test_evidence_vault.py tests/test_server_api_smoke.py tests/test_mcp_bridge_real_subprocess.py`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_evidence_vault.py tests/test_server_api_smoke.py tests/test_mcp_bridge_real_subprocess.py -q`: passed; 15 passed, 1 warning.
- Static frontend script/source probe: passed for Evidence Vault filter controls and query wiring.
- Browser smoke on `127.0.0.1:8034`: passed; generated Demo Pack, created nested Case Memory diff, verified `local-demo-pack + PASS` and `case-memory-diff + FAIL` filters isolate one row each, and recorded no console errors. Screenshot saved to `/tmp/abaqus-agent-vault-filters-smoke.png`.
- `git diff --check`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed; 328 passed, 1 warning.

### Files Changed
- `evidence/vault.py`
- `server.py`
- `mcp_bridge.py`
- `frontend/index.html`
- `tests/test_evidence_vault.py`
- `tests/test_server_api_smoke.py`
- `tests/test_mcp_bridge_real_subprocess.py`
- `README.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
No real Abaqus executable/license/ODB was invoked. Filtering is over local filesystem vault records and their stored summaries only. The remaining warning is the known external Starlette TestClient/httpx fallback warning.

### Scope Check
No vault schema migration, auth/multi-user storage, broad frontend redesign, Docker, PyPI/GitHub Release, pull/merge/commit/push, or real Abaqus validation was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
V0.2-SOLVER-DOCTOR-PATTERN-GALLERY-001

### Date
2026-06-05

### Status
Done

### Summary
Exposed the existing deterministic Solver Doctor parser scope as a discoverable
Pattern Gallery. Users and agent clients can now inspect supported categories,
severity, source file, regex signatures, explanations, and recommendations
through Direct API, MCP bridge, MCP stdio, and the frontend Solver Doctor
workspace.

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_solver_doctor.py tests/test_server_api_smoke.py tests/test_mcp_bridge_real_subprocess.py tests/test_mcp_server.py tests/test_mcp_stdio_client.py -q`: passed, 48 passed / 1 warning.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check premium/autorepair/log_parser.py doctor server.py mcp_bridge.py mcp_server.py tests/test_solver_doctor.py tests/test_server_api_smoke.py tests/test_mcp_bridge_real_subprocess.py tests/test_mcp_server.py tests/test_mcp_stdio_client.py`: passed.
- Static frontend source probe confirmed `Pattern Gallery`, `doctor-pattern-count`, `btn-doctor-patterns-refresh`, `/api/doctor/patterns`, `loadDoctorPatterns`, `renderDoctorPatterns`, and `doctor-patterns`.
- Actual HTTP probe against `uvicorn server:app --host 127.0.0.1 --port 8012`: `/api/doctor/patterns` returned 24 parser patterns across 15 categories; `category=license&severity=error` returned 2 filtered patterns with recommendations.
- `git diff --check`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed, 318 passed / 1 warning.

### Files Changed
- `premium/autorepair/log_parser.py`
- `doctor/solver_doctor.py`
- `server.py`
- `mcp_bridge.py`
- `mcp_server.py`
- `frontend/index.html`
- `tests/test_solver_doctor.py`
- `tests/test_server_api_smoke.py`
- `tests/test_mcp_bridge_real_subprocess.py`
- `tests/test_mcp_server.py`
- `tests/test_mcp_stdio_client.py`
- `README.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`
- `docs/goal_driver/NEXT_TICKETS.md`

### Tests
No real Abaqus executable/license/log corpus was invoked. The pattern gallery
documents current deterministic parser signatures only; it does not prove
coverage against real customer failure logs. The remaining warning is the
previously audited external Starlette TestClient/httpx fallback warning.

### Scope Check
No diagnostic semantic rewrites, LLM repair planner changes, real Abaqus/log
corpus validation claims, broad frontend redesign, Docker, PyPI/GitHub Release,
pull/merge/commit/push, or real Abaqus validation was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
V0.2-FRONTEND-EVIDENCE-LIST-OVERFLOW-HARDENING-001

### Date
2026-06-05

### Status
Done

### Summary
前端 Evidence recent/list 行布局硬化：右侧链接列可收缩换行，长 regex/nested filenames/details 不再制造水平 overflow，并保留窄宽度单列 fallback。

### Commands
- Static CSS/source probe: passed.
- Browser smoke on `127.0.0.1:8033`: passed; opened Solver Doctor Pattern Gallery, filtered `LICENSE + ERROR`, opened `msg-10-license` detail, and verified document, pattern rows, link containers, and detail panel had no horizontal overflow.
- `git diff --check`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed; 327 passed, 1 warning.

### Files Changed
- `frontend/index.html`
- `README.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
- Existing detail/filter UI still loads.
- Browser overflow probe checked document/row/link/detail `scrollWidth <= clientWidth`.
- The remaining warning is the known external Starlette TestClient/httpx fallback warning.

### Scope Check
Frontend CSS/layout hardening and checkpoint docs only. No backend changes, no broad redesign, no data model changes, no real Abaqus/ODB, no Docker/release/GitHub operation.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
V0.2-FRONTEND-SOLVER-DOCTOR-PATTERN-DETAIL-001

### Date
2026-06-05

### Status
Done

### Summary
前端 Solver Doctor Pattern Gallery 行增加详情动作，渲染 pattern regex、explanation、recommendation 和 real-env boundary，便于检查 deterministic parser 覆盖含义。

### Commands
- Static frontend script parse/source probe: passed.
- Browser smoke on `127.0.0.1:8032`: passed; filtered `LICENSE + ERROR`, clicked `msg-10-license`, and observed license regex, explanation, recommendation, and `real_env_verified=false`.
- `git diff --check`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed; 327 passed, 1 warning.

### Files Changed
- `frontend/index.html`
- `README.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
- Existing pattern filtering still works.
- Changing filters clears stale pattern detail.
- The remaining warning is the known external Starlette TestClient/httpx fallback warning.

### Scope Check
Frontend detail rendering and checkpoint docs only. No backend/parser changes, no taxonomy changes, no repair planner changes, no real Abaqus/log corpus validation claims, no Docker/release/GitHub operation.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
V0.2-FRONTEND-SOLVER-DOCTOR-PATTERN-FILTERS-001

### Date
2026-06-05

### Status
Done

### Summary
前端 Solver Doctor Pattern Gallery 增加 category/severity 过滤控件，调用已有 `/api/doctor/patterns?category=...&severity=...` 参数，便于按失败类型检查确定性 parser 覆盖范围。

### Commands
- Static frontend script parse/source probe: passed.
- Browser smoke on `127.0.0.1:8031`: passed; full list showed 24 patterns, `category=LICENSE` isolated LICENSE rows, and `category=LICENSE` + `severity=ERROR` isolated `LICENSE · ERROR` rows.
- `git diff --check`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed; 327 passed, 1 warning.

### Files Changed
- `frontend/index.html`
- `README.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
- Existing unfiltered pattern list still loads.
- New category/severity controls send existing backend filter params.
- The remaining warning is the known external Starlette TestClient/httpx fallback warning.

### Scope Check
Frontend filter controls and checkpoint docs only. No backend/parser changes, no taxonomy changes, no real Abaqus/log corpus validation claims, no Docker/release/GitHub operation.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
V0.2-FRONTEND-KPI-RECIPE-DETAIL-001

### Date
2026-06-05

### Status
Done

### Summary
前端 KPI Recipes 行增加详情动作，调用已有 `/api/kpi-recipes/{recipe_id}` 并渲染 `kpi_spec`、`kpi_types` 和 verification boundary，便于检查 ODB Lens 提取定义。

### Commands
- Static frontend script parse/source probe: passed.
- Browser smoke on `127.0.0.1:8030`: passed; filtered `case=modal`, clicked `modal-first-three-frequencies` detail, and observed `kpi_spec`, three `eigenfrequency` entries, and `verification_boundary`.
- `git diff --check`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed; 327 passed, 1 warning.

### Files Changed
- `frontend/index.html`
- `README.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
- Existing recipe filtering still works.
- Changing filters clears stale recipe detail.
- The remaining warning is the known external Starlette TestClient/httpx fallback warning.

### Scope Check
Frontend detail rendering and checkpoint docs only. No backend API changes, no recipe schema/model changes, no recipe editing UI, no real ODB/Abaqus runtime, no Docker/release/GitHub operation.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
V0.2-FRONTEND-KPI-RECIPE-FILTERS-001

### Date
2026-06-05

### Status
Done

### Summary
前端 KPI Recipes 面板增加 case/type 过滤控件，调用已有 `/api/kpi-recipes?case=...&kpi_type=...` 参数，让 ODB Lens recipe gallery 更可用。

### Commands
- Static frontend script parse/source probe: passed.
- Browser smoke on `127.0.0.1:8029`: passed; full list showed 6 recipes, `case=modal` isolated `First three modal frequencies`, and `case=plate_hole` + `kpi_type=field_max` isolated `Plate-hole max Mises stress`.
- `git diff --check`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed; 327 passed, 1 warning.

### Files Changed
- `frontend/index.html`
- `README.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
- Existing unfiltered recipe list still loads.
- New case/type controls send existing backend filter params.
- The remaining warning is the known external Starlette TestClient/httpx fallback warning.

### Scope Check
Frontend filter controls and checkpoint docs only. No backend API changes, no recipe schema/model changes, no recipe authoring UI, no real ODB/Abaqus runtime, no Docker/release/GitHub operation.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
V0.2-FRONTEND-CASE-MEMORY-FILTERS-001

### Date
2026-06-05

### Status
Done

### Summary
前端 Case Memory 搜索行增加 kind/status 过滤控件，调用已有 `/api/case-memory` query params，便于定位 demo pack、diff、doctor 等本地证据记录。

### Commands
- Static frontend script parse/source probe: passed.
- Browser smoke on `127.0.0.1:8028`: passed; generated Demo Pack and nested Case Memory diff, filtered `kind=case-memory-diff` + `status=FAIL` to isolate the diff row, then filtered `kind=local-demo-pack` + `status=PASS` to isolate the demo pack row.
- `git diff --check`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed; 327 passed, 1 warning.

### Files Changed
- `frontend/index.html`
- `README.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
- Existing text search still works through the same search action.
- Existing refresh/diff completion paths preserve current filters by calling `loadCaseMemory()` with current controls.
- The remaining warning is the known external Starlette TestClient/httpx fallback warning.

### Scope Check
Frontend filter controls and checkpoint docs only. No backend API changes, no search/index engine, no embeddings/vector search, no real Abaqus/ODB, no Docker/release/GitHub operation.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
V0.2-FRONTEND-CASE-MEMORY-FILENAME-SUGGESTIONS-001

### Date
2026-06-05

### Status
Done

### Summary
前端 Case Memory Diff filename 输入框增加 datalist 建议，建议来自选中 Case Memory row 的可比较 JSON 文件；不自动填值，保留 vault-id-only 默认行为。

### Commands
- Static frontend script parse/source probe: passed.
- Browser smoke on `127.0.0.1:8027`: passed; generated Demo Pack, selected baseline/candidate row buttons, confirmed nested suggestions for cantilever/plate-hole/modal/explicit-impact evidence and `simulation-diff/diff.json`, confirmed filename inputs remained empty, filled two suggestions, clicked `Diff`, and observed `FAIL · 4 rows` plus new `case-memory-diff · FAIL`.
- `git diff --check`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed; 327 passed, 1 warning.

### Files Changed
- `frontend/index.html`
- `README.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
- Manual filename diff still works.
- Filename suggestions are populated from row files and do not auto-fill inputs.
- The remaining warning is the known external Starlette TestClient/httpx fallback warning.

### Scope Check
Frontend suggestion workflow and checkpoint docs only. No backend API changes, no broad picker redesign, no automatic filename selection, no real Abaqus/ODB, no Docker/release/GitHub operation.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
V0.2-FRONTEND-CASE-MEMORY-NESTED-FILENAME-DIFF-001

### Date
2026-06-05

### Status
Done

### Summary
前端 Case Memory Diff 增加可选 baseline/candidate filename 输入框，可从同一个 demo pack vault 中选择 nested `evidence.json` 做比较。

### Commands
- Static frontend script parse/source probe: passed.
- Browser smoke on `127.0.0.1:8026`: passed; generated Demo Pack, selected one vault id for baseline/candidate, filled `offline-demo-gallery/cantilever/evidence.json` and `offline-demo-gallery/plate_hole/evidence.json`, clicked `Diff`, observed `FAIL · 4 rows`, `Diff FAIL · 4`, and a new `case-memory-diff · FAIL` row.
- `git diff --check`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed; 327 passed, 1 warning.

### Files Changed
- `frontend/index.html`
- `README.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
- Existing vault-id-only payload behavior preserved.
- New optional filename payload behavior verified through real frontend interaction.
- The remaining warning is the known external Starlette TestClient/httpx fallback warning.

### Scope Check
Frontend exposure and checkpoint docs only. No backend API changes, no broad picker redesign, no real Abaqus/ODB, no Docker, no release, no GitHub operation.

### Review Decision
Review pending.

### Merged
No.

## 2026-06-05 - V0.2-OFFLINE-DEMO-GALLERY-HTML-INDEX-001

### Goal
Add a top-level browser-readable `index.html` to Offline Demo Gallery and expose it through CLI output, ZIP packaging, Direct API, MCP bridge, and local vault artifact URLs.

### Completed
- `evidence/demo_gallery.py` now renders `index.html`, records `index_html_path`, and includes `index.html` in `offline-demo-gallery.zip`.
- Direct API `/api/evidence/demo-gallery` now returns `artifact_urls.index_html`, `index_html`, `index_html_url`, and vault `index.html`.
- MCP bridge `/mcp/api/evidence/demo-gallery` exposes the same HTML artifact/vault surface.
- README, CURRENT_STATE, CAPABILITY_AUDIT, and GOAL_PROGRESS were updated with the new product-visible evidence.

### Evidence
- Focused ruff passed for changed files.
- Focused pytest passed with 3 passed / 1 warning after correcting stale test node names.
- Actual CLI probe generated `/tmp/abaqus-agent-demo-gallery-index-html` and verified `index.html`, boundary text, case links, and ZIP membership.
- Actual HTTP probe on `127.0.0.1:8018` posted `/api/evidence/demo-gallery`, downloaded artifact/vault `index.html` as `text/html`, and verified ZIP members.
- Full `git diff --check`, full `ruff check .`, and full pytest passed with 320 passed / 1 warning.

### Boundary
No real Abaqus execution, ODB read, Docker/release/GitHub operation, local demo pack architecture rewrite, or new template engine.

### Chain Status
Internal ticket closed only as a checkpoint. Goal Chain continuation remains open; continue with the next high-value repo-local product ticket while budget and stop conditions allow.

## 2026-06-05 - V0.2-FRONTEND-DEMO-GALLERY-HTML-LINK-001

### Goal
Expose the new Offline Demo Gallery `index.html` from the frontend Evidence workspace Demo Gallery result.

### Completed
- `frontend/index.html` now renders an `HTML` link from `artifact_urls.index_html` with `index_html_url` fallback in `renderDemoGalleryResult`.
- Existing INDEX JSON, INDEX MD, and GALLERY ZIP links remain.
- CURRENT_STATE, CAPABILITY_AUDIT, and GOAL_PROGRESS were updated with the user-visible behavior.

### Evidence
- Static source probe confirmed Demo Gallery JSON/MD/HTML/ZIP link hooks.
- Static HTML script parse passed.
- Browser smoke on `127.0.0.1:8019` clicked Evidence -> `生成 Demo Gallery`, observed `PASS · 4 cases`, result `HTML` link to `/api/evidence/demo-gallery/<id>/index.html`, and vault/Case Memory `index.html` links.
- Full `git diff --check`, full `ruff check .`, and full pytest passed with 320 passed / 1 warning.

### Boundary
Frontend rendering only. No backend API change, generation change, real Abaqus/ODB execution, Docker/release/GitHub operation, or broad frontend redesign.

### Chain Status
Internal ticket closed only as a checkpoint. Goal Chain continuation remains open while useful repo-local product work remains.

## 2026-06-05 - V0.2-CASE-MEMORY-DIFF-NESTED-FILES-001

### Goal
Allow Case Memory diff callers to compare specific nested vault KPI artifacts.

### Completed
- `evidence/case_memory_diff.py` can load explicit safe nested `evidence.json` or `diff.json` filenames.
- Direct API and MCP bridge request models accept `baseline_filename` and `candidate_filename`.
- MCP stdio `diff_case_memory_tool` accepts the same optional filenames.
- Source metadata records the nested filename used.
- Existing vault-id-only behavior remains.
- CURRENT_STATE, CAPABILITY_AUDIT, and GOAL_PROGRESS were updated.

### Evidence
- Focused ruff passed.
- Focused pytest passed with 4 passed / 1 warning.
- Actual HTTP probe on `127.0.0.1:8024` generated a demo pack, compared nested cantilever vs plate-hole evidence from the same vault, returned FAIL / 4 rows, recorded both nested filenames, and returned 400 for unsafe `../evidence.json`.
- Full `git diff --check`, full `ruff check .`, and full pytest passed with 327 passed / 1 warning.

### Boundary
Local vault file selection only. No frontend picker redesign, embeddings/vector search, auth/storage redesign, real Abaqus/ODB execution, Docker/release/GitHub operation, or publishing.

### Chain Status
Internal ticket closed only as a checkpoint. Goal Chain continuation remains open while useful repo-local product work remains.

## 2026-06-05 - V0.2-FRONTEND-VAULT-NESTED-DEMO-PACK-LINKS-001

### Goal
Expose nested demo pack vault artifacts in Evidence Vault and Case Memory list rows.

### Completed
- `frontend/index.html` Evidence Vault and Case Memory rows now render `GALLERY`, `DOCTOR`, and `DIFF` quick links when nested demo pack vault URLs exist.
- Existing HTML/MD/ZIP/JSON links remain.
- Evidence Vault ZIP fallback now includes `local-demo-pack.zip`.
- CURRENT_STATE, CAPABILITY_AUDIT, and GOAL_PROGRESS were updated.

### Evidence
- Static frontend script parse passed.
- Static source probe confirmed nested list link hooks and local demo pack ZIP fallback.
- Browser smoke on `127.0.0.1:8023` generated a Demo Pack and confirmed nested links in the immediate result, Evidence Vault row, and Case Memory row.
- Full `git diff --check`, full `ruff check .`, and full pytest passed with 327 passed / 1 warning.

### Boundary
Frontend list rendering only. No backend API change, vault storage change, demo pack generation change, real Abaqus/ODB execution, Docker/release/GitHub operation, or broad frontend redesign.

### Chain Status
Internal ticket closed only as a checkpoint. Goal Chain continuation remains open while useful repo-local product work remains.

## 2026-06-05 - V0.2-FRONTEND-DEMO-PACK-NESTED-LINKS-001

### Goal
Expose nested demo pack vault artifacts directly in the frontend Evidence workspace.

### Completed
- `frontend/index.html` Demo Pack result now renders `GALLERY HTML`, `DOCTOR MD`, and `DIFF MD` links from nested `vault_urls`.
- Existing INDEX JSON, INDEX MD, pack HTML, and DEMO ZIP links remain.
- CURRENT_STATE, CAPABILITY_AUDIT, and GOAL_PROGRESS were updated.

### Evidence
- Static frontend script parse passed.
- Static source probe confirmed new nested link hooks.
- Browser smoke on `127.0.0.1:8022` clicked Evidence -> `生成 Demo Pack`, observed `PASS · demo pack`, and confirmed `GALLERY HTML`, `DOCTOR MD`, `DIFF MD`, and `DEMO ZIP` links point to vault URLs.
- Full `git diff --check`, full `ruff check .`, and full pytest passed with 327 passed / 1 warning.

### Boundary
Frontend rendering only. No backend API change, vault storage change, demo pack generation change, real Abaqus/ODB execution, Docker/release/GitHub operation, or broad frontend redesign.

### Chain Status
Internal ticket closed only as a checkpoint. Goal Chain continuation remains open while useful repo-local product work remains.

## 2026-06-05 - V0.2-VAULT-NESTED-DEMO-PACK-HTML-LINKS-001

### Goal
Make browser-served local demo pack HTML links work from evidence vault URLs while preserving path safety.

### Completed
- `evidence/vault.py` now accepts safe POSIX nested relative filenames and rejects absolute paths, `..`, backslashes, empty names, and unsupported filename characters.
- Direct API and MCP bridge vault routes now capture `{filename:path}` and convert unsafe filename errors to HTTP 400.
- `scripts/run_local_demo_pack.py` exposes `collect_demo_pack_vault_files()`.
- Direct API/MCP bridge demo-pack vault registration now includes nested gallery index/case files, Solver Doctor files, Simulation Diff files, and top-level pack files.
- README, CURRENT_STATE, CAPABILITY_AUDIT, and GOAL_PROGRESS were updated.

### Evidence
- Focused ruff passed.
- Focused pytest passed with 9 passed / 1 warning.
- Actual HTTP probe on `127.0.0.1:8020` generated a demo pack, downloaded nested gallery HTML, plate-hole evidence HTML, Solver Doctor Markdown, and Simulation Diff Markdown from vault URLs, and verified unsafe traversal returns 400.
- Full `git diff --check`, full `ruff check .`, and full pytest passed with 327 passed / 1 warning.

### Boundary
Safe local vault paths and demo pack registration only. No auth/permission model, cloud storage, delete/mutation API, real Abaqus/ODB execution, Docker/release/GitHub operation, or publishing.

### Chain Status
Internal ticket closed only as a checkpoint. Goal Chain continuation remains open while useful repo-local product work remains.

## 2026-06-05 - V0.2-OFFLINE-DEMO-GALLERY-ZIP-LINK-TARGETS-001

### Goal
Make `offline-demo-gallery.zip` navigable after extraction by ensuring `index.html` case links have matching ZIP members.

### Completed
- `evidence/demo_gallery.py` now writes root-level `<case>/...` evidence/capsule/bundle files into `offline-demo-gallery.zip`.
- Existing `cases/<case>/...` ZIP members remain for compatibility.
- README, CURRENT_STATE, CAPABILITY_AUDIT, and GOAL_PROGRESS were updated.

### Evidence
- Focused ruff passed.
- Focused pytest passed with 3 passed / 1 warning.
- Actual CLI probe generated `/tmp/abaqus-agent-gallery-zip-links`, extracted `offline-demo-gallery.zip`, and verified `index.html`, 4 direct case HTML files, 4 compatibility case HTML files, direct/compat plate-hole targets, direct index link text, and readable plate-hole HTML title.
- Full `git diff --check`, full `ruff check .`, and full pytest passed with 320 passed / 1 warning.

### Boundary
Gallery ZIP layout compatibility only. No report template redesign, backend route shape change, broad demo pack rewrite, real Abaqus/ODB execution, Docker/release/GitHub operation, or publishing.

### Chain Status
Internal ticket closed only as a checkpoint. Goal Chain continuation remains open while useful repo-local product work remains.

## 2026-06-05 - V0.2-LOCAL-DEMO-PACK-DIRECT-GALLERY-CASE-FILES-001

### Goal
Make the Offline Demo Gallery inside `local-demo-pack.zip` fully navigable after extraction by including direct per-case files.

### Completed
- `scripts/run_local_demo_pack.py` now carries gallery `cases` entries in the pack index.
- `local-demo-pack.zip` includes direct per-case `evidence.json`, `evidence.md`, `evidence.html`, `capsule.json`, and `<case>-demo-bundle.zip` under `offline-demo-gallery/<case>/` for all four gallery cases.
- README, CURRENT_STATE, CAPABILITY_AUDIT, and GOAL_PROGRESS were updated.

### Evidence
- Focused ruff passed for changed files.
- Focused pytest passed with 5 passed / 1 warning.
- Actual CLI probe generated `/tmp/abaqus-agent-local-demo-pack-direct-cases`, extracted the pack ZIP, and verified 4 case HTML files, 4 case bundles, `offline-demo-gallery/index.html`, `offline-demo-gallery/plate_hole/evidence.html`, readable case HTML title, and nested gallery ZIP.
- Full `git diff --check`, full `ruff check .`, and full pytest passed with 320 passed / 1 warning.

### Boundary
Packaging only. No backend route shape change, broad demo pack rewrite, real Abaqus/ODB execution, Docker/release/GitHub operation, or publishing.

### Chain Status
Internal ticket closed only as a checkpoint. Goal Chain continuation remains open while useful repo-local product work remains.

## 2026-06-05 - V0.2-LOCAL-DEMO-PACK-GALLERY-HTML-INCLUSION-001

### Goal
Make the local demo pack ZIP self-contained for opening the Offline Demo Gallery overview directly.

### Completed
- `scripts/run_local_demo_pack.py` records gallery `html_path` in the pack index.
- Pack `index.html` now links to `offline-demo-gallery/index.html`.
- `local-demo-pack.zip` now includes `offline-demo-gallery/index.json`, `offline-demo-gallery/index.md`, `offline-demo-gallery/index.html`, and the existing nested `offline-demo-gallery/offline-demo-gallery.zip`.
- README, CURRENT_STATE, CAPABILITY_AUDIT, and GOAL_PROGRESS were updated.

### Evidence
- Focused ruff passed for changed files.
- Focused pytest passed with 5 passed / 1 warning after correcting a stale MCP server test node name.
- Actual CLI probe generated `/tmp/abaqus-agent-local-demo-pack-gallery-html`, verified PASS, pack HTML gallery link, direct gallery index JSON/MD/HTML members, nested gallery ZIP, and readable gallery HTML title/boundary inside the pack ZIP.
- Full `git diff --check`, full `ruff check .`, and full pytest passed with 320 passed / 1 warning.

### Boundary
Packaging/linking only. No backend API shape change, broad demo pack rewrite, real Abaqus/ODB execution, Docker/release/GitHub operation, or publishing.

### Chain Status
Internal ticket closed only as a checkpoint. Goal Chain continuation remains open while useful repo-local product work remains.

---

## Ticket ID
V0.2-DEMO-GALLERY-HTML-CASE-REPORTS-001

### Date
2026-06-05

### Status
Done

### Summary
Carried per-case `evidence.html` reports through Offline Demo Gallery outputs.
Each case index record now has `html_path`; per-case demo bundles include
`evidence.html`; and top-level `offline-demo-gallery.zip` includes
`cases/<case>/evidence.html`.

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check evidence/demo_gallery.py tests/test_offline_evidence_slice.py tests/test_server_api_smoke.py tests/test_mcp_bridge_real_subprocess.py`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_offline_evidence_slice.py tests/test_server_api_smoke.py tests/test_mcp_bridge_real_subprocess.py -q`: passed, 12 passed / 1 warning.
- Actual CLI probe with `/tmp/abaqus-agent-audit-venv/bin/python scripts/run_offline_demo_gallery.py --out-dir /tmp/abaqus-agent-demo-gallery-html --json`: passed, `PASS` / 4 cases; verified `plate_hole` `html_path` exists, per-case bundle contains readable `evidence.html`, and top-level gallery ZIP contains `cases/plate_hole/evidence.html`.
- `git diff --check`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed, 320 passed / 1 warning.

### Files Changed
- `evidence/demo_gallery.py`
- `tests/test_offline_evidence_slice.py`
- `tests/test_server_api_smoke.py`
- `tests/test_mcp_bridge_real_subprocess.py`
- `README.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Scope Check
No new report template engine, demo pack architecture rewrite, real Abaqus
execution, ODB read, Docker, release, GitHub operation, PyPI, commit, push, or
merge was performed.

### Review Decision
Continue Goal Chain with the next product-visible repo-local ticket if one is
available after full verification.

### Merged
No.

---

## Ticket ID
V0.2-EVIDENCE-HTML-LIST-LINKS-001

### Date
2026-06-05

### Status
Done

### Summary
Surfaced generated HTML reports from frontend evidence lists. Recent Evidence
now shows `artifact_urls.report_html`, and Evidence Vault / Case Memory rows use
`vault_urls['evidence.html']` with `index.html` fallback.

### Commands
- Static `node` parse of `frontend/index.html`: passed.
- Static source probe for Recent/Vault/Case Memory HTML link hooks: passed.
- `git diff --check frontend/index.html docs/goal_driver/GOAL_PROGRESS.md`:
  passed.
- `git diff --check`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed, 320 passed / 1 warning.

### Files Changed
- `frontend/index.html`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Scope Check
No backend API change, report generation change, storage/auth redesign, real
Abaqus execution, ODB read, Docker, release, GitHub operation, PyPI, commit,
push, or merge was performed.

### Review Decision
Continue Goal Chain with the next product-visible repo-local ticket if one is
available after full verification.

### Merged
No.

---

## Ticket ID
V0.2-OFFLINE-EVIDENCE-HTML-REPORT-001

### Date
2026-06-05

### Status
Done

### Summary
Added a self-contained `evidence.html` report for single-run Offline Evidence.
Direct API and MCP bridge artifact responses now expose a browser-readable HTML
URL, vault entries persist the HTML report, ZIP bundles include it, capsules
record it as an artifact, and the frontend Evidence result shows an `HTML`
artifact link.

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check evidence/offline.py server.py mcp_bridge.py mcp_server.py tests/test_offline_evidence_slice.py tests/test_server_api_smoke.py tests/test_mcp_bridge_real_subprocess.py`: passed after import-order fix.
- Static frontend JS parse plus source probe for `report_html`, `evidence.html`,
  and frontend `HTML` link hooks: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_offline_evidence_slice.py tests/test_server_api_smoke.py tests/test_mcp_bridge_real_subprocess.py -q`: first run failed because old tests expected only JSON/MD capsule artifacts and the API/MCP return shape lacked `html_path`; after fixes, passed with 12 passed / 1 warning.
- Actual HTTP probe on `127.0.0.1:8017`: posted `/api/evidence/offline`,
  downloaded `evidence.html` as `text/html`, verified the no-real-Abaqus
  boundary text, confirmed `bundle.zip` contains `evidence.html`, and downloaded
  vault `evidence.html`.
- `git diff --check`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed, 320 passed / 1 warning.

### Files Changed
- `evidence/offline.py`
- `server.py`
- `mcp_bridge.py`
- `mcp_server.py`
- `frontend/index.html`
- `tests/test_offline_evidence_slice.py`
- `tests/test_server_api_smoke.py`
- `tests/test_mcp_bridge_real_subprocess.py`
- `README.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Scope Check
No real Abaqus execution, ODB extraction, PDF/DOCX export, report-template
engine redesign, auth/storage redesign, Docker, release, GitHub operation, PyPI,
commit, push, or merge was performed.

### Review Decision
Continue Goal Chain with the next product-visible repo-local ticket if one is
available after full verification.

### Merged
No.

---

## Ticket ID
V0.2-FRONTEND-SAME-ORIGIN-API-BASE-001

### Date
2026-06-05

### Status
Done

### Summary
Changed the frontend Direct API default to follow the current served origin
instead of hard-coding local port 8000. This keeps local browser workflows
working when the FastAPI server is started on an alternate port, while preserving
saved `serverUrl` overrides and the existing explicit MCP bridge default.

### Commands
- Static `node` parse of `frontend/index.html`: passed.
- Static source probe for `_pageOrigin`, `window.location.origin`,
  `_defaultAPI = _pageOrigin`, `cfg.serverUrl || _defaultAPI`, and preserved
  `_defaultMCPAPI`: passed.
- `git diff --check frontend/index.html docs/goal_driver/GOAL_PROGRESS.md`:
  passed.
- Browser smoke on `127.0.0.1:8016` with
  `ABAQUS_AGENT_EVIDENCE_VAULT=/tmp/abaqus-agent-same-origin-vault`: cleared
  the saved Direct API override through Settings, reloaded the page, opened
  Evidence, and confirmed same-origin 200 responses on the 8016 server for
  `/health`, `/api/evidence/examples`, `/api/evidence/artifacts`,
  `/api/evidence/vault`, `/api/case-memory?limit=8`, `/api/kpi-recipes`,
  `/api/doctor/patterns`, and `/api/benchmark`.
- `git diff --check`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed, 320 passed / 1 warning.

### Files Changed
- `frontend/index.html`
- `README.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Scope Check
No backend API change, MCP bridge default redesign, auth/localStorage migration,
real Abaqus execution, ODB read, Docker, release, GitHub operation, PyPI,
commit, push, or merge was performed.

### Review Decision
Continue Goal Chain with the next product-visible repo-local ticket if one is
available after full verification.

### Merged
No.

---

## Ticket ID
V0.2-CASE-MEMORY-DIFF-FRONTEND-001

### Date
2026-06-05

### Status
Done

### Summary
Connected Case Memory vault-to-vault diff to the frontend Evidence workspace.
Users can search memory entries, pick baseline/candidate vault ids from rows,
run a diff, and inspect the resulting Simulation Diff verdict/report/artifact
links without re-uploading KPI JSON.

### Commands
- `node` static script parse of `frontend/index.html`: passed.
- Static source probe for `case-memory-diff-*`, `/api/case-memory/diff`,
  `runCaseMemoryDiff`, `data-case-memory-role`, and error feedback hooks:
  passed.
- `git diff --check frontend/index.html docs/goal_driver/GOAL_PROGRESS.md`:
  passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_server_api_smoke.py tests/test_mcp_bridge_real_subprocess.py tests/test_mcp_server.py tests/test_mcp_stdio_client.py -q`: passed, 42 passed / 1 warning.
- `git diff --check`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed, 320 passed / 1 warning.
- Browser smoke on `127.0.0.1:8000` with
  `ABAQUS_AGENT_EVIDENCE_VAULT=/tmp/abaqus-agent-frontend-case-memory-vault`:
  listed two Case Memory entries, selected baseline/candidate ids with row
  buttons, posted `/api/case-memory/diff`, rendered `FAIL · 2 rows`, displayed
  the Markdown report, and refreshed Case Memory to include the new
  `case-memory-diff` vault record.

### Files Changed
- `frontend/index.html`
- `README.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Scope Check
No backend behavior change, real Abaqus execution, ODB read, Docker,
vector database, cloud sync, auth, deletion, GitHub release, PyPI, commit, push,
or merge was performed. The frontend calls the existing local KPI-artifact diff
endpoint only.

### Review Decision
Continue Goal Chain with the next product-visible repo-local ticket if one is
available after full verification.

### Merged
No.

---

## Ticket ID
V0.2-CASE-MEMORY-DIFF-001

### Date
2026-06-05

### Status
Done

### Summary
Added Case Memory vault-to-vault KPI diff. Users can compare two saved
`evidence.json` or `diff.json` vault artifacts without re-uploading KPI JSON.
The workflow writes a new Simulation Diff `diff.json`/`diff.md`, records source
vault ids in the report, and persists a `case-memory-diff` vault entry.

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check evidence/case_memory_diff.py server.py mcp_bridge.py mcp_server.py tests/test_server_api_smoke.py tests/test_mcp_bridge_real_subprocess.py tests/test_mcp_server.py tests/test_mcp_stdio_client.py`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_server_api_smoke.py tests/test_mcp_bridge_real_subprocess.py tests/test_mcp_server.py tests/test_mcp_stdio_client.py -q`: first run failed once because MCP stdio Case Memory resource now had 3 seeded entries instead of 1; after fixing the assertion, passed with 42 passed / 1 warning.
- Actual HTTP probe on `127.0.0.1:8015`: generated two offline evidence vault entries, posted `/api/case-memory/diff`, got `FAIL` with one changed KPI, and downloaded `diff.md` containing both source vault ids.
- `git diff --check`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed; 320 passed, 1 warning.

### Files Changed
- `evidence/case_memory_diff.py`
- `server.py`
- `mcp_bridge.py`
- `mcp_server.py`
- `tests/test_server_api_smoke.py`
- `tests/test_mcp_bridge_real_subprocess.py`
- `tests/test_mcp_server.py`
- `tests/test_mcp_stdio_client.py`
- `README.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Scope Check
No real Abaqus, ODB extraction, Docker, vector database, cloud sync, auth,
destructive vault mutation, GitHub release, PyPI, commit, push, or merge was
performed. The diff compares saved KPI JSON artifacts only.

### Review Decision
Continue Goal Chain with the next product-visible repo-local ticket if one is
available from the current strategy.

### Merged
No.

---

## Ticket ID
V0.2-CUSTOM-INP-EVIDENCE-SURFACE-001

### Date
2026-06-05

### Status
Done

### Summary
Added a first-class offline evidence example for an existing `.inp` deck. The
new `custom_inp_deck` fixture points at `examples/inp/custom_cantilever.inp`,
uses supplied KPI/contract fixtures, appears in Direct API/MCP bridge/MCP stdio
example discovery, and is available in the frontend Evidence selector fallback.
Demo Gallery remains four public spec cases.

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_offline_evidence_slice.py tests/test_server_api_smoke.py tests/test_mcp_bridge_real_subprocess.py tests/test_mcp_server.py tests/test_mcp_stdio_client.py -q`: initially failed twice during test/fixture wiring, then passed with 46 passed / 1 warning.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check evidence/examples.py evidence/demo_gallery.py tests/test_offline_evidence_slice.py tests/test_server_api_smoke.py tests/test_mcp_bridge_real_subprocess.py tests/test_mcp_server.py tests/test_mcp_stdio_client.py`: passed.
- Static frontend/source probe for `custom_inp_deck` and `examples/inp/custom_cantilever.inp`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python scripts/run_offline_evidence_slice.py --baseline-kpis examples/kpis/custom_inp_deck_baseline.json --candidate-kpis examples/kpis/custom_inp_deck_candidate.json --contracts examples/contracts/custom_inp_deck.yaml --input examples/inp/custom_cantilever.inp --out-dir /tmp/abaqus-agent-custom-inp-evidence --run-id custom-inp-deck-cli --json`: passed; generated PASS evidence and capsule input `custom_cantilever.inp`.
- Actual HTTP probe on `127.0.0.1:8014`: `/api/evidence/examples/custom_inp_deck` returned the `.inp` payload; `/api/evidence/offline` returned PASS/PASS/PASS and capsule artifact contained `custom_cantilever.inp` plus `input_metadata.json`.
- `git diff --check`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed; 319 passed, 1 warning.

### Files Changed
- `examples/inp/custom_cantilever.inp`
- `examples/kpis/custom_inp_deck_baseline.json`
- `examples/kpis/custom_inp_deck_candidate.json`
- `examples/contracts/custom_inp_deck.yaml`
- `evidence/examples.py`
- `evidence/demo_gallery.py`
- `frontend/index.html`
- `tests/test_offline_evidence_slice.py`
- `tests/test_server_api_smoke.py`
- `tests/test_mcp_bridge_real_subprocess.py`
- `tests/test_mcp_server.py`
- `tests/test_mcp_stdio_client.py`
- `README.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`
- `docs/goal_driver/NEXT_TICKETS.md`

### Scope Check
No real Abaqus, syntaxcheck, submit, ODB extraction, Docker, GitHub release,
PyPI, commit, push, or merge was performed. The `.inp` deck is copied into the
offline capsule/report flow only.

### Review Decision
Ready Local queue is now empty; continue only with a newly justified
product-visible local ticket or stop/consult for direction.

### Merged
No.

---

## Ticket ID
V0.2-SIMDIFF-REPORT-PACK-001

### Date
2026-06-05

### Status
Done

### Summary
Added standalone Simulation Diff evidence to the local demo pack. The demo pack
now writes `simulation-diff/diff.json` and `simulation-diff/diff.md`, exposes a
`simulation_diff` section in `index.json`, renders the sample in Markdown/HTML,
and includes the diff artifacts in `local-demo-pack.zip`. Direct API, MCP
bridge, and MCP stdio demo pack paths return the new section.

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_offline_evidence_slice.py tests/test_server_api_smoke.py tests/test_mcp_bridge_real_subprocess.py tests/test_mcp_server.py tests/test_mcp_stdio_client.py -q`: first run failed once due stale MCP server ZIP member assertion, then passed with 45 passed / 1 warning after updating the assertion.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check scripts/run_local_demo_pack.py server.py mcp_bridge.py tests/test_offline_evidence_slice.py tests/test_server_api_smoke.py tests/test_mcp_bridge_real_subprocess.py tests/test_mcp_server.py tests/test_mcp_stdio_client.py`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python scripts/run_local_demo_pack.py --out-dir /tmp/abaqus-agent-local-demo-pack-simdiff --json`: passed; generated pack `PASS`, Simulation Diff sample `FAIL`, 1 changed KPI, 1 added KPI.
- ZIP inspection of `/tmp/abaqus-agent-local-demo-pack-simdiff/local-demo-pack.zip`: passed; included `simulation-diff/diff.json` and `simulation-diff/diff.md`, with workflow `simulation-diff-kpi`.
- Actual HTTP probe on `127.0.0.1:8013` via `POST /api/evidence/demo-pack`: passed; downloaded `index.html` and `local-demo-pack.zip` through vault URLs and verified Simulation Diff content.
- `git diff --check`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed; 318 passed, 1 warning.

### Files Changed
- `scripts/run_local_demo_pack.py`
- `server.py`
- `mcp_bridge.py`
- `tests/test_offline_evidence_slice.py`
- `tests/test_server_api_smoke.py`
- `tests/test_mcp_bridge_real_subprocess.py`
- `tests/test_mcp_server.py`
- `tests/test_mcp_stdio_client.py`
- `README.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`
- `docs/goal_driver/NEXT_TICKETS.md`

### Scope Check
No real Abaqus, Docker, GitHub release, PyPI, commit, push, or merge was
performed. The Simulation Diff sample compares supplied KPI JSON only and does
not read ODB files or prove solver execution.

### Review Decision
Continue Goal Chain if time remains and a meaningful local product ticket is
available.

### Merged
No.

---

## Ticket ID
V0.2-SIMULATION-DIFF-API-FRONTEND-001

### Date
2026-06-05

### Status
Done

### Summary
Exposed standalone Simulation Diff over supplied KPI dictionaries through
Direct API, MCP bridge, MCP stdio, frontend Evidence, local evidence vault, and
Case Memory. The workflow writes portable `diff.json` and `diff.md` reports and
keeps the no-real-Abaqus/ODB verification boundary explicit.

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_simulation_diff.py tests/test_server_api_smoke.py tests/test_mcp_bridge_real_subprocess.py tests/test_mcp_server.py tests/test_mcp_stdio_client.py -q`: passed, 45 passed / 1 warning.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check simdiff server.py mcp_bridge.py mcp_server.py tests/test_simulation_diff.py tests/test_server_api_smoke.py tests/test_mcp_bridge_real_subprocess.py tests/test_mcp_server.py tests/test_mcp_stdio_client.py`: passed.
- Static frontend source probe confirmed `Simulation Diff`, `btn-simdiff-run`, `/api/simdiff/kpis`, `simdiff-tolerances`, `renderSimulationDiffResult`, `diff.md`, and `diff.json`.
- Actual HTTP probe against `uvicorn server:app --host 127.0.0.1 --port 8011`: `POST /api/simdiff/kpis` returned `FAIL`, downloaded vault `diff.md` and `diff.json`, and found a `simulation-diff` Case Memory entry.
- `git diff --check`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed, 315 passed / 1 warning.

### Files Changed
- `simdiff/service.py`
- `simdiff/__init__.py`
- `server.py`
- `mcp_bridge.py`
- `mcp_server.py`
- `frontend/index.html`
- `tests/test_simulation_diff.py`
- `tests/test_server_api_smoke.py`
- `tests/test_mcp_bridge_real_subprocess.py`
- `tests/test_mcp_server.py`
- `tests/test_mcp_stdio_client.py`
- `README.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`
- `docs/goal_driver/NEXT_TICKETS.md`

### Tests
No real Abaqus executable/license/ODB was invoked. The new Simulation Diff
surface compares supplied KPI JSON values only; it does not read real ODB files,
run a solver, or prove physical correctness of the KPI source data. The
remaining warning is the previously audited external Starlette TestClient/httpx
fallback warning.

### Scope Check
No real Abaqus/ODB verification claims, extraction semantic changes, broad
frontend redesign, Docker, PyPI/GitHub Release, pull/merge/commit/push,
cloud/vector/database storage, or real Abaqus validation was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
V0.2-KPI-RECIPE-GALLERY-001

### Date
2026-06-05

### Status
Done

### Summary
Exposed the existing ODB Lens/KPI extraction capabilities as a discoverable KPI
Recipe Gallery. Built-in recipes now cover every currently implemented
extractor type and are available through Direct API, MCP bridge, MCP stdio, and
the frontend Evidence workspace.

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_server_api_smoke.py tests/test_mcp_bridge_real_subprocess.py tests/test_mcp_server.py tests/test_mcp_stdio_client.py tests/test_extract_kpis_inner_fake_odb.py -q`: passed, 51 passed / 1 warning.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check post evidence server.py mcp_bridge.py mcp_server.py tests/test_server_api_smoke.py tests/test_mcp_bridge_real_subprocess.py tests/test_mcp_server.py tests/test_mcp_stdio_client.py tests/test_extract_kpis_inner_fake_odb.py`: passed.
- Static frontend source probe confirmed `KPI Recipes`, `kpi-recipe-count`, `/api/kpi-recipes`, `renderKpiRecipes`, and `btn-kpi-recipes-refresh`.
- Actual HTTP probe against `uvicorn server:app --host 127.0.0.1 --port 8010`: `/api/kpi-recipes` returned 6 recipes and all supported KPI types; `case=plate_hole` filtering returned plate-hole recipes; `/api/kpi-recipes/modal-first-three-frequencies` returned eigenfrequency KPI specs.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `git diff --check`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed, 311 passed / 1 warning.

### Files Changed
- `post/kpi_recipes.py`
- `server.py`
- `mcp_bridge.py`
- `mcp_server.py`
- `frontend/index.html`
- `tests/test_server_api_smoke.py`
- `tests/test_mcp_bridge_real_subprocess.py`
- `tests/test_mcp_server.py`
- `tests/test_mcp_stdio_client.py`
- `tests/test_extract_kpis_inner_fake_odb.py`
- `README.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`
- `docs/goal_driver/NEXT_TICKETS.md`

### Tests
No real Abaqus executable/license/ODB was invoked. Recipes are source-supported
and fake-ODB aligned only; this ticket did not change extraction semantics or
prove real `odbAccess` runtime behavior.

### Scope Check
No real Abaqus/ODB verification claims, extractor semantic changes, new Abaqus
runtime dependency, broad frontend redesign, Docker, PyPI/GitHub Release,
pull/merge/commit/push, or real Abaqus validation was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
V0.2-CASE-MEMORY-VAULT-SEARCH-001

### Date
2026-06-05

### Status
Done

### Summary
Added the first local Case Memory surface over the evidence vault. Generated
evidence/demo/doctor vault records can now be searched by query, kind, and
status through Direct API, MCP bridge, MCP stdio, and the frontend Evidence
workspace.

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_server_api_smoke.py tests/test_mcp_bridge_real_subprocess.py tests/test_mcp_server.py tests/test_mcp_stdio_client.py -q`: passed, 34 passed / 1 warning.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check evidence server.py mcp_bridge.py mcp_server.py tests/test_server_api_smoke.py tests/test_mcp_bridge_real_subprocess.py tests/test_mcp_server.py tests/test_mcp_stdio_client.py`: initially failed on import grouping in `tests/test_mcp_stdio_client.py`; after patch, passed.
- Static frontend source probe confirmed `Case Memory`, `case-memory-query`, `/api/case-memory`, `renderCaseMemory`, and `btn-case-memory-search`.
- Actual HTTP probe against `uvicorn server:app --host 127.0.0.1 --port 8009` with `ABAQUS_AGENT_EVIDENCE_VAULT=/tmp/abaqus-agent-case-memory-vault`: generated a Demo Pack and Solver Doctor report, then `GET /api/case-memory` found `solver-doctor` and `local-demo-pack` memory entries with expected files/links.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `git diff --check`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed, 308 passed / 1 warning.

### Files Changed
- `evidence/case_memory.py`
- `server.py`
- `mcp_bridge.py`
- `mcp_server.py`
- `frontend/index.html`
- `tests/test_server_api_smoke.py`
- `tests/test_mcp_bridge_real_subprocess.py`
- `tests/test_mcp_server.py`
- `tests/test_mcp_stdio_client.py`
- `README.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`
- `docs/goal_driver/NEXT_TICKETS.md`

### Tests
No real Abaqus executable/license/syntaxcheck/solver/ODB was invoked. Case
Memory indexes local vault metadata for generated offline/sample artifacts only;
it is not semantic/vector search, cloud sync, team permissions, deletion, or
real Abaqus evidence.

### Scope Check
No cloud/database/auth system, vector database, embedding dependency, broad
frontend redesign, Docker, PyPI/GitHub Release, pull/merge/commit/push,
mutation/deletion of vault entries, or real Abaqus validation was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
V0.2-LOCAL-DEMO-PACK-HTML-REPORT-001

### Date
2026-06-05

### Status
Done

### Summary
Added a self-contained `index.html` overview to the local demo pack. The HTML
report is generated by the CLI/service, included in `local-demo-pack.zip`,
returned by Direct API, MCP bridge, and MCP stdio surfaces, exposed through a
frontend `HTML` link, and downloadable from the local evidence vault.

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_offline_evidence_slice.py tests/test_server_api_smoke.py tests/test_mcp_bridge_real_subprocess.py tests/test_mcp_server.py tests/test_mcp_stdio_client.py -q`: passed, 36 passed / 1 warning.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check scripts/run_local_demo_pack.py server.py mcp_bridge.py mcp_server.py tests/test_offline_evidence_slice.py tests/test_server_api_smoke.py tests/test_mcp_bridge_real_subprocess.py tests/test_mcp_server.py tests/test_mcp_stdio_client.py`: passed.
- Static frontend source probe confirmed `index.html`, `index_html_url`, `HTML`, and `renderLocalDemoPackResult`.
- Actual CLI probe: `scripts/run_local_demo_pack.py --out-dir /tmp/abaqus-agent-demo-pack-html-probe --json` generated PASS output, `index.html`, and a ZIP containing `index.html`.
- Actual HTTP probe against `uvicorn server:app --host 127.0.0.1 --port 8008` with `ABAQUS_AGENT_EVIDENCE_VAULT=/tmp/abaqus-agent-demo-pack-html-vault`: `POST /api/evidence/demo-pack` returned `index_html_url`, `GET index.html` returned `text/html; charset=utf-8`, and ZIP members included `index.html`.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `git diff --check`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed, 306 passed / 1 warning.

### Files Changed
- `scripts/run_local_demo_pack.py`
- `server.py`
- `mcp_bridge.py`
- `mcp_server.py`
- `frontend/index.html`
- `tests/test_offline_evidence_slice.py`
- `tests/test_server_api_smoke.py`
- `tests/test_mcp_bridge_real_subprocess.py`
- `tests/test_mcp_server.py`
- `tests/test_mcp_stdio_client.py`
- `README.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`
- `docs/goal_driver/NEXT_TICKETS.md`

### Tests
No real Abaqus executable/license/syntaxcheck/solver/ODB was invoked. The HTML
report summarizes supplied KPI fixtures and sample Solver Doctor log text only.
The remaining warning is the previously audited external Starlette
TestClient/httpx fallback warning.

### Scope Check
No broad frontend redesign, external asset pipeline, PDF/browser automation
dependency, Docker, PyPI/GitHub Release, pull/merge/commit/push, auth system,
cloud storage, database migration, or real Abaqus validation was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
V0.2-DEMO-PACK-MCP-STDIO-001

### Date
2026-06-05

### Status
Done

### Summary
Exposed the local product demo pack through MCP stdio. IDE/agent clients can
now call `create_local_demo_pack_tool` to generate the same reviewable
`local-demo-pack.zip`, index JSON, and Markdown report without HTTP or browser
setup.

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_mcp_server.py tests/test_mcp_stdio_client.py -q`: passed, 26 passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check mcp_server.py tests/test_mcp_server.py tests/test_mcp_stdio_client.py`: passed.
- `git diff --check`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `git diff --check`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed, 306 passed / 1 warning.

### Files Changed
- `mcp_server.py`
- `tests/test_mcp_server.py`
- `tests/test_mcp_stdio_client.py`
- `README.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`
- `docs/goal_driver/NEXT_TICKETS.md`

### Tests
No real Abaqus executable/license/syntaxcheck/solver/ODB was invoked. The MCP
stdio demo pack uses supplied KPI fixtures and sample Solver Doctor log text
only. The remaining warning is the previously audited external Starlette
TestClient/httpx fallback warning.

### Scope Check
No Direct API/MCP bridge/frontend behavior change, Docker, PyPI/GitHub Release,
pull/merge/commit/push, auth system, cloud storage, database migration, vault
semantics change, or real Abaqus validation was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
V0.2-LOCAL-DEMO-PACK-API-FRONTEND-001

### Date
2026-06-05

### Status
Done

### Summary
Exposed the one-command local demo pack through Direct API, MCP bridge, the
frontend Evidence workspace, and local evidence vault downloads. Non-terminal
users can now generate the same reviewable `local-demo-pack.zip` product
artifact from browser/API paths.

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_server_api_smoke.py tests/test_mcp_bridge_real_subprocess.py -q`: passed, 6 passed / 1 warning.
- Corrected focused ruff after an initial command mistake that passed `frontend/index.html` to Python ruff; `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check server.py mcp_bridge.py tests/test_server_api_smoke.py tests/test_mcp_bridge_real_subprocess.py`: passed.
- Static frontend source probe confirmed `btn-evidence-demo-pack`, `/api/evidence/demo-pack`, `renderLocalDemoPackResult`, `local-demo-pack.zip`, and `生成 Demo Pack`.
- Actual HTTP probe against `uvicorn server:app --host 127.0.0.1 --port 8007` with `ABAQUS_AGENT_EVIDENCE_VAULT=/tmp/abaqus-agent-demo-pack-api-vault`: `POST /api/evidence/demo-pack` returned `overall_status=PASS`, 4 gallery cases, Solver Doctor `FAILED`, downloadable `local-demo-pack.zip` with expected files, and vault list kind `local-demo-pack`.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `git diff --check`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed, 305 passed / 1 warning.

### Files Changed
- `server.py`
- `mcp_bridge.py`
- `frontend/index.html`
- `tests/test_server_api_smoke.py`
- `tests/test_mcp_bridge_real_subprocess.py`
- `README.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
No real Abaqus executable/license/syntaxcheck/solver/ODB was invoked. The demo
pack combines supplied KPI fixtures and sample Solver Doctor log text only. The
remaining warning is the previously audited external Starlette TestClient/httpx
fallback warning.

### Scope Check
No Docker, PyPI/GitHub Release, pull/merge/commit/push, auth system, cloud
storage, database migration, evidence semantic change, broad frontend redesign,
or real Abaqus validation was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
V0.2-ONE-COMMAND-LOCAL-DEMO-PACK-001

### Date
2026-06-05

### Status
Done

### Summary
Added `scripts/run_local_demo_pack.py`, a one-command local product demo pack
that combines Offline Demo Gallery output and a Solver Doctor sample into a
single reviewable folder and `local-demo-pack.zip`.

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_offline_evidence_slice.py -q`: passed, 4 passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check scripts tests/test_offline_evidence_slice.py`: initially failed on import ordering; after patch, passed.
- `git diff --check`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python scripts/run_local_demo_pack.py --out-dir /tmp/abaqus-agent-local-demo-pack --json`: passed; follow-up probe confirmed `overall_status=PASS`, 4 gallery cases, Solver Doctor `FAILED` sample, pack ZIP exists, and expected ZIP members are present.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `git diff --check`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed, 305 passed / 1 warning.

### Files Changed
- `scripts/run_local_demo_pack.py`
- `tests/test_offline_evidence_slice.py`
- `README.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
No real Abaqus executable/license/syntaxcheck/solver/ODB was invoked. The demo
pack uses supplied KPI fixtures and sample Solver Doctor log text only. The
remaining warning is the previously audited external Starlette TestClient/httpx
fallback warning.

### Scope Check
No server process management, Docker, PyPI/GitHub Release, pull/merge/commit/
push, frontend/backend behavior change, evidence semantic change, or real
Abaqus validation was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
V0.2-EVIDENCE-VAULT-FRONTEND-001

### Date
2026-06-05

### Status
Done

### Summary
Surfaced the local evidence vault in the frontend Evidence workspace. Users can
refresh persisted vault entries and open MD/ZIP/JSON links for generated
offline evidence, demo gallery, and Solver Doctor deliverables.

### Commands
- Static frontend probe: confirmed `Evidence Vault`, refresh button, count, `/api/evidence/vault` call, and MD/ZIP/JSON link hooks are present in `frontend/index.html`.
- `git diff --check`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `git diff --check`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed, 304 passed / 1 warning.

### Files Changed
- `frontend/index.html`
- `README.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
No real Abaqus executable/license/syntaxcheck/solver/ODB was invoked. Frontend
vault rendering was source/static verified because in-app browser tooling was
unavailable during this Goal Chain segment. The remaining warning is the
previously audited external Starlette TestClient/httpx fallback warning.

### Scope Check
No backend behavior change, Docker, PyPI/GitHub Release, pull/merge/commit/push,
auth system, cloud storage, database migration, broad frontend redesign, or real
Abaqus validation was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
V0.2-LOCAL-EVIDENCE-VAULT-001

### Date
2026-06-05

### Status
Done

### Summary
Added a configurable local evidence vault. Offline evidence, demo gallery, and
Solver Doctor Direct API/MCP bridge paths now persist generated deliverables to
`ABAQUS_AGENT_EVIDENCE_VAULT` or `~/.abaqus-agent/evidence-vault`, return
`vault_id`/`vault_urls`, and expose list/download endpoints.

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_server_api_smoke.py tests/test_mcp_bridge_real_subprocess.py -q`: passed, 6 passed / 1 warning.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check evidence server.py mcp_bridge.py tests/test_server_api_smoke.py tests/test_mcp_bridge_real_subprocess.py`: passed.
- `git diff --check`: passed.
- Actual HTTP probe against `uvicorn server:app --host 127.0.0.1 --port 8006` with `ABAQUS_AGENT_EVIDENCE_VAULT=/tmp/abaqus-agent-http-vault`: `POST /api/doctor/diagnose` returned a `vault_id` and vault URLs; `GET doctor.md` from the vault returned `# Solver Doctor: Vault-Doctor`; `GET /api/evidence/vault` listed the `solver-doctor` entry.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `git diff --check`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed, 304 passed / 1 warning.

### Files Changed
- `evidence/vault.py`
- `server.py`
- `mcp_bridge.py`
- `tests/test_server_api_smoke.py`
- `tests/test_mcp_bridge_real_subprocess.py`
- `README.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
No real Abaqus executable/license/syntaxcheck/solver/ODB was invoked. The vault
persists local generated deliverables only; it is not cloud storage, a database,
or a multi-user permission model. The remaining warning is the previously
audited external Starlette TestClient/httpx fallback warning.

### Scope Check
No Docker, PyPI/GitHub Release, pull/merge/commit/push, auth system, database
migration, frontend redesign, evidence semantic change, or real Abaqus
validation was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
V0.2-SOLVER-DOCTOR-MCP-STDIO-001

### Date
2026-06-05

### Status
Done

### Summary
Exposed Solver Doctor log-text diagnosis to MCP stdio clients through
`diagnose_solver_logs_tool`, so agent/IDE integrations can get the same
deterministic JSON and Markdown report without using the HTTP API or frontend.

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_mcp_server.py tests/test_mcp_stdio_client.py -q`: passed, 25 passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check mcp_server.py tests/test_mcp_server.py tests/test_mcp_stdio_client.py`: passed.
- `git diff --check`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `git diff --check`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed, 304 passed / 1 warning.

### Files Changed
- `mcp_server.py`
- `tests/test_mcp_server.py`
- `tests/test_mcp_stdio_client.py`
- `README.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
No real Abaqus executable/license/syntaxcheck/solver/ODB was invoked. MCP
stdio Solver Doctor uses supplied log text and deterministic patterns only; it
does not prove real-world coverage across actual Abaqus failure logs. The
remaining warning is the previously audited external Starlette TestClient/httpx
fallback warning.

### Scope Check
No Docker, PyPI/GitHub Release, pull/merge/commit/push, LLM diagnosis,
persistent upload storage, Direct API/frontend changes, parser semantic rewrite,
or real Abaqus validation was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
V0.2-SOLVER-DOCTOR-API-FRONTEND-001

### Date
2026-06-05

### Status
Done

### Summary
Made Solver Doctor usable beyond the CLI. Direct API, MCP bridge, and the
frontend can now accept `.msg/.dat/.sta/.log` text payloads and return
deterministic JSON plus Markdown diagnosis evidence without invoking Abaqus or
an LLM.

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_solver_doctor.py tests/test_server_api_smoke.py tests/test_mcp_bridge_real_subprocess.py -q`: passed, 12 passed / 1 warning.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check doctor server.py mcp_bridge.py tests/test_solver_doctor.py tests/test_server_api_smoke.py tests/test_mcp_bridge_real_subprocess.py`: passed.
- `git diff --check`: passed.
- Actual HTTP probe against `uvicorn server:app --host 127.0.0.1 --port 8005`: `POST /api/doctor/diagnose` returned `FAILED`, 3 findings, categories `CONVERGENCE`/`LICENSE`/`RIGID_BODY_MOTION`, `real_env_verified=false`, and Markdown header `# Solver Doctor: Http-Doctor`.
- Served frontend probe on `127.0.0.1:8005`: confirmed Doctor nav/panel/button/API strings.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `git diff --check`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed, 303 passed / 1 warning.

### Files Changed
- `doctor/solver_doctor.py`
- `server.py`
- `mcp_bridge.py`
- `frontend/index.html`
- `tests/test_solver_doctor.py`
- `tests/test_server_api_smoke.py`
- `tests/test_mcp_bridge_real_subprocess.py`
- `README.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/NEXT_TICKETS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
No real Abaqus executable/license/syntaxcheck/solver/ODB was invoked. Solver
Doctor diagnoses supplied or existing log text through deterministic patterns
only; this does not prove real-world coverage across actual Abaqus failure logs.
The remaining warning is the previously audited external Starlette
TestClient/httpx fallback warning.

### Scope Check
No Docker, PyPI/GitHub Release, pull/merge/commit/push, LLM diagnosis,
persistent upload storage, broad frontend redesign, or real Abaqus validation
was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
V0.2-OFFLINE-DEMO-GALLERY-API-001

### Date
2026-06-05

### Status
Done

### Summary
Turned the offline demo gallery into a shared product surface. `evidence/demo_gallery.py`
now powers the CLI, Direct API, MCP bridge, and frontend Demo Gallery action,
and generates a top-level `offline-demo-gallery.zip` containing the gallery
index, manifest, and per-case evidence artifacts.

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_offline_evidence_slice.py tests/test_server_api_smoke.py tests/test_mcp_bridge_real_subprocess.py -q`: passed, 8 passed / 1 warning.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check evidence scripts server.py mcp_bridge.py tests/test_offline_evidence_slice.py tests/test_server_api_smoke.py tests/test_mcp_bridge_real_subprocess.py`: passed.
- `git diff --check`: passed.
- Actual HTTP probe against `uvicorn server:app --host 127.0.0.1 --port 8004`: `POST /api/evidence/demo-gallery` returned `overall_status=PASS`, `case_count=4`, downloadable `index.json`, and `offline-demo-gallery.zip`; ZIP inspection found `gallery_manifest.json`, `index.json`, `index.md`, and checked case evidence/capsule/bundle artifacts.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `git diff --check`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed, 300 passed / 1 warning.

### Files Changed
- `evidence/demo_gallery.py`
- `scripts/run_offline_demo_gallery.py`
- `server.py`
- `mcp_bridge.py`
- `frontend/index.html`
- `tests/test_offline_evidence_slice.py`
- `tests/test_server_api_smoke.py`
- `tests/test_mcp_bridge_real_subprocess.py`
- `README.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
No real Abaqus executable/license/syntaxcheck/solver/ODB was invoked. The demo
gallery uses supplied KPI fixtures only and does not certify KPI physics or
prove solver execution. Direct API and MCP bridge gallery artifacts are
in-process only. The remaining warning is the previously audited external
Starlette TestClient/httpx fallback warning.

### Scope Check
No Docker, PyPI/GitHub Release, pull/merge/commit/push, persistent multi-user
storage, example KPI value change, offline evidence semantic change, capsule
hash semantic change, or real Abaqus validation was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
V0.2-OFFLINE-DEMO-GALLERY-CLI-001

### Date
2026-06-05

### Status
Done

### Summary
Added a one-command offline demo gallery CLI. `scripts/run_offline_demo_gallery.py`
runs all four public offline evidence examples, writes per-case evidence/report/
capsule/bundle outputs, and writes top-level `index.json` plus `index.md` for
demo handoffs.

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_offline_evidence_slice.py tests/test_physics_contract_examples.py -q`: passed, 8 passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check scripts tests/test_offline_evidence_slice.py tests/test_physics_contract_examples.py`: initially failed on direct-executable script `E402`; added local `# ruff: noqa: E402`; rerun passed.
- `git diff --check`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python scripts/run_offline_demo_gallery.py --out-dir /tmp/abaqus-agent-demo-gallery --json`: passed; follow-up index probe confirmed 4 cases, `overall_status=PASS`, `index.md` exists, and all per-case bundles exist. The first probe wrapper failed because a here-doc consumed stdin; the generated output was valid and the corrected index probe passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed, 300 passed / 1 warning.

### Files Changed
- `scripts/run_offline_demo_gallery.py`
- `tests/test_offline_evidence_slice.py`
- `README.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/NEXT_TICKETS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
No real Abaqus executable/license/syntaxcheck/solver/ODB was invoked. The demo
gallery packages offline supplied-KPI fixtures only; it does not certify KPI
physics or prove solver execution. The remaining warning is the previously
audited external Starlette TestClient/httpx fallback warning.

### Scope Check
No Docker, PyPI/GitHub Release, pull/merge/commit/push, server/frontend changes,
persistent storage, example KPI value change, offline evidence semantic change,
capsule hash semantic change, or real Abaqus validation was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
V0.2-EVIDENCE-EXAMPLES-MCP-RESOURCE-001

### Date
2026-06-05

### Status
Done

### Summary
Exposed the Offline Evidence example gallery to MCP stdio clients. Added
`evidence://examples` resource and `get_offline_evidence_example_tool`, then
extended direct MCP tests and real stdio client smoke to list/read/call the new
resource/tool.

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_mcp_server.py tests/test_mcp_stdio_client.py -q`: passed, 24 passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check mcp_server.py tests/test_mcp_server.py tests/test_mcp_stdio_client.py`: passed.
- `git diff --check`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed, 299 passed / 1 warning.

### Files Changed
- `mcp_server.py`
- `tests/test_mcp_server.py`
- `tests/test_mcp_stdio_client.py`
- `README.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/NEXT_TICKETS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
No real Abaqus executable/license/syntaxcheck/solver/ODB was invoked. MCP
examples resource/tool returns local offline supplied-KPI fixtures only; it does
not certify KPI physics or prove solver execution. The remaining warning is the
previously audited external Starlette TestClient/httpx fallback warning.

### Scope Check
No Docker, PyPI/GitHub Release, pull/merge/commit/push, persistent storage,
server transport rewrite, example KPI value change, offline evidence semantic
change, or real Abaqus validation was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
V0.2-EVIDENCE-EXAMPLES-API-001

### Date
2026-06-05

### Status
Done

### Summary
Exposed the Offline Evidence example gallery as Direct API and MCP bridge
resources. Added `evidence.examples` to load example summaries and per-case
payloads, added `/api/evidence/examples` and `/api/evidence/examples/{case}` plus
bridge equivalents, and updated the Evidence frontend to load examples from the
API when online with local fallback.

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_server_api_smoke.py tests/test_mcp_bridge_real_subprocess.py tests/test_physics_contract_examples.py -q`: passed, 10 passed / 1 warning.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check evidence server.py mcp_bridge.py tests/test_server_api_smoke.py tests/test_mcp_bridge_real_subprocess.py tests/test_physics_contract_examples.py`: passed.
- `git diff --check`: passed.
- Actual HTTP probe against `uvicorn server:app --port 8003`: passed; `/api/evidence/examples` listed all four public cases, and `/api/evidence/examples/explicit_impact` returned expected run id, input path, candidate KPIs, and 3 contracts.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed, 297 passed / 1 warning.

### Files Changed
- `evidence/examples.py`
- `server.py`
- `mcp_bridge.py`
- `frontend/index.html`
- `tests/test_server_api_smoke.py`
- `tests/test_mcp_bridge_real_subprocess.py`
- `README.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/NEXT_TICKETS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
No real Abaqus executable/license/syntaxcheck/solver/ODB was invoked. The
examples API returns local offline supplied-KPI fixtures only; it does not
certify KPI physics or prove solver execution. The remaining warning is the
previously audited external Starlette TestClient/httpx fallback warning.

### Scope Check
No Docker, PyPI/GitHub Release, pull/merge/commit/push, persistent storage,
server transport rewrite, contract semantic change, KPI fixture value change, or
real Abaqus validation was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
V0.2-EVIDENCE-EXAMPLE-GALLERY-001

### Date
2026-06-05

### Status
Done

### Summary
Expanded Offline Evidence from a single cantilever sample into a four-case public
example gallery. Added baseline/candidate KPI fixtures for plate-hole, modal,
and explicit-impact examples, extended gallery tests to run all public examples
through the offline evidence workflow, and added a frontend case selector that
preloads case-specific KPI/contract/input-path/run-id data.

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_physics_contract_examples.py tests/test_offline_evidence_slice.py -q`: first run failed for non-cantilever examples because diff semantics correctly failed changed baseline/candidate fixtures; fixtures were adjusted to PASS reference baselines; rerun passed, 7 passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check tests/test_physics_contract_examples.py tests/test_offline_evidence_slice.py`: passed.
- `git diff --check`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python scripts/run_offline_evidence_slice.py --baseline-kpis examples/kpis/plate_hole_baseline.json --candidate-kpis examples/kpis/plate_hole_candidate.json --contracts examples/contracts/plate_hole.yaml --input cases/plate_hole/spec.yaml --out-dir /tmp/abaqus-agent-plate-hole-gallery --run-id plate-hole-gallery --json`: passed with `overall_status=PASS`, `contracts.status=PASS`, `diff.status=PASS`, and capsule manifest generated.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed, 297 passed / 1 warning.

### Files Changed
- `examples/kpis/plate_hole_baseline.json`
- `examples/kpis/plate_hole_candidate.json`
- `examples/kpis/modal_baseline.json`
- `examples/kpis/modal_candidate.json`
- `examples/kpis/explicit_impact_baseline.json`
- `examples/kpis/explicit_impact_candidate.json`
- `frontend/index.html`
- `tests/test_physics_contract_examples.py`
- `README.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/NEXT_TICKETS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
No real Abaqus executable/license/syntaxcheck/solver/ODB was invoked. Gallery
KPI fixtures are offline supplied-KPI examples for product demonstration and
regression plumbing; they are not certified real Abaqus outputs or physical
truth claims. The remaining warning is the previously audited external Starlette
TestClient/httpx fallback warning.

### Scope Check
No Docker, PyPI/GitHub Release, pull/merge/commit/push, server transport change,
contract semantic change, solver behavior change, or real Abaqus validation was
performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
V0.2-EVIDENCE-RUN-HISTORY-001

### Date
2026-06-05

### Status
Done

### Summary
Added recent offline Evidence run history to the artifact surface. Direct
FastAPI and the HTTP-to-MCP bridge now expose recent generated evidence artifact
records with run id, artifact id, sequence, generated time, verdict, summary
counts, capsule summary, and artifact URLs. The Evidence workspace renders a
recent runs list with MD/ZIP links.

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_server_api_smoke.py tests/test_mcp_bridge_real_subprocess.py tests/test_offline_evidence_slice.py -q`: passed, 7 passed / 1 warning.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check server.py mcp_bridge.py tests/test_server_api_smoke.py tests/test_mcp_bridge_real_subprocess.py`: passed.
- `git diff --check`: passed.
- Actual HTTP recent probe against `uvicorn server:app --port 8003`: first run exposed an ordering bug for same-second runs; after adding a sequence field, the probe passed with the second run listed first, `top_is_second=true`, and ZIP URL present.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed, 293 passed / 1 warning.

### Files Changed
- `server.py`
- `mcp_bridge.py`
- `frontend/index.html`
- `tests/test_server_api_smoke.py`
- `tests/test_mcp_bridge_real_subprocess.py`
- `README.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/NEXT_TICKETS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
No real Abaqus executable/license/syntaxcheck/solver/ODB was invoked. Recent
history lists in-process offline evidence artifacts only; it is not persistent
multi-user storage and does not prove solver execution. The remaining warning
is the previously audited external Starlette TestClient/httpx fallback warning.

### Scope Check
No Docker, PyPI/GitHub Release, pull/merge/commit/push, auth/storage policy,
database/cloud storage, solver behavior change, capsule hash semantic change, or
real Abaqus validation was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
V0.2-EVIDENCE-BUNDLE-ZIP-001

### Date
2026-06-05

### Status
Done

### Summary
Added a single downloadable ZIP bundle for offline Evidence outputs. Direct
FastAPI and the HTTP-to-MCP bridge now create and return `bundle_zip` artifact
URLs. Each bundle contains `evidence.json`, `evidence.md`, `capsule.json`, and
`bundle_manifest.json`; the Evidence workspace renders a ZIP link alongside
JSON/MD/CAPSULE links.

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_server_api_smoke.py tests/test_mcp_bridge_real_subprocess.py tests/test_offline_evidence_slice.py -q`: passed, 7 passed / 1 warning.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check server.py mcp_bridge.py tests/test_server_api_smoke.py tests/test_mcp_bridge_real_subprocess.py`: passed.
- `git diff --check`: passed.
- Actual HTTP ZIP probe against `uvicorn server:app --port 8003`: passed; `POST /api/evidence/offline` returned `PASS`, `GET bundle.zip` returned `application/zip`, ZIP file list matched `bundle_manifest.json`, `capsule.json`, `evidence.json`, `evidence.md`, manifest run id/artifact id matched, and `evidence.md` contained `Verdict Summary`.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed, 293 passed / 1 warning.

### Files Changed
- `server.py`
- `mcp_bridge.py`
- `frontend/index.html`
- `tests/test_server_api_smoke.py`
- `tests/test_mcp_bridge_real_subprocess.py`
- `README.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/NEXT_TICKETS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
No real Abaqus executable/license/syntaxcheck/solver/ODB was invoked. The ZIP
bundle packages offline supplied-KPI evidence artifacts for delivery; it does
not prove solver execution, change capsule hash semantics, or provide
persistent multi-user storage. The remaining warning is the previously audited
external Starlette TestClient/httpx fallback warning.

### Scope Check
No Docker, PyPI/GitHub Release, pull/merge/commit/push, auth/storage policy,
artifact database, solver behavior change, capsule hash semantic change, or real
Abaqus validation was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
V0.2-EVIDENCE-ARTIFACT-SURFACE-001

### Date
2026-06-05

### Status
Done

### Summary
Added browser/API retrievable artifact URLs for offline evidence outputs. Direct
FastAPI and the HTTP-to-MCP bridge now register generated `evidence.json`,
`evidence.md`, and `capsule.json` artifacts in controlled in-process registries
and return `artifact_id` plus `artifact_urls` from the offline evidence POST
response. The Evidence workspace renders JSON/MD/CAPSULE links from those URLs.

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_server_api_smoke.py tests/test_mcp_bridge_real_subprocess.py tests/test_offline_evidence_slice.py -q`: passed, 7 passed / 1 warning.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check server.py mcp_bridge.py tests/test_server_api_smoke.py tests/test_mcp_bridge_real_subprocess.py`: passed.
- `git diff --check`: passed.
- Actual HTTP probe against `uvicorn server:app --port 8003`: passed; `POST /api/evidence/offline` returned `PASS` and artifact URLs, and GET retrieval passed for `evidence.json`, `evidence.md`, and `capsule.json` with expected content types/markers.
- `rg -n "artifactLink|artifact_urls|artifact-link|new URL\\(url, API\\)" frontend/index.html`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed, 293 passed / 1 warning.

### Files Changed
- `server.py`
- `mcp_bridge.py`
- `frontend/index.html`
- `tests/test_server_api_smoke.py`
- `tests/test_mcp_bridge_real_subprocess.py`
- `README.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/NEXT_TICKETS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
No real Abaqus executable/license/syntaxcheck/solver/ODB was invoked. The
artifact surface makes generated offline evidence deliverables retrievable from
browser/API surfaces; it does not prove solver execution or provide persistent
multi-user storage. In-app browser automation was unavailable for this ticket,
so UI link rendering was source-verified and artifact retrieval was verified by
real HTTP probe plus API/MCP tests.

### Scope Check
No Docker, PyPI/GitHub Release, pull/merge/commit/push, auth/storage policy,
artifact database, solver behavior change, or real Abaqus validation was
performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
V0.2-CAPSULE-RUN-LIFECYCLE-001

### Date
2026-06-05

### Status
Done

### Summary
Standardized capsule evidence metadata across offline evidence and smoke harness
outputs. `capsule.metadata.evidence_metadata` now supplies common provenance
fields, offline evidence capsules identify supplied-KPI offline evidence, and
smoke harness capsules identify dry-run/mock-real/require-real source and
evidence level without changing real-Abaqus verification semantics.

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_capsule_store.py tests/test_offline_evidence_slice.py tests/test_run_real_abaqus_smoke.py -q`: passed, 11 passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check capsule evidence/offline.py scripts/run_real_abaqus_smoke.py tests/test_capsule_store.py tests/test_offline_evidence_slice.py tests/test_run_real_abaqus_smoke.py`: passed.
- `git diff --check`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed, 293 passed / 1 warning.

### Files Changed
- `capsule/metadata.py`
- `evidence/offline.py`
- `scripts/run_real_abaqus_smoke.py`
- `tests/test_capsule_store.py`
- `tests/test_offline_evidence_slice.py`
- `tests/test_run_real_abaqus_smoke.py`
- `README.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/NEXT_TICKETS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
No real Abaqus executable/license/syntaxcheck/solver/ODB was invoked. The
metadata makes evidence source and real-env state explicit; it does not upgrade
offline, dry-run, or mock-real artifacts into real solver verification. The
remaining warning is the previously audited external Starlette TestClient/httpx
fallback warning.

### Scope Check
No Docker, PyPI/GitHub Release, pull/merge/commit/push, broad capsule schema
migration, artifact hash semantic change, solver behavior change, or real
Abaqus validation was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
V0.2-OFFLINE-EVIDENCE-MCP-PARITY-001

### Date
2026-06-05

### Status
Done

### Summary
Added MCP transport parity for the offline evidence workflow. MCP stdio now has
`run_offline_evidence_tool`; the HTTP-to-MCP bridge exposes
`POST /mcp/api/evidence/offline`; the frontend Evidence workspace now uses the
active `API` base so Direct API and MCP bridge modes share the same endpoint
suffix.

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_mcp_stdio_client.py tests/test_mcp_bridge_real_subprocess.py tests/test_server_api_smoke.py tests/test_offline_evidence_slice.py -q`: passed, 8 passed / 1 warning.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check mcp_server.py mcp_bridge.py tests/test_mcp_stdio_client.py tests/test_mcp_bridge_real_subprocess.py`: passed.
- Real HTTP probe against `uvicorn mcp_bridge:app --port 8002` `POST /mcp/api/evidence/offline`: passed with `PASS/PASS/PASS`, `Verdict Summary` in report Markdown, and capsule manifest present.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `git diff --check`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed, 292 passed / 1 warning.

### Files Changed
- `README.md`
- `frontend/index.html`
- `mcp_server.py`
- `mcp_bridge.py`
- `tests/test_mcp_stdio_client.py`
- `tests/test_mcp_bridge_real_subprocess.py`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/NEXT_TICKETS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
No real Abaqus executable/license/syntaxcheck/solver/ODB was invoked. MCP parity
uses the same supplied-KPI offline evidence workflow. The remaining warning is
the previously audited external Starlette TestClient/httpx fallback warning.

### Scope Check
No Docker, PyPI/GitHub Release, pull/merge/commit/push, broad MCP protocol
rewrite, commercial payment flow, report semantic change, or real Abaqus
validation was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
V0.2-REPORT-POLISH-001

### Date
2026-06-05

### Status
Done

### Summary
Polished offline `evidence.md` into a clearer early user-facing Simulation QA
report. The report now has verdict summary, run metadata, inputs, Physics
Contracts, Simulation Diff, capsule provenance, and verification boundary
sections, with explicit real-Abaqus `not verified` status.

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_offline_evidence_slice.py tests/test_server_api_smoke.py -q`: passed, 6 passed / 1 warning.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check evidence/offline.py tests/test_offline_evidence_slice.py`: passed.
- CLI report probe with cantilever examples plus `rg` for `Verdict Summary`, `Run Metadata`, `Capsule Provenance`, and `Real Abaqus execution`: passed.
- Chrome UI smoke at `http://127.0.0.1:8000` after server restart: passed; Evidence workspace showed polished report with `Verdict Summary`, `Run Metadata`, PASS rows, and real-Abaqus `not verified` row.
- `screencapture -x /tmp/abaqus-agent-offline-evidence-report-polish-ui-smoke.png`: passed; screenshot is PNG 1920x1080.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `git diff --check`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed, 292 passed / 1 warning.

### Files Changed
- `evidence/offline.py`
- `tests/test_offline_evidence_slice.py`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
No real Abaqus executable/license/syntaxcheck/solver/ODB was invoked. The report
continues to represent supplied KPI dictionaries only. The remaining warning is
the previously audited external Starlette TestClient/httpx fallback warning.

### Scope Check
No Docker, PyPI/GitHub Release, pull/merge/commit/push, frontend redesign,
commercial payment flow, contract/diff semantic change, or real Abaqus
validation was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
V0.2-OFFLINE-EVIDENCE-FRONTEND-001

### Date
2026-06-05

### Status
Done

### Summary
Added a browser-visible Offline Evidence workspace to the existing frontend.
The workspace preloads editable cantilever KPI/contract examples, calls
`POST /api/evidence/offline`, and displays overall verdict, contract/diff
summaries, capsule counts, evidence/report/capsule paths, capsule hash, and
Markdown report text.

### Commands
- Chrome UI smoke at `http://127.0.0.1:8000`: passed; clicked Evidence, ran the preloaded example, observed `PASS`, `PASS · 4`, `PASS · 2`, `5/2`, artifact paths, capsule hash, and Markdown report.
- `screencapture -x /tmp/abaqus-agent-offline-evidence-ui-smoke.png`: passed; screenshot is PNG 1920x1080.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_server_api_smoke.py tests/test_offline_evidence_slice.py -q`: passed, 6 passed / 1 warning.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `git diff --check`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed, 292 passed / 1 warning.

### Files Changed
- `README.md`
- `frontend/index.html`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/NEXT_TICKETS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
No real Abaqus executable/license/syntaxcheck/solver/ODB was invoked. The UI
calls the offline evidence API with supplied KPI dictionaries only. The
remaining warning is the previously audited external Starlette TestClient/httpx
fallback warning.

### Scope Check
No Docker, PyPI/GitHub Release, pull/merge/commit/push, commercial payment
flow, new frontend build tooling, or real Abaqus validation was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
V0.2-OFFLINE-EVIDENCE-API-001

### Date
2026-06-05

### Status
Done

### Summary
Extracted the offline evidence workflow into `evidence.offline` and exposed it
through `POST /api/evidence/offline`. The API now accepts baseline/candidate KPI
dicts, contract definitions, a safe run id, optional local input path/metadata,
and returns status summaries, evidence/report paths, Markdown report text, and
capsule metadata. The CLI remains a backward-compatible wrapper around the same
service.

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_offline_evidence_slice.py tests/test_server_api_smoke.py -q`: passed, 6 passed / 1 warning.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check evidence scripts/run_offline_evidence_slice.py server.py tests/test_offline_evidence_slice.py tests/test_server_api_smoke.py`: passed.
- CLI refactor probe with cantilever example KPI/contract/spec inputs: passed; `overall_status=PASS`, `contracts.status=PASS`, `diff.status=PASS`, capsule manifest present, Markdown report present, stdout/evidence capsule path matched.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pip install -e ".[dev]"`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `git diff --check`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed, 292 passed / 1 warning.

### Files Changed
- `README.md`
- `pyproject.toml`
- `evidence/__init__.py`
- `evidence/offline.py`
- `scripts/run_offline_evidence_slice.py`
- `server.py`
- `tests/test_server_api_smoke.py`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/NEXT_TICKETS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
No real Abaqus executable/license/syntaxcheck/solver/ODB was invoked. The API
uses supplied KPI dictionaries only and writes local temp-dir evidence bundles.
The remaining warning is the previously audited external Starlette
TestClient/httpx fallback warning.

### Scope Check
No frontend UI, Docker, PyPI/GitHub Release, pull/merge/commit/push, commercial
payment flow, or real Abaqus validation was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
V0.2-OFFLINE-EVIDENCE-SLICE-001

### Date
2026-06-05

### Status
Done

### Summary
Built a runnable offline v0.2 Simulation QA evidence slice. A user can run one
README command with baseline/candidate KPI JSON, a Physics Contract file, and
an input spec, then receive `evidence.json`, `evidence.md`, and a capsule
manifest. This ticket intentionally pivots from small boundary cleanup to a
product-visible workflow combining Physics Contracts, Simulation Diff, and
Experiment Capsule evidence.

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_offline_evidence_slice.py tests/test_physics_contract_examples.py tests/test_simulation_diff.py tests/test_capsule_store.py -q`: passed, 12 passed.
- `/tmp/abaqus-agent-audit-venv/bin/python scripts/run_offline_evidence_slice.py --baseline-kpis examples/kpis/cantilever_baseline.json --candidate-kpis examples/kpis/cantilever_candidate.json --contracts examples/contracts/cantilever.yaml --input cases/cantilever/spec.yaml --out-dir <tmpdir> --run-id cantilever-offline --json`: passed; `overall_status=PASS`, `contracts.status=PASS`, `diff.status=PASS`, capsule manifest present, Markdown report present.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check scripts/run_offline_evidence_slice.py tests/test_offline_evidence_slice.py`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pip install -e ".[dev]"`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `git diff --check`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed, 291 passed / 1 warning.

### Files Changed
- `README.md`
- `pyproject.toml`
- `scripts/run_offline_evidence_slice.py`
- `examples/kpis/cantilever_baseline.json`
- `examples/kpis/cantilever_candidate.json`
- `examples/contracts/cantilever.yaml`
- `examples/contracts/plate_hole.yaml`
- `examples/contracts/modal.yaml`
- `examples/contracts/explicit_impact.yaml`
- `tests/test_offline_evidence_slice.py`
- `tests/test_physics_contract_examples.py`
- Related existing evidence modules/tests from the current Goal Chain batch:
  `contracts/`, `simdiff/`, `capsule/`, `run_benchmark.py`,
  `scripts/run_real_abaqus_smoke.py`, and their focused tests.
- `docs/goal_driver/GOAL_CHAIN.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/NEXT_TICKETS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
No real Abaqus executable/license/syntaxcheck/solver/ODB was invoked. The
offline slice validates product plumbing over supplied KPI JSON only. The
remaining warning is the previously audited external Starlette TestClient/httpx
fallback warning.

### Scope Check
No Docker, PyPI/GitHub Release, pull/merge/commit/push, commercial payment
flow, broad UI redesign, or real Abaqus validation was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
FINAL-HANDOFF-3H-EXPIRY-001

### Date
2026-06-04

### Status
Done

### Summary
3-hour Goal Chain budget expired; wrote final `CODEX_HANDOFF.md` and preserved Docker/PyPI/GitHub Release/真实 Abaqus as blocked branches, not whole-chain stop conditions.

### Commands
- `git diff --check docs/goal_driver/CODEX_HANDOFF.md docs/goal_driver/GOAL_PROGRESS.md docs/goal_driver/CODEX_RUN_LEDGER.md`: passed.

### Files Changed
- `docs/goal_driver/CODEX_HANDOFF.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Final handoff documentation diff check passed.

### Scope Check
Stopped because the 3-hour budget expired. No product/source/test behavior change, real Abaqus, Docker, PyPI, GitHub Release, pull/merge, commit, or push work was performed during final handoff.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
RUN-CASE-CONTRACT-EVALUATION-001

### Date
2026-06-05

### Status
Done

### Summary
`run_benchmark.run_case` now attaches Physics Contract evaluation results when a completed run has KPI values and an expected/contract file. Legacy `expected.json` files flow through `contracts.io`; contract loader/evaluation failures are recorded under `contracts.status=ERROR` without changing completed pipeline status. Tests use a fake orchestrator; no real Abaqus was invoked.

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_run_benchmark_contracts.py tests/test_run_benchmark_report.py tests/test_physics_contract_io.py tests/test_physics_contracts.py -q`: passed, 15 passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check run_benchmark.py tests/test_run_benchmark_contracts.py`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pip install -e ".[dev]"`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `git diff --check`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed, 288 passed / 1 warning.

### Files Changed
- `README.md`
- `run_benchmark.py`
- `tests/test_run_benchmark_contracts.py`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
No real Abaqus executable/license/syntaxcheck/solver/ODB was invoked. The remaining warning is the previously audited external Starlette TestClient/httpx fallback warning.

### Scope Check
No orchestrator internals, schema migration, Docker, PyPI/GitHub Release, pull/merge/commit/push, or real Abaqus validation was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
BENCHMARK-CONTRACT-REPORT-001

### Date
2026-06-05

### Status
Done

### Summary
Benchmark Markdown report now has a `## Physics Contracts` section when result dicts include `contracts.checks`. This gives Physics Contract results a report surface without running Abaqus or wiring contracts into `run_case`/orchestrator yet.

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_run_benchmark_report.py -q`: passed, 3 passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check run_benchmark.py tests/test_run_benchmark_report.py`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pip install -e ".[dev]"`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `git diff --check`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed, 286 passed / 1 warning.

### Files Changed
- `README.md`
- `run_benchmark.py`
- `tests/test_run_benchmark_report.py`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
No real Abaqus executable/license/syntaxcheck/solver/ODB was invoked. The remaining warning is the previously audited external Starlette TestClient/httpx fallback warning.

### Scope Check
No run_case/orchestrator wiring, schema migration, Docker, PyPI/GitHub Release, pull/merge/commit/push, or real Abaqus validation was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
PHYSICS-CONTRACT-IO-001

### Date
2026-06-05

### Status
Done

### Summary
新增 Physics Contract IO bridge：`contracts.io.load_contracts` 支持 JSON list、YAML/JSON `{contracts: [...]}`，并可把现有 `expected.json` KPI reference/tolerance 转成 `relative_error` contracts。该 ticket 只做 loader/conversion 和 evaluator fixture 测试，不接 orchestrator/schema，也不宣称真实物理契约已验证。

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_physics_contract_io.py tests/test_physics_contracts.py -q`: passed, 10 passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check contracts tests/test_physics_contract_io.py tests/test_physics_contracts.py`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pip install -e ".[dev]"`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `git diff --check`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed, 285 passed / 1 warning.

### Files Changed
- `README.md`
- `contracts/io.py`
- `tests/test_physics_contract_io.py`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
No real Abaqus executable/license/syntaxcheck/solver/ODB was invoked. The remaining warning is the previously audited external Starlette TestClient/httpx fallback warning.

### Scope Check
No orchestrator wiring, schema migration, Docker, PyPI/GitHub Release, pull/merge/commit/push, or real Abaqus validation was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
SMOKE-HARNESS-CAPSULE-ARTIFACT-001

### Date
2026-06-05

### Status
Done

### Summary
将 Experiment Capsule store 接入 smoke/evidence harness。`scripts/run_real_abaqus_smoke.py` 现在在 evidence 中写入 top-level `capsule` 字段，并在 `out_dir/capsule/<case-mode>/capsule.json` 保存 case inputs、stage JSON artifacts、missing report artifact（如存在）的 hash/provenance manifest。该集成不改变 `real_env_verified` 判定，不把 dry-run/mock-real 升级为真实 Abaqus evidence。

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_run_real_abaqus_smoke.py tests/test_capsule_store.py -q`: passed, 8 passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check scripts/run_real_abaqus_smoke.py tests/test_run_real_abaqus_smoke.py capsule`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python scripts/run_real_abaqus_smoke.py --dry-run --json --out-dir <tmpdir>`: passed; `overall_status=dry-run-ready`, `run_id=cantilever-dry-run`, capsule had 3 inputs and 7 artifacts.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pip install -e ".[dev]"`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `git diff --check`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed, 280 passed / 1 warning.

### Files Changed
- `README.md`
- `scripts/run_real_abaqus_smoke.py`
- `tests/test_run_real_abaqus_smoke.py`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
No real Abaqus executable/license/syntaxcheck/solver/ODB was invoked. The remaining warning is the previously audited external Starlette TestClient/httpx fallback warning.

### Scope Check
No real-env verification semantics, Docker, PyPI/GitHub Release, pull/merge/commit/push, or real Abaqus validation was changed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
SIMULATION-DIFF-KPI-EVIDENCE-001

### Date
2026-06-05

### Status
Done

### Summary
新增 deterministic Simulation Diff KPI report：`simdiff.kpi_diff.diff_kpis` 比较 baseline/candidate KPI dict，支持 per-KPI `rtol`/`atol`，标记 PASS/FAIL/ADDED/REMOVED；`render_markdown` 输出便携 Markdown 表。该 ticket 不做 ODB extraction、不接 capsule/orchestrator，也不宣称真实 Abaqus run diff 已验证。

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_simulation_diff.py -q`: initially 1 failed due test row-order assumption, then passed, 5 passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check simdiff tests/test_simulation_diff.py pyproject.toml`: passed after import-order fix.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pip install -e ".[dev]"`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `git diff --check`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed, 280 passed / 1 warning.

### Files Changed
- `README.md`
- `pyproject.toml`
- `simdiff/__init__.py`
- `simdiff/kpi_diff.py`
- `tests/test_simulation_diff.py`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
No real Abaqus executable/license/syntaxcheck/solver/ODB was invoked. The remaining warning is the previously audited external Starlette TestClient/httpx fallback warning.

### Scope Check
No orchestrator wiring, capsule integration, ODB extraction, Docker, PyPI/GitHub Release, pull/merge/commit/push, or real Abaqus validation was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
EXPERIMENT-CAPSULE-STORE-001

### Date
2026-06-05

### Status
Done

### Summary
新增最小 Experiment Capsule store：`capsule.store.create_capsule` 会把已知 input/artifact 文件复制到 capsule 目录，写入 `capsule.json` manifest，并记录 metadata、相对路径、source path、size、SHA-256 和 stable capsule hash。该 ticket 只验证本地 store/hash/manifest semantics，不接 orchestrator，也不宣称 artifact 或真实 Abaqus provenance 已验证。

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_capsule_store.py -q`: passed, 4 passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check capsule tests/test_capsule_store.py pyproject.toml`: passed after import-order fix.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pip install -e ".[dev]"`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `git diff --check`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed, 275 passed / 1 warning.

### Files Changed
- `README.md`
- `pyproject.toml`
- `capsule/__init__.py`
- `capsule/store.py`
- `tests/test_capsule_store.py`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
No real Abaqus executable/license/syntaxcheck/solver/ODB was invoked. The remaining warning is the previously audited external Starlette TestClient/httpx fallback warning.

### Scope Check
No orchestrator wiring, schema migration, Docker, PyPI/GitHub Release, pull/merge/commit/push, or real Abaqus validation was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
PHYSICS-CONTRACT-EVALUATOR-001

### Date
2026-06-05

### Status
Done

### Summary
新增纯 Python Physics Contract evaluator：`contracts.evaluator.evaluate_contracts` 可对 KPI dict 执行 `range`、`direction`、`relative_error`、`order` contract，并返回 PASS/WARNING/FAIL 结构化结果。该 ticket 只验证 evaluator semantics，不接入 orchestrator/YAML schema，也不宣称真实 Abaqus 物理契约已验证。

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_physics_contracts.py -q`: passed, 5 passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check contracts tests/test_physics_contracts.py pyproject.toml`: passed after import-order fix.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pip install -e ".[dev]"`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `git diff --check`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed, 271 passed / 1 warning.

### Files Changed
- `README.md`
- `pyproject.toml`
- `contracts/__init__.py`
- `contracts/evaluator.py`
- `tests/test_physics_contracts.py`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
No real Abaqus executable/license/syntaxcheck/solver/ODB was invoked. The remaining warning is the previously audited external Starlette TestClient/httpx fallback warning.

### Scope Check
No orchestrator wiring, schema migration, Docker, PyPI/GitHub Release, pull/merge/commit/push, or real Abaqus validation was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
SOLVER-DOCTOR-LOG-EVIDENCE-001

### Date
2026-06-05

### Status
Done

### Summary
新增本地 Solver Doctor log evidence 面：`doctor.solver_doctor` 可从已有 Abaqus `.msg/.dat/.sta/.log` artifact 生成 deterministic JSON/Markdown 诊断报告，不调用 Abaqus、不调用 LLM。扩展日志 parser 的窄分类/line-number 证据，并用 fixture 覆盖 license、convergence、distortion、rigid-body、path、ODB、syntax、memory、output 等常见类别。

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_solver_doctor.py tests/test_premium_autorepair.py -q`: passed, 20 passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check doctor premium/autorepair/log_parser.py tests/test_solver_doctor.py pyproject.toml`: passed.
- `python -m doctor.solver_doctor <tmpdir> Job-1 --format markdown --out <file>` using Python 3.11 venv: passed; rendered fixture license/convergence Markdown report.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pip install -e ".[dev]"`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `git diff --check`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed, 266 passed / 1 warning.

### Files Changed
- `README.md`
- `pyproject.toml`
- `doctor/__init__.py`
- `doctor/solver_doctor.py`
- `premium/autorepair/log_parser.py`
- `tests/test_solver_doctor.py`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
No real Abaqus executable/license/syntaxcheck/solver/ODB was invoked. Solver Doctor evidence is currently fixture/log-artifact verified only. The remaining warning is the previously audited external Starlette TestClient/httpx fallback warning.

### Scope Check
No Docker, PyPI/GitHub Release, pull/merge/commit/push, or premium autorepair architecture rewrite was performed. Existing dirty Goal Chain worktree remains expected.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
FINAL-STATUS-AT-EXPIRY-CHECK-001

### Date
2026-06-04

### Status
Done

### Summary
预算到期前最后 status/diff checkpoint：`git status --short` 仍为预期 Goal Chain dirty worktree，full `git diff --check` 通过。

### Commands
- `git status --short`: captured expected dirty Goal Chain worktree.
- `git diff --check`: passed.
- `git diff --check docs/goal_driver/GOAL_PROGRESS.md docs/goal_driver/CODEX_RUN_LEDGER.md`: passed.

### Files Changed
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Final pre-expiry status/diff checkpoint passed.

### Scope Check
Stayed within status/diff verification and Goal Driver records. No product/source/test behavior change, cleanup, staging, commit, final handoff, `update_goal complete`, real Abaqus, Docker, PyPI, GitHub Release, pull/merge, or push work was performed during this ticket.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
FINAL-HANDOFF-PREP-READS-001

### Date
2026-06-04

### Status
Done

### Summary
最终 handoff 前读取准备完成：复读 current state 的环境限制/current blockers、progress 顶部与近期 ticket sequence、ledger 最新 entries。未在预算到期前写最终 handoff 或 complete。

### Commands
- `tail -n 40 docs/goal_driver/CURRENT_STATE.md`: passed.
- `sed -n '1,34p' docs/goal_driver/GOAL_PROGRESS.md`: passed.
- `sed -n '400,460p' docs/goal_driver/GOAL_PROGRESS.md`: passed.
- `head -n 120 docs/goal_driver/CODEX_RUN_LEDGER.md`: passed.
- `git diff --check docs/goal_driver/GOAL_PROGRESS.md docs/goal_driver/CODEX_RUN_LEDGER.md`: passed.

### Files Changed
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Read-only final handoff prep checks passed. No final handoff was produced during this ticket.

### Scope Check
Stayed within Goal Driver prep reads and records. No product/source/test behavior change, final handoff, `update_goal complete`, real Abaqus, Docker, PyPI, GitHub Release, pull/merge, commit, or push work was performed during this ticket.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
CHAIN-BUDGET-PREEXPIRY-AUDIT-001

### Date
2026-06-04

### Status
Done

### Summary
预算到期前审计 stop-condition 状态。近期 focused tests 和 262 full baseline 已记录；无三连失败；Docker/PyPI/GitHub Release/真实 Abaqus 仍按 blocked branches 处理，不是整条 Goal Chain 的 stop condition。

### Commands
- `rg -n 'blocked branches, not whole Goal Chain stop conditions|3 consecutive|262 passed|5 passed, 1 warning|21 passed|26 passed|13 passed|3 passed' docs/goal_driver/GOAL_PROGRESS.md docs/goal_driver/CODEX_RUN_LEDGER.md docs/goal_driver/CURRENT_STATE.md`: passed.
- `git diff --check docs/goal_driver/GOAL_PROGRESS.md docs/goal_driver/CODEX_RUN_LEDGER.md docs/goal_driver/CURRENT_STATE.md`: passed.

### Files Changed
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Pre-expiry stop-condition audit passed. No product/source tests were needed because this ticket only audited Goal Driver state.

### Scope Check
Stayed within Goal Driver state audit and records. No final handoff, `update_goal complete`, product/source/test behavior change, real Abaqus, Docker, PyPI, GitHub Release, pull/merge, commit, or push work was performed during this ticket.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
API-MCP-NEAR-BUDGET-FOCUSED-REFRESH-001

### Date
2026-06-04

### Status
Done

### Summary
预算末尾刷新 focused API/MCP smoke evidence。direct FastAPI smoke、MCP stdio client、HTTP-to-MCP bridge real subprocess smoke 均通过；未执行真实 Abaqus。

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_server_api_smoke.py tests/test_mcp_stdio_client.py tests/test_mcp_bridge_real_subprocess.py`: passed; 5 passed, 1 warning.
- `git diff --check docs/goal_driver/GOAL_PROGRESS.md docs/goal_driver/CODEX_RUN_LEDGER.md`: passed.

### Files Changed
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Focused API/MCP smoke tests passed. The warning is the previously audited external Starlette TestClient/httpx fallback.

### Scope Check
Stayed within focused no-real-Abaqus API/MCP smoke verification and Goal Driver records. No endpoint/source behavior change, real Abaqus, Docker, PyPI, GitHub Release, pull/merge, commit, or push work was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
ERRORS-STATIC-GUARD-FOCUSED-REFRESH-001

### Date
2026-06-04

### Status
Done

### Summary
刷新 structured-error 和 static-guard focused evidence。`tests/test_errors.py` 与 `tests/test_static_guard.py` 均通过；未改 guard policy 或错误模型。

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_errors.py tests/test_static_guard.py`: passed; 21 passed.
- `git diff --check docs/goal_driver/GOAL_PROGRESS.md docs/goal_driver/CODEX_RUN_LEDGER.md`: passed.

### Files Changed
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Focused errors/static guard tests passed.

### Scope Check
Stayed within focused errors/static guard verification and Goal Driver records. No guard policy, error-model, source behavior, real Abaqus, Docker, PyPI, GitHub Release, pull/merge, commit, or push work was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
CORE-SCHEMA-FOCUSED-REFRESH-001

### Date
2026-06-04

### Status
Done

### Summary
刷新 core pipeline 和 public schema focused evidence。`tests/test_core_pipeline.py` 与 `tests/test_schema.py` 均通过；未执行真实 Abaqus。

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_core_pipeline.py tests/test_schema.py`: passed; 26 passed.
- `git diff --check docs/goal_driver/GOAL_PROGRESS.md docs/goal_driver/CODEX_RUN_LEDGER.md`: passed.

### Files Changed
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Focused core/schema tests passed.

### Scope Check
Stayed within focused no-real-Abaqus core/schema verification and Goal Driver records. No source behavior change, real Abaqus, Docker, PyPI, GitHub Release, pull/merge, commit, or push work was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
LLM-PLANNER-MOCK-FOCUSED-REFRESH-001

### Date
2026-06-04

### Status
Done

### Summary
刷新 LLM planner provider adapter mock evidence。OpenAI/Anthropic mocked extraction and env override restoration tests passed；未进行外部 LLM API call、真实 API key 使用、provider dependency/model changes。

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_llm_planner_provider_mock.py`: passed; 3 passed.
- `git diff --check docs/goal_driver/GOAL_PROGRESS.md docs/goal_driver/CODEX_RUN_LEDGER.md`: passed.

### Files Changed
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Focused LLM provider mock tests passed. This verifies adapter plumbing only, not live provider/API behavior.

### Scope Check
Stayed within focused no-network LLM mock verification and Goal Driver records. No external API calls, real API keys, provider dependency/model changes, product behavior change, Docker, PyPI, GitHub Release, pull/merge, commit, or push work was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
SMOKE-EVIDENCE-HARNESS-FOCUSED-REFRESH-001

### Date
2026-06-04

### Status
Done

### Summary
刷新 no-real-Abaqus smoke/evidence harness evidence。环境 validator、real-Abaqus smoke harness dry/mock/missing-prereq tests、Markdown evidence report renderer tests 均通过；未执行真实 Abaqus。

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_validate_abaqus_env.py tests/test_run_real_abaqus_smoke.py tests/test_render_smoke_evidence_report.py`: passed; 13 passed.
- `git diff --check docs/goal_driver/GOAL_PROGRESS.md docs/goal_driver/CODEX_RUN_LEDGER.md`: passed.

### Files Changed
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Focused smoke/evidence harness tests passed. This verifies dry/mock/missing-prereq/report plumbing only, not real Abaqus execution.

### Scope Check
Stayed within focused no-real-Abaqus harness verification and Goal Driver records. No real Abaqus, report artifact write outside tests, product behavior change, Docker, PyPI, GitHub Release, pull/merge, commit, or push work was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
LOCAL-DIFF-STATUS-CHECKPOINT-001

### Date
2026-06-04

### Status
Done

### Summary
刷新最新 Goal Driver 记录后的全工作树 diff/status 检查点。full `git diff --check` 通过；`git status --short` 仍为预期 Goal Chain dirty worktree。

### Commands
- `git diff --check`: passed.
- `git status --short`: captured expected dirty Goal Chain worktree.
- `git diff --check docs/goal_driver/GOAL_PROGRESS.md docs/goal_driver/CODEX_RUN_LEDGER.md`: passed.

### Files Changed
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Full worktree diff/status checkpoint passed. No product/source tests were needed because this ticket did not change product code.

### Scope Check
Stayed within local diff/status verification and Goal Driver records. No product/source/test behavior change, cleanup, staging, commit, real Abaqus, Docker, PyPI, GitHub Release, pull/merge, or push work was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
LEDGER-PROGRESS-LATEST-TICKET-CHECK-001

### Date
2026-06-04

### Status
Done

### Summary
验证连续小票后的 Goal Driver 顶部状态一致性：`GOAL_PROGRESS.md` active ticket 为本票；`CODEX_RUN_LEDGER.md` 顶部已完成票为上一张 `DIRTY-WORKTREE-DIFFSTAT-SNAPSHOT-001`；近期 continuation ticket sequence 可检索。

### Commands
- `sed -n '1,28p' docs/goal_driver/GOAL_PROGRESS.md`: passed; active ticket is `LEDGER-PROGRESS-LATEST-TICKET-CHECK-001`.
- `head -n 80 docs/goal_driver/CODEX_RUN_LEDGER.md`: passed; top completed entry is `DIRTY-WORKTREE-DIFFSTAT-SNAPSHOT-001`.
- `rg -n 'DIRTY-WORKTREE-DIFFSTAT-SNAPSHOT-001|CODEX-HANDOFF-NONFINAL-SAFETY-CHECK-001|LOCAL-RUNTIME-CLEANUP-CHECK-001|GOAL-DRIVER-CONSISTENCY-SCAN-001|BLOCKED-BRANCH-CONTINUATION-POLICY-001' docs/goal_driver/GOAL_PROGRESS.md docs/goal_driver/CODEX_RUN_LEDGER.md`: passed.
- `git diff --check docs/goal_driver/GOAL_PROGRESS.md docs/goal_driver/CODEX_RUN_LEDGER.md`: passed.

### Files Changed
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Goal Driver latest-ticket ordering check passed. No product/source tests were needed because this ticket did not change product code.

### Scope Check
Stayed within Goal Driver ordering verification and records. No product/source/test behavior change, broad historical rewrite, real Abaqus, Docker, PyPI, GitHub Release, pull/merge, commit, or push work was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
DIRTY-WORKTREE-DIFFSTAT-SNAPSHOT-001

### Date
2026-06-04

### Status
Done

### Summary
采集 dirty-worktree 范围快照，便于后续 review/final handoff。tracked diffstat 为 15 files changed, 469 insertions, 282 deletions；untracked file count 为 31；`git status --short` 仍为预期 Goal Chain 工作树。

### Commands
- `git diff --stat`: passed; 15 tracked files changed, 469 insertions, 282 deletions.
- `git ls-files --others --exclude-standard | wc -l`: passed; 31 untracked files.
- `git status --short`: captured expected dirty Goal Chain worktree.
- `git diff --check docs/goal_driver/GOAL_PROGRESS.md docs/goal_driver/CODEX_RUN_LEDGER.md`: passed.

### Files Changed
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Read-only git snapshot commands passed. No product/source tests were needed because this ticket did not change product code.

### Scope Check
Stayed within read-only git snapshot and Goal Driver records. No product/source/test behavior change, cleanup, staging, commit, real Abaqus, Docker, PyPI, GitHub Release, pull/merge, or push work was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
CODEX-HANDOFF-NONFINAL-SAFETY-CHECK-001

### Date
2026-06-04

### Status
Done

### Summary
验证 `CODEX_HANDOFF.md` 在 Goal Chain 仍 active 时保持非最终状态：文件标记为 `Superseded`，说明不是当前最终 handoff，指向 `GOAL_PROGRESS.md` / `CODEX_RUN_LEDGER.md`，并声明不能作为最终完成证据。

### Commands
- `rg -n 'Superseded|not the current final Goal Chain handoff|Do not use this file as final completion evidence|GOAL_PROGRESS|CODEX_RUN_LEDGER' docs/goal_driver/CODEX_HANDOFF.md`: passed.
- `git diff --check docs/goal_driver/CODEX_HANDOFF.md docs/goal_driver/GOAL_PROGRESS.md docs/goal_driver/CODEX_RUN_LEDGER.md`: passed.

### Files Changed
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Non-final handoff safety marker check passed. No final handoff was produced.

### Scope Check
Stayed within Goal Driver handoff/progress/ledger verification. No product/source/test behavior change, final handoff, `update_goal complete`, real Abaqus, Docker, PyPI, GitHub Release, pull/merge, commit, or push work was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
LOCAL-RUNTIME-CLEANUP-CHECK-001

### Date
2026-06-04

### Status
Done

### Summary
检查本地 smoke 后是否有 dev-server/runtime 残留，并刷新 dirty worktree 边界。8000/8002 均无监听进程；`git status --short` 仍为预期 Goal Chain 改动集合。

### Commands
- `lsof -nP -iTCP:8000 -sTCP:LISTEN`: no listener; command exited 1 with no output as expected.
- `lsof -nP -iTCP:8002 -sTCP:LISTEN`: no listener; command exited 1 with no output as expected.
- `git status --short`: captured expected dirty Goal Chain worktree.
- `git diff --check docs/goal_driver/GOAL_PROGRESS.md docs/goal_driver/CODEX_RUN_LEDGER.md`: passed.

### Files Changed
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Local runtime cleanup/status checks passed. No product/source tests were needed because this ticket did not change product code.

### Scope Check
Stayed within local process/status verification and Goal Driver records. No product/source/test behavior change, real Abaqus, Docker, PyPI, GitHub Release, pull/merge, commit, or push work was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
GOAL-DRIVER-CONSISTENCY-SCAN-001

### Date
2026-06-04

### Status
Done

### Summary
扫描当前 Goal Driver surfaces，确认最新本地证据和 blocked-branch 边界一致：262 full pytest baseline、source-only/PyPI unpublished、Docker unavailable、real-Abaqus Environment-limited、blocked branches 不结束整条 Goal Chain。

### Commands
- `rg -n '262 passed|blocked branches|PyPI|Docker|real Abaqus|真实 Abaqus|Environment-limited|source install|not published' docs/goal_driver/CURRENT_STATE.md docs/goal_driver/CAPABILITY_AUDIT.md docs/goal_driver/NEXT_TICKETS.md`: passed.
- `git diff --check docs/goal_driver/GOAL_PROGRESS.md docs/goal_driver/CODEX_RUN_LEDGER.md`: passed.

### Files Changed
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Documentation consistency scan passed. No product/source tests were needed because this ticket changed only Goal Driver progress/ledger records.

### Scope Check
Stayed within Goal Driver read/scan and evidence documentation. No product/source/test behavior change, broad historical rewrite, real Abaqus, Docker, PyPI, GitHub Release, pull/merge, commit, or push work was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
BLOCKED-BRANCH-CONTINUATION-POLICY-001

### Date
2026-06-04

### Status
Done

### Summary
固化用户纠正的 Goal Chain 边界：Docker/PyPI/GitHub Release/真实 Abaqus 是 blocked branches，不是整条 Goal Chain 的 stop condition；预算未到且仍有本地有价值工作时，应记录阻塞分支并继续下一张本地票。

### Commands
- `rg -n 'blocked branches, not whole Goal Chain stop conditions|Docker/PyPI/GitHub Release/真实 Abaqus' docs/goal_driver/GOAL_CHAIN.md docs/goal_driver/NEXT_TICKETS.md docs/goal_driver/CURRENT_STATE.md docs/goal_driver/GOAL_PROGRESS.md`: passed.
- `git diff --check docs/goal_driver/CURRENT_STATE.md docs/goal_driver/GOAL_PROGRESS.md docs/goal_driver/CODEX_RUN_LEDGER.md`: passed.

### Files Changed
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Documentation policy verification passed. No product/source tests were needed because this ticket changed Goal Driver state only.

### Scope Check
Stayed within Goal Driver documentation. No product/source/test behavior change, real Abaqus, Docker, PyPI, GitHub Release, pull/merge, commit, or push work was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
LOCAL-VERIFY-CHECKPOINT-262-001

### Date
2026-06-04

### Status
Done

### Summary
刷新 accumulated Goal Chain dirty-worktree 的完整本地验证检查点。全仓 lint、diff whitespace、full pytest、status 记录均完成；未执行真实 Abaqus、Docker、PyPI 或 GitHub Release。

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `git diff --check`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed; 262 passed, 1 warning.
- `git status --short`: captured expected dirty Goal Chain worktree.
- `git diff --check docs/goal_driver/CURRENT_STATE.md docs/goal_driver/CAPABILITY_AUDIT.md docs/goal_driver/GOAL_PROGRESS.md docs/goal_driver/CODEX_RUN_LEDGER.md`: passed.

### Files Changed
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Full local verification checkpoint passed. The remaining warning is the previously audited external Starlette TestClient/httpx fallback warning.

### Scope Check
Stayed within local verification/evidence documentation. No source behavior change, real Abaqus, Docker, PyPI, GitHub Release, pull/merge, commit, or push work was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
BUILD-COMPARE-REPORT-FOCUSED-REFRESH-001

### Date
2026-06-04

### Status
Done

### Summary
刷新 focused no-Abaqus build/compare/report evidence。build_model custom input/handoff、orchestrator compare_expected、benchmark report fixture tests 均通过；未执行真实 Abaqus。

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_build_model_custom_inp.py tests/test_orchestrator_compare_expected.py tests/test_run_benchmark_report.py`: passed; 9 passed.
- `git diff --check docs/goal_driver/CURRENT_STATE.md docs/goal_driver/CAPABILITY_AUDIT.md docs/goal_driver/GOAL_PROGRESS.md docs/goal_driver/CODEX_RUN_LEDGER.md`: passed.

### Files Changed
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Focused build/compare/report tests passed. No real Abaqus runtime or benchmark report artifact write was used.

### Scope Check
Stayed within focused build/compare/report verification and evidence documentation. No source behavior change, real Abaqus, Docker, PyPI, GitHub Release, pull/merge, commit, or push work was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
RUNNER-KPI-FOCUSED-SMOKE-REFRESH-001

### Date
2026-06-04

### Status
Done

### Summary
刷新 focused no-Abaqus runner/post adapter evidence。syntaxcheck、submit_job、monitor_job、KPI outer subprocess、fake-ODB inner KPI tests 均通过；未执行真实 Abaqus 或 `odbAccess`。

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_syntaxcheck_runner.py tests/test_submit_job_runner.py tests/test_monitor_job.py tests/test_extract_kpis_subprocess.py tests/test_extract_kpis_inner_fake_odb.py`: passed; 39 passed.
- `git diff --check docs/goal_driver/CURRENT_STATE.md docs/goal_driver/CAPABILITY_AUDIT.md docs/goal_driver/GOAL_PROGRESS.md docs/goal_driver/CODEX_RUN_LEDGER.md`: passed.

### Files Changed
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Focused runner/KPI adapter tests passed. No real Abaqus, real ODB, or `odbAccess` runtime was used.

### Scope Check
Stayed within focused runner/KPI verification and evidence documentation. No source behavior change, real Abaqus, Docker, PyPI, GitHub Release, pull/merge, commit, or push work was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
API-MCP-FOCUSED-SMOKE-REFRESH-001

### Date
2026-06-04

### Status
Done

### Summary
刷新 focused no-Abaqus API/MCP smoke evidence。直接 FastAPI smoke、MCP stdio smoke、HTTP-to-MCP bridge real subprocess smoke 均通过；未执行真实 Abaqus。

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_server_api_smoke.py tests/test_mcp_stdio_client.py tests/test_mcp_bridge_real_subprocess.py`: passed; 5 passed, 1 warning.
- `git diff --check docs/goal_driver/CURRENT_STATE.md docs/goal_driver/CAPABILITY_AUDIT.md docs/goal_driver/GOAL_PROGRESS.md docs/goal_driver/CODEX_RUN_LEDGER.md`: passed.

### Files Changed
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Focused direct API, MCP stdio, and bridge subprocess smoke tests passed. Remaining warning is the external Starlette TestClient/httpx fallback previously audited.

### Scope Check
Stayed within focused API/MCP smoke verification and evidence documentation. No source behavior change, real Abaqus, Docker, PyPI, GitHub Release, pull/merge, commit, or push work was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
SCHEMA-ENV-FOCUSED-REFRESH-001

### Date
2026-06-04

### Status
Done

### Summary
刷新 no-Abaqus launch-facing schema/env readiness evidence。运行 focused schema tests 和 local Abaqus environment validator tests，避免 `run_benchmark.py --dry-run` 写入 `reports/` artifacts。未执行真实 Abaqus。

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_schema.py tests/test_validate_abaqus_env.py`: passed; 13 passed.
- `git diff --check docs/goal_driver/CURRENT_STATE.md docs/goal_driver/CAPABILITY_AUDIT.md docs/goal_driver/GOAL_PROGRESS.md docs/goal_driver/CODEX_RUN_LEDGER.md`: passed.

### Files Changed
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Focused schema and environment validator tests passed. No benchmark report artifacts were written.

### Scope Check
Stayed within focused no-Abaqus readiness verification and evidence documentation. No source behavior change, real Abaqus, Docker, PyPI, GitHub Release, pull/merge, commit, or push work was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
FRONTEND-COPY-HTTP-SMOKE-001

### Date
2026-06-04

### Status
Done

### Summary
验证 served frontend HTML 中的 claim-boundary copy。启动本地 `server:app` 于 `127.0.0.1:8000`，HTTP GET `/` 确认新的 syntaxcheck license-boundary copy、deterministic run-id Benchmark note、pre-solver syntaxcheck stage label 已由服务端提供；旧 no-license/license-token 和 all-case idempotency copy 不在响应中。票内启动的 server 已停止。

### Commands
- `lsof -nP -iTCP:8000 -sTCP:LISTEN`: no listener before start.
- `/tmp/abaqus-agent-audit-venv/bin/python -m uvicorn server:app --host 127.0.0.1 --port 8000`: started and later stopped.
- HTTP GET/text check for served `/`: passed; new copy present, stale copy absent.
- `git diff --check docs/goal_driver/CURRENT_STATE.md docs/goal_driver/CAPABILITY_AUDIT.md docs/goal_driver/GOAL_PROGRESS.md docs/goal_driver/CODEX_RUN_LEDGER.md`: passed.

### Files Changed
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Served frontend HTTP smoke passed. This verified the updated static copy is served by the FastAPI app; it did not exercise browser layout, interactions, mobile responsiveness, real Abaqus execution, or commercial license/payment behavior.

### Scope Check
Stayed within served frontend copy verification and evidence documentation. No frontend/source behavior change, real Abaqus, Docker, PyPI, GitHub Release, pull/merge, commit, or push work was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
CLAIM-BOUNDARY-ACTIVE-SURFACE-SCAN-001

### Date
2026-06-04

### Status
Done

### Summary
完成 active-surface stale-claim scan。扫描 README、`RELEASE_INSTRUCTIONS.md`、frontend、agent/core/API/MCP source surfaces、`pyproject.toml`，确认旧定位、旧 PyPI install、旧 stale test count、no-license/no-token、license-safe、all-case idempotency、cached-artifacts claim phrases 在 active surfaces 中无匹配。历史 Goal Driver ledger/progress 中的旧短语保留为审计历史，不作为 active-surface failure。

### Commands
- `rg -n "LLM-powered automation agent|Natural language ->|pip install abaqus-agent|TESTS: 39|单元测试 39|no license consumed|不消耗 license|不消耗 token|license-safe|所有 case 支持幂等|cached artifacts" README.md RELEASE_INSTRUCTIONS.md frontend/index.html agent core server.py mcp_server.py mcp_bridge.py pyproject.toml`: expected no matches; exited 1 with no output.
- `git diff --check docs/goal_driver/CURRENT_STATE.md docs/goal_driver/CAPABILITY_AUDIT.md docs/goal_driver/GOAL_PROGRESS.md docs/goal_driver/CODEX_RUN_LEDGER.md`: passed.

### Files Changed
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Active-surface scan and diff whitespace check passed. Full pytest was not rerun because this scan did not change runtime code or tests after the prior 262-pass verification checkpoint.

### Scope Check
Stayed within claim-boundary scan and evidence documentation. No source behavior change, real Abaqus, Docker, PyPI, GitHub Release, pull/merge, commit, or push work was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
CAPABILITY-AUDIT-7STAGE-RISK-WORDING-001

### Date
2026-06-04

### Status
Done

### Summary
对齐 capability audit 的 7-stage risk wording。Audit 不再写 “README says 7-stage completed”；现在描述 README validation matrix 已把 7-stage real orchestrator 标为 source-supported/mock-covered/environment-limited，并继续区分 API/frontend 6-stage simulated path。未改 README、API、frontend、orchestrator 或 tests。

### Commands
- `rg -n "7-stage completed|7-stage real pipeline|6-stage simulated|validation matrix|API/frontend" docs/goal_driver/CAPABILITY_AUDIT.md docs/goal_driver/CURRENT_STATE.md README.md`: passed.
- `git diff --check docs/goal_driver/CAPABILITY_AUDIT.md docs/goal_driver/CURRENT_STATE.md docs/goal_driver/GOAL_PROGRESS.md docs/goal_driver/CODEX_RUN_LEDGER.md`: passed.

### Files Changed
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Documentation/evidence-boundary ticket. Targeted 7-stage/API-frontend wording search and diff whitespace check passed; full pytest was not rerun because no runtime code or tests changed after the prior 262-pass verification checkpoint.

### Scope Check
Stayed within capability-audit wording and evidence documentation. No README/API/frontend/orchestrator behavior change, real Abaqus, Docker, PyPI, GitHub Release, pull/merge, commit, or push work was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
README-AUDIT-RECOMMENDED-LICENSE-WORDING-001

### Date
2026-06-04

### Status
Done

### Summary
对齐 README next steps 和 capability audit recommended priority 的 real-Abaqus license wording。`license-safe cantilever` 改为 `license-aware minimal-scope cantilever`，避免预设 license 行为；实际 license behavior 仍需真实 Abaqus 环境记录。

### Commands
- `rg -n "license-safe|license-aware minimal-scope|license-aware|actual license|cantilever" README.md docs/goal_driver/CAPABILITY_AUDIT.md docs/goal_driver/CURRENT_STATE.md`: passed.
- `git diff --check README.md docs/goal_driver/CAPABILITY_AUDIT.md docs/goal_driver/CURRENT_STATE.md docs/goal_driver/GOAL_PROGRESS.md docs/goal_driver/CODEX_RUN_LEDGER.md`: passed.

### Files Changed
- `README.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Documentation/evidence-boundary ticket. Targeted license wording search and diff whitespace check passed; full pytest was not rerun because no runtime code or tests changed after the prior 262-pass verification checkpoint.

### Scope Check
Stayed within recommended next-step wording and evidence documentation. No real Abaqus/license check, source behavior change, Docker, PyPI, GitHub Release, pull/merge, commit, or push work was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
NEXT-TICKETS-LICENSE-WORDING-BOUNDARY-001

### Date
2026-06-04

### Status
Done

### Summary
对齐 `NEXT_TICKETS.md` 中真实 Abaqus blocked branch 的 license wording。未来 `ABAQUS-ENV-VALIDATION-001` 不再预设“no-license/minimal-license”行为，而是要求记录 actual license behavior 和 license-aware minimal-scope evidence。未执行真实 Abaqus。

### Commands
- `rg -n "license|license-aware|不消耗|最小消耗|actual license|Blocked Branches|ABAQUS-ENV-VALIDATION" docs/goal_driver/NEXT_TICKETS.md docs/goal_driver/CURRENT_STATE.md docs/goal_driver/CAPABILITY_AUDIT.md`: passed.
- `git diff --check docs/goal_driver/NEXT_TICKETS.md docs/goal_driver/CURRENT_STATE.md docs/goal_driver/CAPABILITY_AUDIT.md docs/goal_driver/GOAL_PROGRESS.md docs/goal_driver/CODEX_RUN_LEDGER.md`: passed.

### Files Changed
- `docs/goal_driver/NEXT_TICKETS.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Documentation/evidence-boundary ticket. Targeted license wording search and diff whitespace check passed; full pytest was not rerun because no runtime code or tests changed after the prior 262-pass verification checkpoint.

### Scope Check
Stayed within blocked-branch wording and evidence documentation. No real Abaqus/license check, source behavior change, Docker, PyPI, GitHub Release, pull/merge, commit, or push work was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
LOCAL-VERIFY-AFTER-CLAIM-BOUNDARY-COPY-001

### Date
2026-06-04

### Status
Done

### Summary
刷新 README/frontend/source claim-boundary wording 变更后的累计本地验证。覆盖全项目 ruff、全量 diff whitespace、当前 dirty status、全量 pytest。未重新安装 editable package，因为没有依赖或 package metadata 改动。

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `git diff --check`: passed.
- `git status --short`: recorded expected dirty Goal Chain worktree.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed; 262 passed, 1 warning.

### Files Changed
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Full-project ruff, diff whitespace check, dirty status capture, and full pytest passed. Remaining warning is the external Starlette TestClient/httpx warning previously audited.

### Scope Check
Verification-only ticket. No source behavior changes, dependency changes, real Abaqus, Docker, PyPI, GitHub Release, pull/merge, commit, or push work was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
RUN-ID-IDEMPOTENCY-COPY-BOUNDARY-001

### Date
2026-06-04

### Status
Done

### Summary
收窄 run-id/idempotency copy。README Design principles 和 frontend Benchmark note 不再声称所有 case 都幂等重跑或会读 cached artifacts；现在明确 spec-based runs 使用 deterministic `sha256(spec)[:16]` run IDs，benchmark dry-run 创建独立记录。未改 `make_run_id`、benchmark run-id 或 cache behavior。

### Commands
- `rg -n "Idempotency|Deterministic|run_id = sha256|sha256\\(spec\\)\\[:16\\]|bench_|幂等|cached artifacts|独立记录" README.md frontend/index.html core/helpers.py server.py mcp_server.py tests/test_core_pipeline.py docs/goal_driver/CAPABILITY_AUDIT.md docs/goal_driver/CURRENT_STATE.md`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_core_pipeline.py`: passed.
- `git diff --check README.md frontend/index.html docs/goal_driver/CURRENT_STATE.md docs/goal_driver/CAPABILITY_AUDIT.md docs/goal_driver/GOAL_PROGRESS.md docs/goal_driver/CODEX_RUN_LEDGER.md`: passed.

### Files Changed
- `README.md`
- `frontend/index.html`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Focused core pipeline tests passed, including deterministic `make_run_id` coverage. Targeted wording/source search and diff whitespace check passed.

### Scope Check
Stayed within run-id/idempotency claim alignment and evidence documentation. No run-id logic, cache behavior, benchmark behavior, real Abaqus, Docker, PyPI, GitHub Release, pull/merge, commit, or push work was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
FRONTEND-SYNTAXCHECK-LICENSE-COPY-ALIGNMENT-001

### Date
2026-06-04

### Status
Done

### Summary
对齐 frontend syntaxcheck/license copy。`frontend/index.html` 的 Benchmark 说明和 simulated pipeline stage label 不再写 syntaxcheck 不消耗 license/token；现在表述为求解前检查，并说明 license 行为需在真实 Abaqus 环境验证。未改 API、pipeline behavior、layout 或 tests。

### Commands
- `rg -n "不消耗 license|license token|求解前检查|syntaxcheck" frontend/index.html docs/goal_driver/CAPABILITY_AUDIT.md docs/goal_driver/CURRENT_STATE.md`: passed.
- `git diff --check frontend/index.html docs/goal_driver/CURRENT_STATE.md docs/goal_driver/CAPABILITY_AUDIT.md docs/goal_driver/GOAL_PROGRESS.md docs/goal_driver/CODEX_RUN_LEDGER.md`: passed.

### Files Changed
- `frontend/index.html`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Frontend copy/evidence-boundary ticket. Targeted wording search and diff whitespace check passed; browser was not rerun because only short static copy changed and no behavior/layout code changed.

### Scope Check
Stayed within frontend syntaxcheck copy alignment and evidence documentation. No API/pipeline behavior change, real Abaqus/license check, Docker, PyPI, GitHub Release, pull/merge, commit, or push work was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
SOURCE-SYNTAXCHECK-LICENSE-COMMENT-ALIGNMENT-001

### Date
2026-06-04

### Status
Done

### Summary
对齐 source-facing syntaxcheck/license wording。`agent/orchestrator.py` stage docstring 和 `core/pipeline.py` simulated stage label 不再写 no-license/no-token；现在使用 pre-solver/check wording。未改 syntaxcheck runtime behavior、API/frontend behavior 或 tests。

### Commands
- `rg -n "no license consumed|不消耗 token|pre-solver|license behavior|syntaxcheck" agent/orchestrator.py core/pipeline.py README.md docs/goal_driver/CAPABILITY_AUDIT.md docs/goal_driver/CURRENT_STATE.md`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check agent/orchestrator.py core/pipeline.py`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_core_pipeline.py tests/test_real_pipeline.py`: passed.
- `git diff --check agent/orchestrator.py core/pipeline.py README.md docs/goal_driver/CURRENT_STATE.md docs/goal_driver/CAPABILITY_AUDIT.md docs/goal_driver/GOAL_PROGRESS.md docs/goal_driver/CODEX_RUN_LEDGER.md`: passed.

### Files Changed
- `agent/orchestrator.py`
- `core/pipeline.py`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Ruff passed for touched source files. Focused core/real pipeline tests passed. Targeted wording search and diff whitespace check passed.

### Scope Check
Stayed within source-facing syntaxcheck claim alignment and evidence documentation. No syntaxcheck runtime behavior change, real Abaqus/license check, Docker, PyPI, GitHub Release, pull/merge, commit, or push work was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
README-API-SIMULATION-PIPELINE-BOUNDARY-001

### Date
2026-06-04

### Status
Done

### Summary
补强 README validation matrix 的 API/frontend 证据边界。FastAPI/frontend 行现在明确：本地 API/SSE/benchmark/premium/frontend smoke 通过 no-Abaqus simulated API/UI path，不是 7-stage real orchestrator、solver 或 ODB evidence。未改 `core/pipeline.py`、API、frontend、orchestrator 或 tests。

### Commands
- `rg -n "6-stage|simulated|7-stage real orchestrator|FastAPI REST API and web frontend|not solver|not 7-stage" README.md docs/goal_driver/CAPABILITY_AUDIT.md docs/goal_driver/CURRENT_STATE.md`: passed.
- `git diff --check README.md docs/goal_driver/CURRENT_STATE.md docs/goal_driver/CAPABILITY_AUDIT.md docs/goal_driver/GOAL_PROGRESS.md docs/goal_driver/CODEX_RUN_LEDGER.md`: passed.

### Files Changed
- `README.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Documentation/evidence-boundary ticket. Targeted API/frontend simulation-vs-real-pipeline search and diff whitespace check passed; full pytest was not rerun because no runtime code or tests changed after the prior 262-pass verification checkpoint.

### Scope Check
Stayed within README validation matrix and evidence documentation. No API/frontend/orchestrator behavior change, real Abaqus, Docker, PyPI, GitHub Release, pull/merge, commit, or push work was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
README-SYNTAXCHECK-LICENSE-CLAIM-ALIGNMENT-001

### Date
2026-06-04

### Status
Done

### Summary
收窄 README syntaxcheck/license wording。README 架构图、Design principles、Project Structure 不再把 `syntaxcheck` 写成 no-license/no-token 已验证事实；现在表述为 pre-solver fail-fast gate，并保留真实 Abaqus/license 行为需要环境验证的边界。未改 `runner/syntaxcheck.py`。

### Commands
- `rg -n "syntaxcheck gate|pre-solver|license behavior|no license consumed|no token consumed" README.md docs/goal_driver/CAPABILITY_AUDIT.md docs/goal_driver/CURRENT_STATE.md`: passed.
- `git diff --check README.md docs/goal_driver/CURRENT_STATE.md docs/goal_driver/CAPABILITY_AUDIT.md docs/goal_driver/GOAL_PROGRESS.md docs/goal_driver/CODEX_RUN_LEDGER.md`: passed.

### Files Changed
- `README.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Documentation/evidence-boundary ticket. Targeted syntaxcheck/license wording search and diff whitespace check passed; full pytest was not rerun because no runtime code or tests changed after the prior 262-pass verification checkpoint.

### Scope Check
Stayed within README syntaxcheck/license claim alignment and evidence documentation. No syntaxcheck behavior change, real Abaqus/license check, Docker, PyPI, GitHub Release, pull/merge, commit, or push work was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
README-SAFETY-CLAIM-ALIGNMENT-001

### Date
2026-06-04

### Status
Done

### Summary
对齐 README Design principles 的 safety wording。原句容易被读成 Static AST guard 会在每条执行路径前自动拦截；现改为 command-tested static guard plus prompt constraints for generated script text，与 `CAPABILITY_AUDIT.md` 已记录的边界一致。未改 guard policy、`build_model` enforcement、测试或依赖。

### Commands
- `rg -n "Static AST guard|automatic enforcement|prompt-generated CAE scripts|Safety \\|" README.md docs/goal_driver/CAPABILITY_AUDIT.md docs/goal_driver/CURRENT_STATE.md`: passed.
- `git diff --check README.md docs/goal_driver/CURRENT_STATE.md docs/goal_driver/CAPABILITY_AUDIT.md docs/goal_driver/GOAL_PROGRESS.md docs/goal_driver/CODEX_RUN_LEDGER.md`: passed.

### Files Changed
- `README.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Documentation/evidence-boundary ticket. Targeted claim-boundary search and diff whitespace check passed; full pytest was not rerun because no runtime code or tests changed after the prior 262-pass verification checkpoint.

### Scope Check
Stayed within README safety claim alignment and evidence documentation. No runtime guard integration, guard policy change, real Abaqus, Docker, PyPI, GitHub Release, pull/merge, commit, or push work was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
LOCAL-VERIFY-AFTER-KPI-MAPPING-FIXES-001

### Date
2026-06-04

### Status
Done

### Summary
刷新累计 KPI mapping/subset/inference 修复后的本地验证。覆盖全项目 ruff、全量 diff whitespace、当前 dirty status、全量 pytest；未重新安装 editable package，因为上一张验证 checkpoint 后没有依赖或 package metadata 改动。

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `git diff --check`: passed.
- `git status --short`: recorded expected dirty Goal Chain worktree.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed; 262 passed, 1 warning.

### Files Changed
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Full-project ruff, diff whitespace check, dirty status capture, and full pytest passed. Remaining warning is the external Starlette TestClient/httpx warning previously audited.

### Scope Check
Verification-only ticket. No source behavior changes, dependency changes, real Abaqus, Docker, PyPI, GitHub Release, pull/merge, commit, or push work was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
EXTRACT-KPIS-EXPLICIT-LOCATION-ALIASES-001

### Date
2026-06-04

### Status
Done

### Summary
对齐 explicit-impact benchmark KPI locations 与生成 set aliases。`post.extract_kpis.py` 新增 `fixed_face -> FIXED_END`、`top_face/load_face -> LOAD_END` aliases，并让 `reaction_force_max` 在取绝对 component max 前应用 location subset。fake ODB tests 覆盖 `RF_Z_MAX`/`fixed_face` 和 `U_Z_MIN`/`top_face` 风格路径。未运行真实 ODB 或 `odbAccess`。

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_extract_kpis_inner_fake_odb.py tests/test_extract_kpis_subprocess.py`: passed; 18 passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check post/extract_kpis.py tests/test_extract_kpis_inner_fake_odb.py`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed; 262 passed, 1 warning.

### Files Changed
- `README.md`
- `post/extract_kpis.py`
- `tests/test_extract_kpis_inner_fake_odb.py`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Focused KPI tests, ruff, and full pytest passed. Remaining warning is the external Starlette TestClient/httpx warning previously audited.

### Scope Check
Stayed within local explicit-impact KPI location alias/subset handling and evidence documentation. No real Abaqus/ODB/odbAccess execution, broad KPI DSL redesign, build_model template rewrite, dependency, release, PyPI, Docker, pull/merge, commit, or push work was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
EXTRACT-KPIS-FIELD-VARIABLE-INFERENCE-001

### Date
2026-06-04

### Status
Done

### Summary
修复 `field_max` 对 displacement component 的默认 field variable 推断。若 KPI 未显式设置 `field_variable` 且 `component` 为 `U1`/`U2`/`U3`，现在默认读取 `U` field，而不是 `S` field；fake ODB test 覆盖 benchmark-style `U_X_MAX`。未运行真实 ODB 或 `odbAccess`。

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_extract_kpis_inner_fake_odb.py tests/test_extract_kpis_subprocess.py`: passed; 16 passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check post/extract_kpis.py tests/test_extract_kpis_inner_fake_odb.py`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed; 260 passed, 1 warning.

### Files Changed
- `README.md`
- `post/extract_kpis.py`
- `tests/test_extract_kpis_inner_fake_odb.py`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Focused KPI tests, ruff, and full pytest passed. Remaining warning is the external Starlette TestClient/httpx warning previously audited.

### Scope Check
Stayed within local field-variable inference and evidence documentation. No real Abaqus/ODB/odbAccess execution, broad KPI DSL redesign, build_model template rewrite, dependency, release, PyPI, Docker, pull/merge, commit, or push work was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
EXTRACT-KPIS-FIELD-LOCATION-SUBSET-001

### Date
2026-06-04

### Status
Done

### Summary
修复 `post.extract_kpis._extract_single_kpi` 中 `field_max`/`field_min` 忽略 `location` 的本地可复现边界。字段 KPI 现在会先按 element set、再按 node set 解析 location，并在命中时对 field 调用 `getSubset()`；fake ODB tests 覆盖 `field_max` 的 `hole_edge_set -> HOLE_EDGE` element subset，以及 `field_min` 的 `tip_center -> TIP_NODES` node subset。未运行真实 ODB 或 `odbAccess`。

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_extract_kpis_inner_fake_odb.py tests/test_extract_kpis_subprocess.py`: passed; 15 passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check post/extract_kpis.py tests/test_extract_kpis_inner_fake_odb.py`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed; 259 passed, 1 warning.

### Files Changed
- `README.md`
- `post/extract_kpis.py`
- `tests/test_extract_kpis_inner_fake_odb.py`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Focused KPI tests, ruff, and full pytest passed. Remaining warning is the external Starlette TestClient/httpx warning previously audited.

### Scope Check
Stayed within local field KPI location-subset resolution and evidence documentation. No real Abaqus/ODB/odbAccess execution, broad KPI DSL redesign, build_model template rewrite, dependency, release, PyPI, Docker, pull/merge, commit, or push work was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
LOCAL-VERIFY-AFTER-KPI-ADAPTERS-001

### Date
2026-06-04

### Status
Done

### Summary
刷新累计 dirty worktree 本地验证。覆盖近期 build_model、syntaxcheck、submit_job、monitor_job、ODB upgrade、KPI extraction 和 Goal Driver 证据文档改动后的 editable install、全项目 ruff、全量 diff whitespace、当前 dirty status、全量 pytest。外部 Docker/PyPI/GitHub Release/真实 Abaqus 仍按 blocked branches 记录，未执行。

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m pip install -e ".[dev]"`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `git diff --check`: passed.
- `git status --short`: recorded expected dirty Goal Chain worktree.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed; 257 passed, 1 warning.

### Files Changed
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Editable install, full-project ruff, diff whitespace check, and full pytest passed. Remaining warning is the external Starlette TestClient/httpx warning previously audited.

### Scope Check
Verification-only ticket. No source behavior changes, dependency changes, real Abaqus, Docker, PyPI, GitHub Release, pull/merge, commit, or push work was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
EXTRACT-KPIS-LOCATION-ALIAS-001

### Date
2026-06-04

### Status
Done

### Summary
修复 `post.extract_kpis._extract_single_kpi` 中 benchmark/spec KPI location 与生成脚本 set 名称的本地可复现错配。新增最小别名解析：`tip_center`/`tip` -> `TIP_NODES`，`hole_edge_set`/`hole_edge` -> `HOLE_EDGE`，`whole_model` -> `ALL`，同时保留原名和大写名查找。fake ODB tests 覆盖 `tip_center -> TIP_NODES` 和 `hole_edge_set -> HOLE_EDGE`。未运行真实 ODB 或 `odbAccess`。

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_extract_kpis_inner_fake_odb.py tests/test_extract_kpis_subprocess.py`: passed; 13 passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check post/extract_kpis.py tests/test_extract_kpis_inner_fake_odb.py`: initially reported import-block formatting; `ruff check --fix` applied mechanical cleanup; subsequent ruff passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed; 257 passed, 1 warning.

### Files Changed
- `README.md`
- `post/extract_kpis.py`
- `tests/test_extract_kpis_inner_fake_odb.py`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Focused KPI tests, ruff, and full pytest passed. Remaining warning is the external Starlette TestClient/httpx warning previously audited.

### Scope Check
Stayed within local KPI location alias resolution and evidence documentation. No real Abaqus/ODB/odbAccess execution, subprocess adapter change, broad KPI DSL redesign, build_model template rewrite, dependency, release, PyPI, Docker, pull/merge, commit, or push work was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
EXTRACT-KPIS-INNER-FAKE-ODB-001

### Date
2026-06-04

### Status
Done

### Summary
为 `post.extract_kpis._extract_single_kpi` 增加纯 Python fake ODB tests。覆盖 nodal displacement subset/component minimum、field max Mises、field min component、reaction-force absolute max、eigenfrequency mode lookup、derived stress concentration element subset，以及 missing-field error。未运行真实 ODB 或 `odbAccess`。

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_extract_kpis_inner_fake_odb.py`: passed; 7 passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check tests/test_extract_kpis_inner_fake_odb.py`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed; 255 passed, 1 warning.

### Files Changed
- `README.md`
- `tests/test_extract_kpis_inner_fake_odb.py`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Focused fake-ODB KPI tests, ruff, and full pytest passed. Remaining warning is the external Starlette TestClient/httpx warning previously audited.

### Scope Check
Stayed within local inner KPI calculation fixture coverage and evidence documentation. No real Abaqus/ODB/odbAccess execution, subprocess adapter change, KPI DSL redesign, dependency, release, PyPI, Docker, pull/merge, commit, or push work was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
UPGRADE-ODB-FAKE-SUBPROCESS-001

### Date
2026-06-04

### Status
Done

### Summary
为 `post.upgrade_odb.upgrade_odb_if_needed` 增加非 Abaqus fake-subprocess tests。覆盖默认/显式 upgraded path、外层 `abaqus python _upgrade_inner.py -- ...` 命令和 capture/timeout 参数、result JSON 读取、missing executable、timeout、无结果文件 stderr fallback，以及 inner script 中的 `odbAccess` upgrade 调用文本。未运行真实 ODB 或 `odbAccess`。

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_upgrade_odb_subprocess.py`: passed; 6 passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check tests/test_upgrade_odb_subprocess.py`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed; 248 passed, 1 warning.

### Files Changed
- `README.md`
- `tests/test_upgrade_odb_subprocess.py`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Focused ODB upgrade subprocess tests, ruff, and full pytest passed. Remaining warning is the external Starlette TestClient/httpx warning previously audited.

### Scope Check
Stayed within local ODB upgrade adapter coverage and evidence documentation. No real Abaqus/ODB/odbAccess execution, extract/orchestrator integration change, dependency, release, PyPI, Docker, pull/merge, commit, or push work was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
MONITOR-JOB-FILE-STATE-FIXTURE-001

### Date
2026-06-04

### Status
Done

### Summary
为 `runner.monitor_job.monitor_job` 增加公开 API 文件状态 fixture tests。覆盖无 job 文件时 pending、`.sta` 进度解析、`.log/.msg` error/warning 去重、completed log 加 `.odb` 时返回 completed 和 `odb_path`、以及 failed `.sta` 状态优先于已存在 `.odb`。未运行真实 Abaqus job，也未重写轮询逻辑。

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_monitor_job.py`: passed; 14 passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check tests/test_monitor_job.py`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed; 242 passed, 1 warning.

### Files Changed
- `README.md`
- `tests/test_monitor_job.py`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Focused monitor_job tests, ruff, and full pytest passed. Remaining warning is the external Starlette TestClient/httpx warning previously audited.

### Scope Check
Stayed within local monitor_job file-state fixture coverage and evidence documentation. No real Abaqus job polling, parser rewrite, dependency, release, PyPI, Docker, pull/merge, commit, or push work was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
EXTRACT-KPIS-FAKE-SUBPROCESS-001

### Date
2026-06-04

### Status
Done

### Summary
为 `post.extract_kpis.extract_kpis` 增加非 Abaqus fake-subprocess tests，覆盖外层 `abaqus python post/extract_kpis.py -- ...` 命令构造、cwd/capture/timeout 参数、`_kpi_spec.json` 写入、`_kpi_result.json` 成功读取、missing executable、timeout、以及无结果文件时的 stderr fallback。未运行真实 Abaqus、真实 ODB 或 `odbAccess`。

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_extract_kpis_subprocess.py`: first run failed once due stray patch marker in the new test file; second run failed due package-level import shadowing; passed after test-file fixes; 4 passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check tests/test_extract_kpis_subprocess.py`: passed after import-order cleanup.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed; 238 passed, 1 warning.

### Files Changed
- `README.md`
- `tests/test_extract_kpis_subprocess.py`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Focused KPI extraction subprocess tests, ruff, and full pytest passed. Remaining warning is the external Starlette TestClient/httpx warning previously audited.

### Scope Check
Stayed within outer KPI subprocess adapter coverage and evidence documentation. No real Abaqus/ODB/odbAccess execution, KPI semantic redesign, dependency, release, PyPI, Docker, pull/merge, commit, or push work was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
SUBMIT-JOB-FAKE-SUBPROCESS-001

### Date
2026-06-04

### Status
Done

### Summary
为 `runner.submit_job.submit_job` 增加非 Abaqus fake-subprocess tests，并修复已有 `lmhanglimit=1` license-queue guard 未传入 subprocess env 的问题。现在 `allow_license_queue=False` 会把 `lmhanglimit=1` 传给 `subprocess.run/Popen`。测试覆盖 interactive command/env/log/meta success、license failure classification、background Popen command/env behavior、以及 missing executable 的结构化 `ABAQUS_NOT_FOUND` 错误。

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_submit_job_runner.py`: passed; 4 passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check runner/submit_job.py tests/test_submit_job_runner.py`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed; 234 passed, 1 warning.

### Files Changed
- `README.md`
- `runner/submit_job.py`
- `tests/test_submit_job_runner.py`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Focused submit_job runner tests, ruff, and full pytest passed. Remaining warning is the external Starlette TestClient/httpx warning previously audited.

### Scope Check
Stayed within submit_job fake-subprocess coverage and license env forwarding. No real Abaqus job submission, monitor/syntaxcheck/extract changes, broad runner rewrite, dependency, release, PyPI, Docker, pull/merge, commit, or push work was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
SYNTAXCHECK-RUNNER-FAKE-SUBPROCESS-001

### Date
2026-06-04

### Status
Done

### Summary
为 `runner.syntaxcheck.syntaxcheck_inp` 增加非 Abaqus fake-subprocess tests，覆盖 `abaqus job=... input=... syntaxcheck interactive` 命令构造、cwd、log 写入、`.dat` warning/error parsing、`ok` 结果行为，以及 missing executable 的结构化 `ABAQUS_NOT_FOUND` 错误。未运行真实 Abaqus syntaxcheck。

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_syntaxcheck_runner.py`: passed; 3 passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check tests/test_syntaxcheck_runner.py`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed; 230 passed, 1 warning.

### Files Changed
- `README.md`
- `tests/test_syntaxcheck_runner.py`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Focused syntaxcheck runner tests, ruff, and full pytest passed. Remaining warning is the external Starlette TestClient/httpx warning previously audited.

### Scope Check
Stayed within syntaxcheck fake-subprocess coverage and documentation updates. No real Abaqus syntaxcheck execution, runner command semantics change, dependency, release, PyPI, Docker, pull/merge, commit, or push work was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
BUILD-MODEL-CUSTOM-INP-MISSING-ERROR-001

### Date
2026-06-04

### Status
Done

### Summary
为 `custom_inp` missing source deck 增加结构化错误处理：`runner/build_model.py` 在 `geometry.inp_path` 不存在时抛出 `AbaqusAgentError(ErrorCode.FILE_NOT_FOUND)`，避免裸 `FileNotFoundError`。测试覆盖 missing-source error，同时保留 custom copy/cache/fake-CAE handoff 覆盖。

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_build_model_custom_inp.py`: passed; 4 passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check runner/build_model.py tests/test_build_model_custom_inp.py`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed; 227 passed, 1 warning.

### Files Changed
- `README.md`
- `runner/build_model.py`
- `tests/test_build_model_custom_inp.py`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Focused build_model tests, ruff, and full pytest passed. Remaining warning is the external Starlette TestClient/httpx warning previously audited.

### Scope Check
Stayed within custom_inp missing-source error handling and documentation updates. No general build_model rewrite, CAE generation semantic change, dependency, release, PyPI, Docker, real Abaqus, pull/merge, commit, or push work was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
LOCAL-VERIFY-AFTER-BUILDMODEL-TESTS-001

### Date
2026-06-04

### Status
Done

### Summary
在 build_model custom_inp 修复、fake-CAE handoff 测试、benchmark report fixture、static guard claim-boundary 等累计改动后，重新执行本地验证 checkpoint。未进行 pull/merge/commit/push，Docker/PyPI/GitHub Release/真实 Abaqus 仍作为 blocked branches，不作为本票或 Goal Chain 的整体停止条件。

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m pip install -e ".[dev]"`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `git diff --check`: passed.
- `git status --short`: recorded dirty Goal Chain worktree.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed; 226 passed, 1 warning.

### Files Changed
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Editable install, full-repo ruff, diff whitespace check, and full pytest passed. Remaining warning is the external Starlette TestClient/httpx warning previously audited.

### Scope Check
Stayed within local verification and checkpoint docs. No source behavior, dependency, release, PyPI, Docker, real Abaqus, pull/merge, commit, or push work was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
BUILD-MODEL-FAKE-CAE-HANDOFF-001

### Date
2026-06-04

### Status
Done

### Summary
为普通 `build_model` generated-script path 增加 fake-CAE handoff test：验证 `build_model_script.py` 写出、`_run_cae_nougui` 收到预期 script/workdir/release、fake runner 写出的 `.inp` 被检测并返回、`cached=False` 保持。该测试验证本地 handoff plumbing，不声称真实 Abaqus script semantics。

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_build_model_custom_inp.py`: passed; 3 passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check tests/test_build_model_custom_inp.py`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed; 226 passed, 1 warning.

### Files Changed
- `README.md`
- `tests/test_build_model_custom_inp.py`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Focused build_model tests, ruff, and full pytest passed. Remaining warning is the external Starlette TestClient/httpx warning previously audited.

### Scope Check
Stayed within generated-script handoff test coverage and documentation updates. No build_model behavior change, real Abaqus execution, syntaxcheck/submit/monitor/extract behavior, dependency, release, PyPI, Docker, pull/merge, commit, or push work was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
BUILD-MODEL-CUSTOM-INP-NO-CAE-001

### Date
2026-06-04

### Status
Done

### Summary
修复 `runner/build_model.py` 的 `custom_inp` 路径：当 `_write_cae_script` 已复制出非空目标 `.inp` 时，`build_model` 直接返回，不再调用 `_run_cae_nougui`。这让 README/source 中的 “custom_inp copy existing .inp directly” 成为本地可验证路径。新增测试覆盖 custom `.inp` copy/no-CAE、custom script marker、`cached=False`、以及既有 cached `.inp` skip behavior。

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_build_model_custom_inp.py`: initially failed; 2 failed due test import resolving to package-level `runner.build_model` function instead of module.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check runner/build_model.py tests/test_build_model_custom_inp.py`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_build_model_custom_inp.py`: passed after import fix; 2 passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check runner/build_model.py tests/test_build_model_custom_inp.py`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed; 225 passed, 1 warning.

### Files Changed
- `README.md`
- `runner/build_model.py`
- `tests/test_build_model_custom_inp.py`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Focused custom_inp tests, ruff, and full pytest passed. Remaining warning is the external Starlette TestClient/httpx warning previously audited.

### Scope Check
Stayed within custom_inp no-CAE behavior and documentation updates. No general CAE generation rewrite, syntaxcheck/submit/monitor/extract behavior, dependency, release, PyPI, Docker, real Abaqus, pull/merge, commit, or push work was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
BENCHMARK-REPORT-FIXTURE-001

### Date
2026-06-04

### Status
Done

### Summary
为 `run_benchmark.generate_report` 新增非 Abaqus fixture tests，覆盖 benchmark Markdown report 的 summary counts、KPI rendering、PASS/FAIL regression labels、KPI comparison table、error details 和 suggestions。Report rendering 现在有本地命令验证；真实 benchmark solver/KPI/regression 仍需 Abaqus 环境。

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_run_benchmark_report.py`: passed; 2 passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check tests/test_run_benchmark_report.py`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed; 223 passed, 1 warning.

### Files Changed
- `README.md`
- `tests/test_run_benchmark_report.py`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Focused benchmark report fixture tests, ruff, and full pytest passed. Remaining warning is the external Starlette TestClient/httpx warning previously audited.

### Scope Check
Stayed within benchmark report fixture verification and documentation updates. No benchmark runner behavior, persistent report artifacts, dependency, release, PyPI, Docker, real Abaqus, pull/merge, commit, or push work was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
STATIC-GUARD-CLAIM-BOUNDARY-001

### Date
2026-06-04

### Status
Done

### Summary
修正 static guard 的发布面 claim：README 不再声称所有 LLM-generated scripts 自动经过 static guard。当前证据边界是 `tools/static_guard.py` 与 `tests/test_static_guard.py` 已命令/测试验证，`prompts/script_generator.txt` 有 guard constraints，但自动 enforcement across every generated script path 未证明；`runner/build_model.py` 也未调用 `check_script`，且其模板包含当前 guard 会阻断的 `import os`。本票不改变 guard policy 或 build behavior。

### Commands
- Targeted source audit with `rg` over README/docs/prompts/tests/runner/tools: passed; old overbroad claim located and replacement boundary verified.
- `git diff --check README.md docs/goal_driver/CURRENT_STATE.md docs/goal_driver/CAPABILITY_AUDIT.md docs/goal_driver/GOAL_PROGRESS.md docs/goal_driver/CODEX_RUN_LEDGER.md`: passed.

### Files Changed
- `README.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
No full pytest required for this documentation-only claim-boundary ticket. Previous full pytest in the prior ticket passed with 221 passed / 1 warning.

### Scope Check
Stayed within safety claim documentation and audit boundary. No static guard policy, build_model/script generation behavior, dependency, release, PyPI, Docker, real Abaqus, pull/merge, commit, or push work was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
ORCHESTRATOR-COMPARE-EXPECTED-FIXTURE-001

### Date
2026-06-04

### Status
Done

### Summary
为 `AbaqusOrchestrator._stage_compare` 新增非 Abaqus fixture tests，覆盖 expected KPI regression compare 的 PASS/FAIL/MISSING/INFO 分支、result shape 和 `compare_kpis` progress callback。`compare_expected` 现在有本地命令验证；真实 ODB KPI 提取值上的 compare 仍需 Abaqus 环境。

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_orchestrator_compare_expected.py`: passed; 3 passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check tests/test_orchestrator_compare_expected.py`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed; 221 passed, 1 warning.

### Files Changed
- `README.md`
- `tests/test_orchestrator_compare_expected.py`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Focused compare fixture tests, ruff, and full pytest passed. Remaining warning is the external Starlette TestClient/httpx warning previously audited.

### Scope Check
Stayed within compare_expected fixture verification and documentation updates. No solver/build/extract behavior, broad orchestrator refactor, dependency, release, PyPI, Docker, real Abaqus, pull/merge, commit, or push work was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
FRONTEND-SETTINGS-PREMIUM-BROWSER-SMOKE-001

### Date
2026-06-04

### Status
Done

### Summary
将 Frontend Settings/Premium 从 source-audited 提升为本地 browser-smoke verified。由于本机 8001 被另一个 `api:app` 占用，本票使用 direct API `127.0.0.1:8000` 和 MCP bridge `127.0.0.1:8002/mcp`。浏览器实际保存 direct/MCP URL，验证 MCP bridge 连接，分别通过 direct 和 MCP UI path 使用 dev key 激活 premium，并确认五个 premium features 显示 ENABLED。未声称真实商业 license/payment 或真实 Abaqus 验证。

### Commands
- `curl -fsS http://127.0.0.1:8000/health`: passed; direct API healthy with 4 cases and `abaqus_available=false`.
- `curl -fsS http://127.0.0.1:8002/mcp/health`: passed; MCP bridge healthy with `transport=mcp`.
- `curl -fsS http://127.0.0.1:8000/api/premium/features`: passed; five premium features returned disabled before activation.
- `curl -fsS http://127.0.0.1:8002/mcp/api/premium/features`: passed; five premium features returned disabled before activation.
- Browser Settings/Premium direct smoke: passed; saved `http://127.0.0.1:8000`, activated `dev-browser-smoke`, Premium badge became `已配置`, and all five features showed `ENABLED`.
- Browser Settings/Premium MCP smoke: passed; saved `http://127.0.0.1:8002/mcp`, MCP connection toast showed `MCP Bridge 连接成功: ok · transport: mcp`, activated `dev-mcp-browser-smoke`, and all five features showed `ENABLED`.
- `curl -fsS -X POST 'http://127.0.0.1:8002/mcp/api/premium/activate?license_key='`: passed; returned `valid=false` and `No license key provided`.
- Browser console errors: none.
- Screenshot saved: `/tmp/abaqus-agent-settings-premium-mcp-smoke.png`.

### Files Changed
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/NEXT_TICKETS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Browser UI smoke plus HTTP probes passed. Full pytest was already refreshed in `LOCAL-VERIFY-AFTER-METADATA-AND-LLM-001`; this ticket did not change product source.

### Scope Check
Stayed within frontend browser verification and checkpoint docs. No frontend redesign, endpoint contract, dependency, release, PyPI, Docker, real Abaqus, pull/merge, commit, or push work was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
LOCAL-VERIFY-AFTER-METADATA-AND-LLM-001

### Date
2026-06-04

### Status
Done

### Summary
在累计 LLM provider mock smoke、request-model hardening、FastAPI metadata、MCP bridge metadata 等改动后，重新执行本地验证 checkpoint。未进行 pull/merge/commit/push，Docker/PyPI/GitHub Release/真实 Abaqus 仍作为 blocked branches，不作为本票或 Goal Chain 的整体停止条件。

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m pip install -e ".[dev]"`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `git diff --check`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed; 218 passed, 1 warning.
- `git status --short`: recorded dirty Goal Chain worktree.

### Files Changed
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Editable install, ruff, diff whitespace check, and full pytest passed. Remaining warning is the external Starlette TestClient/httpx warning previously audited.

### Scope Check
Stayed within local verification and checkpoint docs. No product source behavior, dependency, release, PyPI, Docker, real Abaqus, pull/merge, commit, or push work was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
MCP-BRIDGE-POSITIONING-METADATA-001

### Date
2026-06-04

### Status
Done

### Summary
将 `mcp_bridge.py` FastAPI app description 从泛化 `HTTP/SSE bridge to MCP server for browser access` 改为 browser-facing Local Simulation QA evidence workflow bridge，明确 dry-run/mock-real/real-runtime boundaries。Bridge metadata 现在与 direct API、MCP server、README/package 定位一致。

### Commands
- `rg -n 'HTTP/SSE bridge to MCP server for browser access|HTTP/SSE bridge to the Abaqus Agent MCP server|Local Simulation QA|dry-run/mock-real/real-runtime' mcp_bridge.py server.py mcp_server.py`: passed; old bridge description absent and new positioning present.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_mcp_bridge.py tests/test_mcp_bridge_real_subprocess.py`: passed; 18 passed, 1 warning.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check mcp_bridge.py`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed; 218 passed, 1 warning.
- Re-read changed `mcp_bridge.py`.

### Files Changed
- `mcp_bridge.py`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Focused bridge tests, ruff, and full pytest passed. Remaining warning is the external Starlette TestClient/httpx warning.

### Scope Check
Stayed within bridge metadata positioning. No endpoint contract, bridge/runtime behavior, dependency, release, PyPI, Docker, real Abaqus, pull/merge, commit, or push work was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
PYDANTIC-RUNNER-CFG-DEFAULT-FACTORY-001

### Date
2026-06-04

### Status
Done

### Summary
将 direct FastAPI 和 HTTP-to-MCP bridge 的 `StartRunRequest.runner_cfg` 从 mutable `{}` defaults 改为 `Field(default_factory=dict)`，并在现有 API/bridge smoke tests 中验证不同 request 实例不会共享 `runner_cfg` 状态。API contract 未变。

### Commands
- `rg -n 'runner_cfg: dict = \{\}|Field\(default_factory=dict\)|BaseModel, Field|runner_cfg\["cpus"\]' server.py mcp_bridge.py tests/test_server_api_smoke.py tests/test_mcp_bridge.py`: passed; mutable defaults absent and default factories/tests present.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_server_api_smoke.py tests/test_mcp_bridge.py`: passed; 20 passed, 1 warning.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check server.py mcp_bridge.py tests/test_server_api_smoke.py tests/test_mcp_bridge.py`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed; 218 passed, 1 warning.
- Re-read changed `server.py`, `mcp_bridge.py`, `tests/test_server_api_smoke.py`, and `tests/test_mcp_bridge.py`.

### Files Changed
- `server.py`
- `mcp_bridge.py`
- `tests/test_server_api_smoke.py`
- `tests/test_mcp_bridge.py`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Focused API/bridge tests, ruff, and full pytest passed. Remaining warning is the external Starlette TestClient/httpx warning.

### Scope Check
Stayed within request model default hardening. No API contract, route/runtime behavior redesign, dependency, release, PyPI, Docker, real Abaqus, pull/merge, commit, or push work was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
FASTAPI-SERVER-POSITIONING-METADATA-001

### Date
2026-06-04

### Status
Done

### Summary
将 `server.py` FastAPI app description 从旧 `LLM-powered Abaqus FEA automation agent` 定位改为 Local Simulation QA / regression framework，明确 validate specs、local evidence workflows、benchmark cases，以及 dry-run/mock-real/real-runtime boundaries。Direct FastAPI metadata 现在与 `mcp_server.py` 和 README/package 定位一致。

### Commands
- `rg -n 'LLM-powered Abaqus FEA automation agent|Local Simulation QA and regression framework|dry-run/mock-real/real-runtime' server.py mcp_server.py README.md pyproject.toml`: passed; old server/MCP metadata wording absent and new wording present.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_server_api_smoke.py`: passed; 3 passed, 1 warning.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check server.py`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed; 218 passed, 1 warning.
- Re-read changed `server.py`.

### Files Changed
- `server.py`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Focused API smoke, ruff, and full pytest passed. Remaining warning is the external Starlette TestClient/httpx warning.

### Scope Check
Stayed within FastAPI metadata positioning. No API contract, route/runtime behavior, dependency, release, PyPI, Docker, real Abaqus, pull/merge, commit, or push work was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
LLM-PLANNER-PROVIDER-MOCK-SMOKE-001

### Date
2026-06-04

### Status
Done

### Summary
新增本地 LLM provider adapter mock smoke。`tests/test_llm_planner_provider_mock.py` 伪造 OpenAI/Anthropic SDK 模块和响应对象，验证 OpenAI message content extraction、Anthropic text content extraction，以及 `generate_spec_async` 使用临时 OpenAI key 后恢复原环境变量。未安装 provider SDK、未使用真实 API key、未发网络请求。Full pytest 现在为 218 passed / 1 warning。

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_llm_planner_provider_mock.py`: passed; 3 passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check tests/test_llm_planner_provider_mock.py`: first run failed once due import ordering.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check tests/test_llm_planner_provider_mock.py`: passed after import-order fix.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed; 218 passed, 1 warning.
- Re-read changed `tests/test_llm_planner_provider_mock.py`.

### Files Changed
- `tests/test_llm_planner_provider_mock.py`
- `README.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Focused provider mock test, ruff, and full pytest passed after one import-order fix. Remaining warning is the external Starlette TestClient/httpx warning.

### Scope Check
Stayed within local provider adapter mock coverage. No real API keys, network calls, provider dependency installs/upgrades, provider model changes, release, PyPI, Docker, real Abaqus, pull/merge, commit, or push work was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
FRONTEND-SETTINGS-PREMIUM-STATIC-AUDIT-001

### Date
2026-06-04

### Status
Done

### Summary
静态审计 frontend Settings/Premium 路径。`frontend/index.html` 使用 `abaqus_agent_settings` localStorage，按 `transport` 在 direct API 和 MCP `/mcp` API base 间切换；MCP health 使用 `/mcp/health`；premium feature loading 和 activation 使用 `${API}/api/premium/...`，因此 direct 模式落到 `/api/premium/...`，MCP 模式落到 `/mcp/api/premium/...`；激活成功后 license key 写回 localStorage。结论：Settings/Premium 路径 source-supported，但未做浏览器点击、MCP frontend flow 或 mobile/responsive 验证。

### Commands
- `sed -n '1490,1625p' frontend/index.html`: inspected settings/localStorage/API base setup.
- `sed -n '2490,2725p' frontend/index.html`: inspected settings initialization, save, server/MCP tests, premium activation, and premium feature loading.
- `sed -n '2725,2795p' frontend/index.html`: inspected health check and benchmark loading API path behavior.
- `rg -n 'function api\\(|const API|MCP|transport|mcpServerUrl|licenseKey|activatePremium|loadPremiumFeatures|premium/features|premium/activate|localStorage|settings' frontend/index.html`: relevant paths found.

### Files Changed
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/NEXT_TICKETS.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Static audit only. No browser-click verification was performed or claimed.

### Scope Check
Stayed within frontend source audit and documentation. No frontend behavior change, browser automation claim, source runtime change, release, PyPI, Docker, real Abaqus, pull/merge, commit, or push work was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
TESTCLIENT-HTTPX-WARNING-AUDIT-001

### Date
2026-06-04

### Status
Done

### Summary
审计剩余 FastAPI TestClient/httpx warning。当前 audit venv 中 FastAPI 0.136.3、Starlette 1.2.1、httpx 0.28.1，`httpx2` 未安装。Installed `starlette.testclient` 会先 import `httpx2`，缺失时 fallback 到 `httpx` 并发出 `StarletteDeprecationWarning`；该 warning 继承 `UserWarning`，不是 `DeprecationWarning`。结论：这是外部 Starlette TestClient/httpx compatibility warning，不是项目业务/runtime code warning。本票未改依赖。

### Commands
- Local package version inspection: FastAPI 0.136.3, Starlette 1.2.1, httpx 0.28.1, mcp 1.27.2, abaqus-agent 0.1.0.
- `httpx2` package inspection: not installed.
- Installed `fastapi/testclient.py` and `starlette/testclient.py` re-read: warning source confirmed at missing-`httpx2` fallback.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_server_api_smoke.py -W error::DeprecationWarning`: passed with the same Starlette warning, confirming it is not a `DeprecationWarning` subclass.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_mcp_bridge_real_subprocess.py tests/test_server_api_smoke.py -W error::starlette.exceptions.StarletteDeprecationWarning`: expected failure at TestClient import, confirming warning source.

### Files Changed
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/NEXT_TICKETS.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Audit commands completed. The `-W error::StarletteDeprecationWarning` probe intentionally failed at collection to prove the warning source; no dependency or warning filter was changed.

### Scope Check
Stayed within local warning audit and documentation. No dependency upgrade, warning suppression, source/test runtime behavior change, release, PyPI, Docker, real Abaqus, pull/merge, commit, or push work was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
LOCAL-VERIFY-DIRTY-WORKTREE-001

### Date
2026-06-04

### Status
Done

### Summary
对累计 dirty worktree 做完整本地验证。Editable install、full-project ruff、full `git diff --check`、full pytest 均通过；`git status --short` 已捕获当前 modified/untracked 边界。外部 Docker、真实 Abaqus、GitHub Release、PyPI、pull/merge/commit/push 均未执行。

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m pip install -e ".[dev]"`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `git diff --check`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed; 215 passed, 1 warning.
- `git status --short`: captured dirty worktree.

### Files Changed
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Full local verification passed. Remaining warning is the external FastAPI TestClient/httpx warning.

### Scope Check
Verification and checkpoint update only. No source/test/runtime fix, final handoff, `update_goal complete`, release, PyPI, Docker, real Abaqus, pull/merge, commit, or push work was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
NEXT-TICKETS-BLOCKED-BRANCH-SEMANTICS-001

### Date
2026-06-04

### Status
Done

### Summary
更新 `NEXT_TICKETS.md` 队列语义：本地可执行候选现在位于 `Ready Local`，真实 Abaqus、Docker、GitHub Release、PyPI、pull/merge、版本控制确认等外部或用户决策路径位于 `Blocked Branches`。文件明确 blocked branches 不是整个 Goal Chain stop condition；如果未到预算且还有有价值本地工作，应继续下一张本地票。

### Commands
- `rg -n 'Ready Local|Blocked Branches|not whole Goal Chain stop conditions|keep executing the next local ticket|ABAQUS-ENV-VALIDATION|Docker compose|GitHub Release|PyPI|LOCAL-VERIFY-DIRTY-WORKTREE|TESTCLIENT-HTTPX-WARNING|FRONTEND-SETTINGS-PREMIUM' docs/goal_driver/NEXT_TICKETS.md docs/goal_driver/GOAL_PROGRESS.md`: passed.
- `git diff --check docs/goal_driver/NEXT_TICKETS.md docs/goal_driver/GOAL_PROGRESS.md docs/goal_driver/CODEX_RUN_LEDGER.md`: passed.
- Re-read changed `docs/goal_driver/NEXT_TICKETS.md`.

### Files Changed
- `docs/goal_driver/NEXT_TICKETS.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Documentation checkpoint only. Targeted search and `git diff --check` passed.

### Scope Check
Stayed within Goal Driver queue semantics. No source/test/runtime changes, final handoff, `update_goal complete`, release, PyPI, Docker, real Abaqus, pull/merge, commit, or push work was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
FASTAPI-RUN-START-SSE-SMOKE-001

### Date
2026-06-04

### Status
Done

### Summary
扩展 direct FastAPI REST/SSE smoke，覆盖 `/api/run/start` 到 `/api/run/{run_id}/stream` 的 no-Abaqus simulated pipeline。测试验证 run registration，并消费 SSE 到 `done`；不声称真实 Abaqus solver/background run 验证。

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_server_api_smoke.py`: passed; 3 passed, 1 warning.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check tests/test_server_api_smoke.py`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed; 215 passed, 1 warning.
- Re-read changed `tests/test_server_api_smoke.py`.

### Files Changed
- `tests/test_server_api_smoke.py`
- `README.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Focused API smoke, ruff, and full pytest passed. Remaining warning is the external FastAPI TestClient/httpx warning.

### Scope Check
Stayed within local direct API run start/SSE evidence coverage. No pipeline implementation rewrite, real Abaqus execution, frontend/browser automation, release, PyPI, Docker, pull/merge, commit, or push work was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
FASTAPI-BENCHMARK-RUN-SMOKE-001

### Date
2026-06-04

### Status
Done

### Summary
扩展 direct FastAPI REST smoke，覆盖 `/api/benchmark/run?dry_run=true`。测试验证 benchmark run id、dry-run flag、public case names 和 `RUNS` registration；不声称真实 Abaqus benchmark/solver/KPI 验证。

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_server_api_smoke.py`: passed; 3 passed, 1 warning.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check tests/test_server_api_smoke.py`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed; 215 passed, 1 warning.
- Re-read changed `tests/test_server_api_smoke.py`.

### Files Changed
- `tests/test_server_api_smoke.py`
- `README.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Focused API smoke, ruff, and full pytest passed. Remaining warning is the external FastAPI TestClient/httpx warning.

### Scope Check
Stayed within local direct API benchmark dry-run evidence coverage. No benchmark implementation rewrite, real Abaqus benchmark execution, frontend/browser automation, release, PyPI, Docker, pull/merge, commit, or push work was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
MCP-STDIO-BENCHMARK-RUN-SMOKE-001

### Date
2026-06-04

### Status
Done

### Summary
扩展真实 MCP stdio client smoke，覆盖 `run_benchmark_tool(dry_run=True)`。测试通过真实 `mcp_server.py` subprocess 和 MCP stdio transport，验证 benchmark dry-run trigger 返回 benchmark run id、dry-run flag 和 public case names；不声称真实 Abaqus benchmark/solver/KPI 验证。

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_mcp_stdio_client.py`: passed; 1 passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_mcp_server.py tests/test_mcp_stdio_client.py`: passed; 22 passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check tests/test_mcp_stdio_client.py`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed; 215 passed, 1 warning.
- Re-read changed `tests/test_mcp_stdio_client.py`.

### Files Changed
- `tests/test_mcp_stdio_client.py`
- `README.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Focused stdio smoke, MCP focused suite, ruff, and full pytest passed. Remaining warning is the external FastAPI TestClient/httpx warning.

### Scope Check
Stayed within local MCP stdio benchmark dry-run evidence coverage. No benchmark implementation rewrite, MCP protocol redesign, real Abaqus benchmark execution, frontend/browser automation, release, PyPI, Docker, pull/merge, commit, or push work was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
MCP-BRIDGE-BENCHMARK-RUN-SUBPROCESS-SMOKE-001

### Date
2026-06-04

### Status
Done

### Summary
扩展真实 HTTP-to-MCP bridge subprocess smoke，覆盖 `/mcp/api/benchmark/run?dry_run=true`。测试通过真实 `MCPConnection` 子进程路由到 `mcp_server.py`，验证 benchmark dry-run trigger 返回 benchmark run id、dry-run flag 和 public case names；不声称真实 Abaqus benchmark/solver/KPI 验证。

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_mcp_bridge_real_subprocess.py`: first run failed once because the test expected case dicts while `run_benchmark_tool` returns case-name strings.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_mcp_bridge_real_subprocess.py`: passed after assertion fix; 1 passed, 1 warning.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_mcp_bridge.py tests/test_mcp_bridge_real_subprocess.py`: passed; 18 passed, 1 warning.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check tests/test_mcp_bridge_real_subprocess.py`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed; 215 passed, 1 warning.
- Re-read changed `tests/test_mcp_bridge_real_subprocess.py`.

### Files Changed
- `tests/test_mcp_bridge_real_subprocess.py`
- `README.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Focused real bridge subprocess test, bridge suite, ruff, and full pytest passed after one assertion-shape correction. Remaining warning is the external FastAPI TestClient/httpx warning.

### Scope Check
Stayed within local bridge benchmark dry-run evidence coverage. No benchmark implementation rewrite, real Abaqus benchmark execution, frontend/browser automation, release, PyPI, Docker, pull/merge, commit, or push work was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
MCP-STDIO-PREMIUM-SMOKE-001

### Date
2026-06-04

### Status
Done

### Summary
扩展真实 MCP stdio client smoke，覆盖 premium tool listing、`get_premium_features`、空 license activation failure、`dev-stdio-smoke` activation success，以及 `premium://features` resource。该测试通过真实 `mcp_server.py` subprocess 和 MCP stdio transport，补齐 AI-agent 集成入口的 premium evidence；不声称真实商业授权、支付/license policy 或真实 Abaqus 执行验证。

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_mcp_stdio_client.py`: passed; 1 passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_mcp_server.py tests/test_mcp_stdio_client.py`: passed; 22 passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check tests/test_mcp_stdio_client.py`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed; 215 passed, 1 warning.
- Re-read changed `tests/test_mcp_stdio_client.py`.

### Files Changed
- `tests/test_mcp_stdio_client.py`
- `README.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Focused stdio smoke, MCP focused suite, ruff, and full pytest passed. Remaining warning is the external FastAPI TestClient/httpx warning.

### Scope Check
Stayed within local MCP stdio premium evidence coverage. No MCP protocol redesign, premium licensing/product policy change, external credentials, frontend/browser automation, release, PyPI, Docker, real Abaqus, pull/merge, commit, or push work was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
MCP-BRIDGE-PREMIUM-SUBPROCESS-SMOKE-001

### Date
2026-06-04

### Status
Done

### Summary
扩展真实 HTTP-to-MCP bridge subprocess smoke，覆盖 premium feature status、空 license activation failure、`dev-bridge-smoke` activation success。该测试通过真实 `MCPConnection` 子进程路由到 `mcp_server.py`，验证 bridge premium endpoint routing；不声称真实商业授权、支付/license policy 或真实 Abaqus 执行验证。

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_mcp_bridge_real_subprocess.py`: passed; 1 passed, 1 warning.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_mcp_bridge.py tests/test_mcp_bridge_real_subprocess.py`: passed; 18 passed, 1 warning.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check tests/test_mcp_bridge_real_subprocess.py`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed; 215 passed, 1 warning.
- Re-read changed `tests/test_mcp_bridge_real_subprocess.py`.

### Files Changed
- `tests/test_mcp_bridge_real_subprocess.py`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Focused real bridge subprocess test, bridge suite, ruff, and full pytest passed. Remaining warning is the external FastAPI TestClient/httpx warning.

### Scope Check
Stayed within local bridge premium endpoint evidence coverage. No premium licensing redesign, commercial license/payment integration, frontend/browser automation, release, PyPI, Docker, real Abaqus, pull/merge, commit, or push work was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
MCP-SERVER-TEST-TASK-CLEANUP-001

### Date
2026-06-04

### Status
Done

### Summary
清理 direct MCP server tests 的 pending background task notices。`tests/test_mcp_server.py` 新增 autouse fixture，在每个测试后 drain pending asyncio tasks，并清理 MCP `RUNS`、progress queues、premium `feature_gate`。Focused MCP tests 不再输出 `Task was destroyed but it is pending!`，full pytest 仍通过。

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_mcp_server.py tests/test_mcp_stdio_client.py`: passed; 22 passed with no pending task notices.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check tests/test_mcp_server.py`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed; 215 passed, 1 warning.
- `git diff --check tests/test_mcp_server.py docs/goal_driver/CURRENT_STATE.md docs/goal_driver/GOAL_PROGRESS.md docs/goal_driver/CODEX_RUN_LEDGER.md`: passed.
- Re-read changed `tests/test_mcp_server.py`.

### Files Changed
- `tests/test_mcp_server.py`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Focused MCP tests, ruff, and full pytest passed. Remaining warning is the external FastAPI TestClient/httpx warning.

### Scope Check
Changed test cleanup only. No runtime MCP server behavior, protocol, frontend/browser, release, PyPI, Docker, real Abaqus, pull/merge, commit, or push work was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
MCP-SERVER-POSITIONING-METADATA-001

### Date
2026-06-04

### Status
Done

### Summary
将 `mcp_server.py` FastMCP instructions 从旧 `LLM-powered Abaqus FEA automation agent` 定位改为 Local Simulation QA / regression framework，明确 validate specs、local evidence workflows、benchmark cases，以及 dry-run/mock-real/real-runtime boundaries。MCP focused tests 和 full pytest 均通过。

### Commands
- node_repl Playwright availability check: failed with `Module not found: playwright`; frontend Settings/Premium browser automation branch recorded as tool-limited, not a full-chain stop.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_mcp_server.py tests/test_mcp_stdio_client.py`: passed; 22 passed. Existing direct `start_run` tests still print pending task notices.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check mcp_server.py tests/test_mcp_server.py tests/test_mcp_stdio_client.py`: passed.
- `rg -n 'LLM-powered Abaqus FEA automation agent|Local Simulation QA and regression framework|dry-run/mock-real/real-runtime' mcp_server.py`: passed; old instructions absent and new instructions present.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed; 215 passed, 1 warning.
- `git diff --check mcp_server.py docs/goal_driver/GOAL_PROGRESS.md docs/goal_driver/CODEX_RUN_LEDGER.md docs/goal_driver/CURRENT_STATE.md`: passed.

### Files Changed
- `mcp_server.py`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
MCP focused tests, ruff, and full pytest passed. Remaining warning is the external FastAPI TestClient/httpx warning.

### Scope Check
Stayed within MCP metadata positioning. No MCP tool contract, protocol, frontend/browser, release, PyPI, Docker, real Abaqus, pull/merge, commit, or push work was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
FASTAPI-PREMIUM-API-SMOKE-001

### Date
2026-06-04

### Status
Done

### Summary
扩展 FastAPI API smoke 覆盖到 Settings/Premium 所依赖的 premium endpoints。`tests/test_server_api_smoke.py` 现在验证 `/api/premium/features`、空 license activation failure、`dev-api-smoke` activation success，并在 fixture 中重置 premium `feature_gate`，避免全局状态污染。Full pytest 现在为 215 passed / 1 warning。

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_server_api_smoke.py`: passed; 3 passed, 1 warning.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check tests/test_server_api_smoke.py`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed; 215 passed, 1 warning.
- `rg -n '215 passing|215 passed|premium endpoint|premium smoke|REST/SSE/premium|api/premium/features|api/premium/activate|FastAPI REST API with SSE and premium endpoints' README.md docs/goal_driver/CURRENT_STATE.md docs/goal_driver/CAPABILITY_AUDIT.md tests/test_server_api_smoke.py`: passed.
- `git diff --check README.md tests/test_server_api_smoke.py docs/goal_driver/CURRENT_STATE.md docs/goal_driver/CAPABILITY_AUDIT.md docs/goal_driver/GOAL_PROGRESS.md docs/goal_driver/CODEX_RUN_LEDGER.md`: passed.

### Files Changed
- `tests/test_server_api_smoke.py`
- `README.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Focused API smoke, ruff, and full pytest passed. Remaining warning is the external FastAPI TestClient/httpx warning.

### Scope Check
Stayed within local FastAPI premium endpoint smoke coverage. No premium licensing redesign, frontend/browser automation, secrets, payment/license integration, release, PyPI, Docker, real Abaqus, pull/merge, commit, or push work was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
MCP-BRIDGE-REAL-SSE-SMOKE-001

### Date
2026-06-04

### Status
Done

### Summary
扩展真实 HTTP-to-MCP bridge subprocess smoke：测试现在通过真实 `MCPConnection` 子进程启动 no-Abaqus simulated run，并消费 `/mcp/api/run/{run_id}/stream` SSE 到 `done`。这关闭了本地可验证的 bridge SSE evidence gap，同时不声称真实 Abaqus solver/background run。

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_mcp_bridge_real_subprocess.py`: passed; 1 passed, 1 warning.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check tests/test_mcp_bridge_real_subprocess.py`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_mcp_bridge.py tests/test_mcp_bridge_real_subprocess.py`: passed; 18 passed, 1 warning.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed; 214 passed, 1 warning.
- `rg -n 'MCP-BRIDGE-REAL-SSE|stream until \`done\`|simulated SSE|SSE over a real subprocess|long-running/SSE bridge flows remain unverified|HTTP-to-MCP bridge subprocess smoke|MCP bridge real subprocess SSE' docs/goal_driver/CURRENT_STATE.md docs/goal_driver/CAPABILITY_AUDIT.md`: passed.
- `git diff --check tests/test_mcp_bridge_real_subprocess.py docs/goal_driver/CURRENT_STATE.md docs/goal_driver/CAPABILITY_AUDIT.md docs/goal_driver/GOAL_PROGRESS.md docs/goal_driver/CODEX_RUN_LEDGER.md`: passed.

### Files Changed
- `tests/test_mcp_bridge_real_subprocess.py`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Focused real bridge subprocess test, bridge suite, ruff, and full pytest all passed. Remaining warning is the external FastAPI TestClient/httpx warning.

### Scope Check
Stayed within local bridge evidence coverage. No endpoint contract rewrite, MCP protocol rewrite, frontend, release, PyPI, Docker, real Abaqus, pull/merge, commit, or push work was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
CODEX-HANDOFF-SUPERSEDE-001

### Date
2026-06-04

### Status
Done

### Summary
纠正过早 final handoff 的本地状态记录。`docs/goal_driver/CODEX_HANDOFF.md` 顶部现在明确标记为 superseded/non-final，说明 Docker/PyPI/GitHub Release/真实 Abaqus 是 blocked branches，不是整个 Goal Chain stop condition，并指向 `GOAL_PROGRESS.md`、`CODEX_RUN_LEDGER.md`、`CURRENT_STATE.md` 作为当前继续执行状态。

### Commands
- `rg -n 'Superseded|not the current final Goal Chain handoff|blocked branches|Do not use this file as final completion evidence|GOAL_PROGRESS|CODEX_RUN_LEDGER' docs/goal_driver/CODEX_HANDOFF.md`: passed.
- `git diff --check docs/goal_driver/CODEX_HANDOFF.md docs/goal_driver/GOAL_PROGRESS.md docs/goal_driver/CODEX_RUN_LEDGER.md`: passed.
- Re-read the top of `docs/goal_driver/CODEX_HANDOFF.md`.

### Files Changed
- `docs/goal_driver/CODEX_HANDOFF.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Documentation state correction only. Verification used targeted search, `git diff --check`, and re-read.

### Scope Check
No final handoff was written. No `update_goal complete`, source/runtime, release, PyPI, Docker, real Abaqus, pull/merge, commit, or push work was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
CAPABILITY-AUDIT-DASHBOARD-ASSET-001

### Date
2026-06-04

### Status
Done

### Summary
同步 capability audit 的 Frontend 行到最新 README dashboard asset 状态。Audit 现在记录 `docs/assets/dashboard-preview.jpg` 已作为 benchmark browser smoke 截图提交，并继续标明该 asset 不代表真实 Abaqus solver/ODB/full e2e 验证。

### Commands
- `rg -n 'dashboard-preview|/tmp/abaqus-agent-frontend-smoke|README preview asset|Browser smoke and README preview asset|Frontend \\|' docs/goal_driver/CAPABILITY_AUDIT.md`: passed.
- `git diff --check docs/goal_driver/CAPABILITY_AUDIT.md docs/goal_driver/GOAL_PROGRESS.md docs/goal_driver/CODEX_RUN_LEDGER.md`: passed.
- Re-read updated capability audit Frontend row.

### Files Changed
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Documentation-only current-state sync. Verification used targeted search, `git diff --check`, and re-read.

### Scope Check
No source/runtime, frontend/browser execution, release, PyPI, Docker, real Abaqus, pull/merge, commit, or push work was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
README-DASHBOARD-ASSET-001

### Date
2026-06-04

### Status
Done

### Summary
将 README Dashboard Preview 从 TODO/ASCII 占位替换为真实 frontend browser smoke 截图资产 `docs/assets/dashboard-preview.jpg`。README caption 明确该图是本地 direct API / benchmark dry-run smoke，不代表真实 Abaqus solver、ODB 或 full e2e runtime verification。

### Commands
- `ls -l /tmp/abaqus-agent-frontend-smoke-benchmark.png /tmp/abaqus-agent-frontend-smoke-spec.png`: passed; smoke screenshots exist.
- `file docs/assets/dashboard-preview.jpg`: passed; JPEG image data, 1610x839.
- `rg -n 'TODO:|ASCII 示意|dashboard-preview|browser smoke|real Abaqus solver|Dashboard Preview' README.md docs/assets docs/goal_driver/GOAL_PROGRESS.md`: passed; README references the asset and no longer contains the old TODO/ASCII placeholder.
- `git diff --check README.md docs/assets/dashboard-preview.jpg docs/goal_driver/GOAL_PROGRESS.md docs/goal_driver/CODEX_RUN_LEDGER.md docs/goal_driver/CURRENT_STATE.md`: passed.
- Re-read updated README Dashboard Preview section.

### Files Changed
- `README.md`
- `docs/assets/dashboard-preview.jpg`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Documentation/asset change. Verification used image file inspection, targeted stale-placeholder search, `git diff --check`, and README re-read.

### Scope Check
No frontend code, release, PyPI, Docker, real Abaqus, pull/merge, commit, or push work was performed. Screenshot evidence remains explicitly local dry-run/browser-smoke evidence only.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
CAPABILITY-AUDIT-CURRENT-STATE-001

### Date
2026-06-04

### Status
Done

### Summary
同步 `docs/goal_driver/CAPABILITY_AUDIT.md` 到当前状态：旧 NL-to-solver headline 不再作为 README 当前声明；baseline 更新为 full pytest 214 passed / 1 warning；HTTP-to-MCP bridge 行记录 FastAPI lifespan migration；unit test 行记录 bridge `on_event` deprecation 已清理，剩余 warning 来自外部 TestClient/httpx；Docker 记录为 blocked branch。

### Commands
- `rg -n 'README headline presents|Natural language -> Problem Spec -> CAE model -> Solver|FastAPI \`on_event\` and Starlette|214 passed, 5 warnings|214 passed, 1 warning|Local Simulation QA / evidence pipeline positioning|FastAPI lifespan|blocked branch' docs/goal_driver/CAPABILITY_AUDIT.md`: passed; stale phrases absent and current phrases present.
- `git diff --check docs/goal_driver/CAPABILITY_AUDIT.md docs/goal_driver/GOAL_PROGRESS.md docs/goal_driver/CODEX_RUN_LEDGER.md docs/goal_driver/CURRENT_STATE.md`: passed.
- Re-read updated `docs/goal_driver/CAPABILITY_AUDIT.md`.

### Files Changed
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Documentation-only correction based on the already-run bridge/full pytest evidence. No new runtime tests were required.

### Scope Check
Stayed within current-state audit synchronization. No source/runtime, release, PyPI, Docker, real Abaqus, pull/merge, commit, or push work was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
MCP-BRIDGE-LIFESPAN-DEPRECATION-001

### Date
2026-06-04

### Status
Done

### Summary
修复 HTTP-to-MCP bridge 的 FastAPI lifecycle deprecation。`mcp_bridge.py` 从 deprecated `@app.on_event("startup"/"shutdown")` 迁移到 FastAPI `lifespan`，保留现有 `mcp_conn` 全局和 endpoint contract。专项 bridge 测试通过，真实 subprocess bridge smoke 通过，full pytest warning 从 5 降到 1。

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_mcp_bridge.py tests/test_mcp_bridge_real_subprocess.py`: passed; 18 passed, 1 warning.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check mcp_bridge.py tests/test_mcp_bridge.py tests/test_mcp_bridge_real_subprocess.py`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed; 214 passed, 1 warning.
- `git diff --check mcp_bridge.py docs/goal_driver/GOAL_PROGRESS.md`: passed.

### Files Changed
- `mcp_bridge.py`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Bridge mock endpoints and real MCP subprocess bridge both passed. Remaining warning is from `fastapi.testclient` / Starlette's dependency-level `httpx` deprecation, not from bridge `on_event` hooks.

### Scope Check
Stayed within bridge lifecycle hardening. No endpoint contract, MCP protocol, dependency, frontend, Docker, real Abaqus, release, PyPI, pull/merge, commit, or push work was performed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
LOCAL-VERIFY-CURRENT-STATE-001

### Date
2026-06-04

### Status
Done

### Summary
对当前 dirty Goal Chain 状态执行本地验证。README、`pyproject.toml`、release instructions、测试和 Goal Driver 文件改动叠加后，editable install、ruff、diff whitespace 检查、full pytest 均通过。

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m pip install -e ".[dev]"`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `git diff --check`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed; 214 passed, 5 warnings.

### Files Changed
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Full local regression passed in the Python 3.11 audit venv. Warnings remain the known Starlette/FastAPI `TestClient` / `on_event` deprecations.

### Scope Check
Read-only verification plus Goal Driver checkpoint updates. No source fix, pull/merge, commit, push, release, PyPI publishing, Docker execution, or real Abaqus claim was made.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
RELEASE-INSTRUCTIONS-HARDENING-001

### Date
2026-06-04

### Status
Done

### Summary
重写 `RELEASE_INSTRUCTIONS.md`，使其匹配当前证据和新定位：GitHub-only 发布边界、PyPI 未发布/source install、Docker 与真实 Abaqus 环境限制、clean/synced checkout preflight、现有 `v0.1.0` tag 与空 GitHub Releases 状态。Release notes 模板已改为 Local Simulation QA / evidence positioning，不再使用旧的 `LLM-powered automation agent` 文案。

### Commands
- `rg -n "LLM-powered automation agent|Natural language|PyPI.*published|Local Simulation QA|not published|docker.*unavailable|real_env_verified|gh release create" RELEASE_INSTRUCTIONS.md`: passed; old release positioning absent, current-boundary phrases present.
- `git diff --check RELEASE_INSTRUCTIONS.md docs/goal_driver/GOAL_PROGRESS.md docs/goal_driver/CODEX_RUN_LEDGER.md docs/goal_driver/CURRENT_STATE.md`: passed.
- Re-read `RELEASE_INSTRUCTIONS.md` after edits.

### Files Changed
- `RELEASE_INSTRUCTIONS.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`
- `docs/goal_driver/NEXT_TICKETS.md`

### Tests
Documentation-only change. Verification used targeted stale-copy search, `git diff --check`, and manual re-read of the rewritten release instructions.

### Scope Check
No release was created. No tag mutation, push, pull/merge, PyPI publishing, code change, dependency change, or real Abaqus claim was made.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
PRODUCT-POSITIONING-METADATA-001

### Date
2026-06-04

### Status
Done

### Summary
将 README 首屏和包 metadata 从旧的 “LLM-powered / Natural language -> Solver” 定位对齐到当前策略：`Local Simulation QA and Regression Framework for Abaqus FEA`。README 现在把输入路径表述为 spec/`.inp`/capsule 到 syntaxcheck、solver、ODB KPI、physics contract、diff/report evidence；`pyproject.toml` description/keywords 也已更新。没有修改运行时代码或依赖。

### Commands
- `rg -n "LLM-powered|Natural language|NL|YAML|Problem Spec|Local Simulation QA|Regression Framework|simulation QA|regression framework" README.md pyproject.toml RELEASE_INSTRUCTIONS.md`: located stale README/metadata positioning and separate stale release instruction copy.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pip install -e ".[dev]"`: passed.
- Package metadata inspection via `importlib.metadata`: passed; Summary is `Local simulation QA and regression framework for Abaqus FEA`, keywords are `abaqus,fea,mcp,odb,qa,regression-testing,simulation`.
- `rg -n "LLM-powered automation agent|Natural language -> Problem Spec|Local Simulation QA|Local simulation QA|regression framework|custom \\.inp|contracts / diff / report" README.md pyproject.toml`: passed; old README/pyproject positioning absent, new positioning present.
- `git diff --check README.md pyproject.toml docs/goal_driver/GOAL_PROGRESS.md docs/goal_driver/CODEX_RUN_LEDGER.md`: passed.

### Files Changed
- `README.md`
- `pyproject.toml`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
No runtime code was changed. Verification covered editable install, installed package metadata, targeted stale-copy search, `git diff --check`, and re-read of README/pyproject.

### Residual Risk
`RELEASE_INSTRUCTIONS.md` still contains old release description/release notes copy. It should be handled in a separate release-instructions hardening ticket so release notes are not accidentally created with the old positioning.

### Scope Check
Stayed within README/package metadata positioning. No runtime/source behavior, dependency versions, release action, publishing, or real Abaqus claims were changed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
REMOTE-RELEASE-CI-STATUS-001

### Date
2026-06-04

### Status
Done

### Summary
完成远端 launch/readiness 状态核验。GitHub open PR/open issue 均为空；repo description/topics 已切到 Simulation QA / regression 定位；最新 visible remote `main` CI run `26815338911` 在 remote head `62c3eb541bddc583c01a1e9d86e4409f07260ce2` 上成功，build 与 Python 3.10/3.11/3.12 test jobs 均 success。远端 tag `v0.1.0` 存在，但 GitHub Releases 为空；PyPI `abaqus-agent` JSON API 返回 404。README 已移除不存在 PyPI 的 badge/install 暗示，改为 source install，并标注 Docker runtime 本机未验证。

### Commands
- `git remote -v`: passed; origin is `https://github.com/Tomsabay/abaqus_agent.git`.
- `git rev-parse HEAD`: passed; local HEAD `553de3fc41336f19e601a042a0adce5b9a88f212`.
- `gh pr list --repo Tomsabay/abaqus_agent --state open --json ...`: passed; `[]`.
- `gh issue list --repo Tomsabay/abaqus_agent --state open --json ...`: passed; `[]`.
- `gh run list --repo Tomsabay/abaqus_agent --branch main --limit 10 --json ...`: passed; latest 10 visible runs all success.
- `gh run view 26815338911 --repo Tomsabay/abaqus_agent --json ...`: passed; build, test (3.10), test (3.11), and test (3.12) all success.
- `gh release list --repo Tomsabay/abaqus_agent --limit 10`: passed; no releases returned.
- `gh api repos/Tomsabay/abaqus_agent/tags`: passed; `v0.1.0` exists.
- `curl -fsSL https://pypi.org/pypi/abaqus-agent/json`: expected 404; package not published.
- `git ls-remote origin refs/heads/main`: passed; remote `main` is `62c3eb541bddc583c01a1e9d86e4409f07260ce2`.
- `git fetch --dry-run origin`: passed; reports forced update from local `553de3f` to remote `62c3eb5`.
- `git diff --check README.md docs/goal_driver/CAPABILITY_AUDIT.md docs/goal_driver/CURRENT_STATE.md docs/goal_driver/NEXT_TICKETS.md docs/goal_driver/GOAL_PROGRESS.md`: passed.

### Files Changed
- `README.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`
- `docs/goal_driver/NEXT_TICKETS.md`

### Tests
No source code was changed. Verification consisted of current remote GitHub/PyPI API checks, README re-read, targeted search for stale PyPI install claims, and `git diff --check`.

### Scope Check
Read-only remote checks only. No commits, pushes, releases, issue/PR comments, workflow reruns, publishing, secret inspection, or strategy changes were performed. Local checkout is behind remote `main`, but no pull/merge was attempted because the worktree has uncommitted Goal Chain changes.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
DOCKER-RUNTIME-SMOKE-001

### Date
2026-06-04

### Status
Blocked by local environment

### Summary
Attempted Docker runtime smoke ticket. `Dockerfile` and `docker-compose.yml` were inspected and the intended smoke path was identified: build image, start API on port 8000, probe `/health`, and trigger a dry-run benchmark endpoint. The local shell cannot run the smoke because `docker` is not installed or not on PATH.

### Commands
- `sed -n '1,220p' Dockerfile`: passed; image uses `python:3.11-slim`, installs requirements and `.[mcp]`, exposes 8000/8001, runs `python server.py`.
- `sed -n '1,220p' docker-compose.yml`: passed; services `api` and `mcp-bridge` exist.
- `docker --version`: failed; `zsh:1: command not found: docker`.
- `docker compose version`: failed; `zsh:1: command not found: docker`.
- `docker compose config`: failed; `zsh:1: command not found: docker`.

### Files Changed
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`
- Docker status was later reflected in `README.md`, `docs/goal_driver/CAPABILITY_AUDIT.md`, `CURRENT_STATE.md`, and `NEXT_TICKETS.md` during `REMOTE-RELEASE-CI-STATUS-001`.

### Tests
Docker smoke was not executable in this environment. No Docker/runtime source change was made, and no container build/start/HTTP probe was completed.

### Scope Check
No Dockerfile, compose, dependency, server, frontend, or Abaqus runtime code was changed. Docker remains config-supported but runtime-unverified until Docker CLI/daemon are available.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
FRONTEND-METADATA-HARDENING-001

### Date
2026-06-04

### Status
Done

### Summary
修复 frontend browser smoke 中发现的静态旧指标：`frontend/index.html` 侧边栏 `TESTS: 39 ✓` 改为 `LOCAL SMOKE ✓`，Benchmark 说明中的“单元测试 39 个，无需 Abaqus 即可运行”改为“本地 smoke / pytest 可在无 Abaqus 环境运行”。Browser reload 确认旧文案不再出现，新文案可见。

### Commands
- `rg -n "TESTS: 39|单元测试 39|LOCAL SMOKE|本地 smoke" frontend/index.html docs/goal_driver README.md`: old frontend text absent; new frontend text present; historical Goal Driver mentions updated afterward.
- Browser reload at `http://127.0.0.1:8000`: passed; `LOCAL SMOKE ✓` visible; old `TESTS: 39` and `单元测试 39` absent.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_server_api_smoke.py`: passed; 2 passed, 1 warning.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: initially failed; 10 failed in `tests/test_real_pipeline.py` because the new stdio smoke test used `asyncio.run()` and closed the default event loop expected by legacy tests.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_mcp_stdio_client.py tests/test_real_pipeline.py`: passed; 17 passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed; 214 passed, 5 warnings.

### Files Changed
- `frontend/index.html`
- `tests/test_mcp_stdio_client.py`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`
- `docs/goal_driver/NEXT_TICKETS.md`

### Tests
Focused API smoke still passes after the frontend copy change, and the served page was reloaded in Browser to confirm visible metadata. Full pytest initially caught an event-loop side effect in the new stdio smoke test; that test was fixed and full pytest now passes. No real Abaqus execution was run.

### Scope Check
Stayed within frontend metadata hardening. No layout redesign, API/server code, dependencies, strategy, or real Abaqus claims were changed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
FRONTEND-BROWSER-SMOKE-001

### Date
2026-06-04

### Status
Done

### Summary
完成本地 frontend browser smoke。启动 `server:app` 于 `http://127.0.0.1:8000`，用 Browser 打开前端，确认页面 title/main UI/topbar `API · ABAQUS ✗ sim · 4 cases`，生成 cantilever spec 并通过校验，Benchmark 表加载 4 个公开 case，Benchmark dry-run 全部 PASS，browser console errors 为空。截图保存到 `/tmp/abaqus-agent-frontend-smoke-benchmark.png` 与 `/tmp/abaqus-agent-frontend-smoke-spec.png`。README/CAPABILITY_AUDIT/CURRENT_STATE/NEXT_TICKETS 已更新为 frontend browser smoke verified；真实 Abaqus 仍 Environment-limited。

### Commands
- `lsof -nP -iTCP:8000 -sTCP:LISTEN`: no listener before start.
- `/tmp/abaqus-agent-audit-venv/bin/python -m uvicorn server:app --host 127.0.0.1 --port 8000`: server started for browser smoke.
- Browser smoke at `http://127.0.0.1:8000`: passed; page loaded, API status visible, spec generated/validated, benchmark dry-run all PASS, console errors empty.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.

### Files Changed
- `README.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`
- `docs/goal_driver/NEXT_TICKETS.md`

### Tests
Browser verification exercised the served frontend in direct API simulation mode only. It did not run real Abaqus, MCP frontend mode, mobile layout, settings/premium flows, or a real solver pipeline.

### Residual Risk
Visible frontend sidebar still shows static `TESTS: 39 ✓`, which is stale relative to current pytest counts. Added a follow-up ticket to harden or remove static frontend metadata before public launch.

### Scope Check
Stayed within browser verification and documentation status scope. No frontend/source/API code was changed; no publishing, secrets, external services, or real Abaqus validation claims were involved.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
FASTAPI-REST-SSE-SMOKE-001

### Date
2026-06-04

### Status
Done

### Summary
新增本地 FastAPI REST/SSE smoke test：`tests/test_server_api_smoke.py` 使用 FastAPI TestClient 验证 `/health`、`/api/spec/generate`、`/api/spec/validate`、`/api/benchmark`，并通过预置完成态 run 验证 `/api/run/{run_id}/stream` 的 SSE 输出。README/CAPABILITY_AUDIT/CURRENT_STATE/NEXT_TICKETS 已更新为 FastAPI REST/SSE smoke verified；浏览器 UI 和真实 Abaqus pipeline 仍未验证。

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_server_api_smoke.py -q`: passed; 2 passed, 1 warning.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_server_api_smoke.py tests/test_mcp_bridge_real_subprocess.py tests/test_mcp_bridge.py`: passed; 20 passed, 5 warnings.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.

### Files Changed
- `tests/test_server_api_smoke.py`
- `README.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`
- `docs/goal_driver/NEXT_TICKETS.md`

### Tests
Local REST/SSE endpoints were exercised through TestClient without starting a real Abaqus job. Existing bridge smoke and mocked bridge endpoint tests still pass. No real Abaqus execution was run.

### Scope Check
Stayed within focused API verification scope. No API contract, frontend, pipeline/background task, dependency, strategy, or real Abaqus validation claim was changed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
MCP-BRIDGE-SUBPROCESS-SMOKE-001

### Date
2026-06-04

### Status
Done

### Summary
新增真实 HTTP-to-MCP bridge subprocess smoke test：`tests/test_mcp_bridge_real_subprocess.py` 使用 FastAPI TestClient 启动真实 `mcp_bridge.MCPConnection`，由 bridge 子进程连接 `mcp_server.py`，验证 `/mcp/health`、`/mcp/api/spec/validate`、`/mcp/api/benchmark`。探针确认现有 `MCPConnection` 可握手，无需重写 bridge 连接层。README/CAPABILITY_AUDIT/CURRENT_STATE/NEXT_TICKETS 已更新为 bridge subprocess smoke verified。

### Commands
- Real `MCPConnection.start()` probe with timeout: passed; `health_check` returned `transport=mcp`.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_mcp_bridge_real_subprocess.py -q`: passed; 1 passed, 5 warnings.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_mcp_bridge_real_subprocess.py tests/test_mcp_server.py tests/test_mcp_bridge.py tests/test_mcp_stdio_client.py`: passed; 40 passed, 5 warnings. Existing output includes pending async task notices from direct `start_run` tests and FastAPI/Starlette deprecation warnings.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.

### Files Changed
- `tests/test_mcp_bridge_real_subprocess.py`
- `README.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`
- `docs/goal_driver/NEXT_TICKETS.md`

### Tests
HTTP bridge requests were routed through a real subprocess-backed `MCPConnection` to `mcp_server.py`. Existing direct MCP tests, mocked bridge tests, stdio client smoke, and ruff all pass. No real Abaqus execution was run.

### Scope Check
Stayed within focused bridge validation scope. No bridge/API rewrite was needed; no frontend, dependency, strategy, or real Abaqus validation claims were changed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
MCP-STDIO-SMOKE-001

### Date
2026-06-04

### Status
Done

### Summary
新增真实 MCP stdio client smoke test：`tests/test_mcp_stdio_client.py` 会启动 `mcp_server.py` 子进程，通过 MCP stdio transport 完成 initialize、list tools、call `health_check`、call `validate_spec_tool`、list resources、read `benchmark://cases`。README 与 capability audit 已将 MCP stdio server 从 direct-function-only 提升为 transport smoke verified；HTTP-to-MCP bridge 的真实 subprocess path 仍保持未验证。

### Commands
- One-off MCP stdio probe: passed; server initialized, tools/resources listed, `health_check` called, `benchmark://cases` read.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_mcp_stdio_client.py -q`: passed; 1 passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_mcp_server.py tests/test_mcp_bridge.py tests/test_mcp_stdio_client.py`: passed; 39 passed, 5 warnings. Existing output includes pending async task notices from direct `start_run` tests and FastAPI/Starlette deprecation warnings.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.

### Files Changed
- `tests/test_mcp_stdio_client.py`
- `README.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`
- `docs/goal_driver/NEXT_TICKETS.md`

### Tests
MCP stdio transport was exercised through the installed `mcp` client and a real `mcp_server.py` subprocess. Existing direct MCP server tests and mocked bridge endpoint tests still pass. No real Abaqus execution was run.

### Scope Check
Stayed within focused MCP validation scope. No MCP API redesign, bridge refactor, frontend/API runtime change, dependency upgrade, strategy change, or Abaqus execution claim was made.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
README-VALIDATION-MATRIX-001

### Date
2026-06-04

### Status
Done

### Summary
README 发布面 hardening：将 `Roadmap` 的混合 `[x]` 能力清单替换为 `Validation Matrix`，明确区分 command verified、covered by tests、dry-run/mock-real、source-supported、environment-limited 和 unverified remote/runtime evidence。真实 Abaqus executable/license/syntaxcheck/submit/ODB/full e2e 仍明确为 Environment-limited。

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_render_smoke_evidence_report.py tests/test_run_real_abaqus_smoke.py tests/test_validate_abaqus_env.py`: passed; 13 passed.
- `rg -n "\\[x\\]|## Roadmap|## Validation Matrix|Environment-limited|real_env_verified|CAPABILITY_AUDIT" README.md`: passed; no `[x]` or `## Roadmap`, validation matrix present.

### Files Changed
- `README.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`
- `docs/goal_driver/NEXT_TICKETS.md`

### Tests
No runtime code was changed. Full ruff and focused evidence-harness pytest passed. README was scanned to confirm the old checkbox roadmap is gone.

### Scope Check
Stayed within README/Goal Driver documentation hardening scope. No source, tests, dependency, frontend, MCP/API runtime, CI, Docker, or strategy changes were made. No dry-run/mock-real evidence was represented as real Abaqus verification.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
EVIDENCE-REPORT-001

### Date
2026-06-04

### Status
Done

### Summary
新增 `scripts/render_smoke_evidence_report.py`，将 `run_real_abaqus_smoke.py` 生成的 `smoke_evidence.json` 渲染为 Markdown handoff report。报告展示 mode/case/overall status/real_env_verified/missing prerequisites/stage summary/stage command/evidence/artifact，并保留 dry-run/mock-real/environment-limited 不等于真实 Abaqus e2e 的边界。

### Commands
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_render_smoke_evidence_report.py`: passed; 4 passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check .`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python scripts/run_real_abaqus_smoke.py --dry-run --json --out-dir /tmp/abaqus-agent-report-smoke`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python scripts/render_smoke_evidence_report.py /tmp/abaqus-agent-report-smoke/smoke_evidence.json --out /tmp/abaqus-agent-report-smoke/smoke_evidence.md`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed; 210 passed, 5 warnings.

### Files Changed
- `scripts/render_smoke_evidence_report.py`
- `tests/test_render_smoke_evidence_report.py`
- `README.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_HANDOFF.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
The renderer was verified with focused tests, full ruff, a generated dry-run smoke bundle, Markdown render output, and full pytest. Real Abaqus execution was not run and remains environment-limited on this Mac.

### Scope Check
Stayed within evidence/reporting scope. Existing uncommitted/untracked state from earlier tickets was observed and not reverted. No dependency, CI, frontend, MCP transport, solver harness behavior, or broad refactor was changed.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
ABAQUS-ENV-VALIDATION-001

### Date
2026-06-03

### Status
Done

### Summary
建立本地 Abaqus 环境验证入口 `scripts/validate_abaqus_env.py`，将 dry-run/source-supported/real-env prerequisites/real e2e not-run 状态分开报告，并新增 JSON 输出和测试覆盖。README 与 CAPABILITY_AUDIT 已更新，降低 roadmap `[x]` 被误读成当前机器真实 Abaqus e2e 已跑通的风险。

### Commands
- `python --version`: failed; `python` command not found.
- `python -m pip install -e ".[dev]"`: failed; `python` command not found.
- `python scripts/validate_abaqus_env.py --dry-run`: failed; `python` command not found.
- `python scripts/validate_abaqus_env.py --json --dry-run`: failed; `python` command not found.
- `python scripts/validate_abaqus_env.py --require-real`: failed; `python` command not found.
- `python -m pytest`: failed; `python` command not found.
- `/tmp/abaqus-agent-audit-venv/bin/python --version`: passed; Python 3.11.15.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pip install -e ".[dev]"`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python scripts/validate_abaqus_env.py`: passed; exit 0; default reports real-env missing.
- `/tmp/abaqus-agent-audit-venv/bin/python scripts/validate_abaqus_env.py --dry-run`: passed; exit 0.
- `/tmp/abaqus-agent-audit-venv/bin/python scripts/validate_abaqus_env.py --json --dry-run`: passed; exit 0; JSON parseable.
- `/tmp/abaqus-agent-audit-venv/bin/python scripts/validate_abaqus_env.py --require-real`: expected non-zero; exit 2; missing list emitted.
- `/tmp/abaqus-agent-audit-venv/bin/python -m ruff check scripts/validate_abaqus_env.py tests/test_validate_abaqus_env.py`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/test_validate_abaqus_env.py -q`: passed; 5 passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest`: passed; 202 passed, 5 warnings.

### Files Changed
- `scripts/validate_abaqus_env.py`
- `tests/test_validate_abaqus_env.py`
- `README.md`
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CODEX_HANDOFF.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`

### Tests
Default and dry-run modes pass without real Abaqus. `--require-real` correctly fails on current Mac due missing Abaqus executable/license/prerequisites. Full pytest passes with 202 tests. Real Abaqus syntaxcheck/submit/ODB/e2e were not run.

### Scope Check
Stayed within allowed files. Existing uncommitted `pyproject.toml` change from an earlier ticket was observed but not edited. No frontend, MCP protocol core, benchmark core, CI, lock, or dependency config changes were made in this ticket.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
README-CAPABILITY-AUDIT-001

### Date
2026-06-03

### Status
Done

### Summary
完成 README capability audit。生成 `docs/goal_driver/CAPABILITY_AUDIT.md`，将 README 核心能力声明映射到源码、测试、命令、dry-run、环境限制和未验证风险。

### Commands
- `cat docs/goal_driver/PROJECT_ID.md`: passed; project name is `abaqus-agent`.
- `python3.11 --version`: passed; Python 3.11.15.
- `python3.11 -m venv /tmp/abaqus-agent-audit-venv`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pip install --upgrade pip`: passed.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pip install -e ".[dev]"`: passed; installed `mcp-1.27.2`.
- package metadata / CLI entry point check: passed; `abaqus-agent -> server:main`.
- `/tmp/abaqus-agent-audit-venv/bin/python -m pytest tests/ -v`: passed; 197 passed, 5 warnings.
- `/tmp/abaqus-agent-audit-venv/bin/python run_benchmark.py --dry-run`: passed; 4/4 `DRY_RUN_PASS`.

### Files Changed
- `docs/goal_driver/CAPABILITY_AUDIT.md`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CODEX_HANDOFF.md`
- `docs/goal_driver/DECISION_LOG.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`
- `docs/goal_driver/NEXT_TICKETS.md`

### Tests
- No source/test fixes were made.
- Real Abaqus executable/license/syntaxcheck/solver/ODB extraction were not run.
- MCP stdio client integration was not run.
- Benchmark dry-run generated `reports/benchmark_20260603_164924.md` and `reports/benchmark_20260603_164924.json`; both were removed because `reports/` is outside allowed modification scope.

### Scope Check
Only allowed Goal Driver files were modified. No source, tests, `pyproject.toml`, README, AGENTS, PROJECT_ID, CI, lock files, benchmark source, frontend source, or unrelated files were modified. No `git add`, `git commit`, or `git reset` was executed.

### Tool Side Effects
- Temporary venv: `/tmp/abaqus-agent-audit-venv`.
- Test cache / bytecode may exist from pytest/import execution: `.pytest_cache`, `__pycache__`.
- Accidental temporary file `/tmp/forbidden-check.txt` was created and removed before continuing; it was outside the repo.

### Review Decision
Review pending.

### Merged
No.

---

## Ticket ID
INIT-PROGRESS-001

### Date
2026-06-03

### Status
Done

### Summary
完成首次只读项目盘点，未修改源码，GPT-5.5 Pro review 结论为满足任务合同、可接受。

### Files Changed
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CODEX_HANDOFF.md`

### Tests
- 本 ticket 不要求运行代码测试。
- `PROJECT_ID` 校验通过，项目名为 `abaqus-agent`。
- `git diff` 无输出，原因是 `docs/` 当前未被 git 跟踪。
- `git status --short` 显示 `AGENTS.md` 与 `docs/` 为 untracked。

### Review Decision
Accept; follow-up needed for baseline verification.

### Merged
No. 建议接受本轮结果；合并前需确认 `AGENTS.md` 与 `docs/goal_driver/` 是否纳入版本控制。

---

## Ticket ID
BASELINE-VERIFY-001

### Date
2026-06-03

### Status
Done

### Summary
完成真实 baseline 验证。安装和 package/CLI metadata 验证通过，benchmark dry-run 通过；pytest 未通过，baseline 判定为 Degraded。

### Commands
- `cat docs/goal_driver/PROJECT_ID.md`: passed; project name is `abaqus-agent`.
- `python --version`: failed; `python` command not found.
- `python3 --version`: passed; Python 3.9.6, below project requirement `>=3.10`.
- `python -m pip install -e ".[dev]"`: failed; `python` command not found.
- `/tmp/abaqus-agent-baseline-venv/bin/python -m pip install -e ".[dev]"`: passed.
- package metadata / CLI entry point check: passed; `abaqus-agent -> server:main`.
- `/tmp/abaqus-agent-baseline-venv/bin/python -m pytest tests/ -v`: failed; 197 collected, 176 passed, 21 failed, 5 warnings.
- `python run_benchmark.py --dry-run`: failed; `python` command not found.
- `/tmp/abaqus-agent-baseline-venv/bin/python run_benchmark.py --dry-run`: passed; 4/4 dry-run cases passed.

### Files Changed
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CODEX_HANDOFF.md`
- `docs/goal_driver/DECISION_LOG.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`
- `docs/goal_driver/NEXT_TICKETS.md`

### Tests
- No source/test fixes were made.
- Pytest failure cause: `tests/test_mcp_server.py` imports `mcp_server.py`, which requires `mcp.server.fastmcp`; `mcp` was not installed by `.[dev]`.
- Benchmark dry-run generated report files, then they were removed because reports are outside allowed modification scope.
- Tool side effects observed: `.pytest_cache`, `__pycache__`, temporary venv under `/tmp/abaqus-agent-baseline-venv`.

### Scope Check
No source, tests, dependency config, CI, README, pyproject, AGENTS, PROJECT_ID, lock files, benchmark source, or frontend source were modified. No `git add`, `git commit`, or `git reset` was executed.

### Review Decision
Review pending. Recommended follow-up: baseline repair ticket.

### Merged
No.

---

## Ticket ID
MCP-TEST-CONTRACT-001

### Date
2026-06-03

### Status
Done

### Summary
修复 MCP dependency / default pytest 合同。`dev` extra 增加 `mcp>=1.0`，使 Python 3.11 下 `pip install -e ".[dev]"` 后默认 MCP server 测试可运行。

### Commands
- `cat docs/goal_driver/PROJECT_ID.md`: passed; project name is `abaqus-agent`.
- `python3.11 --version`: passed; Python 3.11.15.
- `python3.11 -m venv /tmp/abaqus-agent-mcp-fix-venv`: passed.
- `/tmp/abaqus-agent-mcp-fix-venv/bin/python -m pip install --upgrade pip`: passed.
- `/tmp/abaqus-agent-mcp-fix-venv/bin/python -m pip install -e ".[dev]"`: passed; installed `mcp-1.27.2`.
- package metadata / CLI entry point check: passed; `abaqus-agent -> server:main`.
- `import mcp.server.fastmcp`: passed.
- `/tmp/abaqus-agent-mcp-fix-venv/bin/python -m pytest tests/test_mcp_server.py -v`: passed; 21 passed.
- `/tmp/abaqus-agent-mcp-fix-venv/bin/python -m pytest tests/ -v`: passed; 197 passed, 5 warnings.
- `/tmp/abaqus-agent-mcp-fix-venv/bin/python run_benchmark.py --dry-run`: passed; 4/4 dry-run cases passed.

### Files Changed
- `pyproject.toml`
- `docs/goal_driver/GOAL_PROGRESS.md`
- `docs/goal_driver/CURRENT_STATE.md`
- `docs/goal_driver/CODEX_HANDOFF.md`
- `docs/goal_driver/DECISION_LOG.md`
- `docs/goal_driver/CODEX_RUN_LEDGER.md`
- `docs/goal_driver/NEXT_TICKETS.md`

### Tests
- MCP import verified.
- MCP-focused tests passed.
- Full default pytest passed.
- Benchmark dry-run passed.
- Benchmark report files were generated and removed because reports are outside allowed modification scope.
- Tool side effects observed: `.pytest_cache`, `__pycache__`, editable install metadata/cache, temporary venv under `/tmp/abaqus-agent-mcp-fix-venv`.

### Scope Check
Only `pyproject.toml` and allowed Goal Driver files were modified. No source, tests, CI, README, AGENTS, PROJECT_ID, lock files, benchmark source, frontend source, LLM planner, or Abaqus execution modules were modified. No `git add`, `git commit`, or `git reset` was executed.

### Review Decision
Review pending.

### Merged
No.
