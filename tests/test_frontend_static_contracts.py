import sys
from pathlib import Path

FRONTEND_INDEX = Path(__file__).resolve().parent.parent / "frontend" / "index.html"
FRONTEND_WORKBENCH = Path(__file__).resolve().parent.parent / "frontend" / "workbench.html"

# The workbench is markup + workbench.css + workbench_i18n.js +
# workbench_viewport.js since the split. Reading only the .html would not
# fail these tests loudly -- it would quietly stop finding what they guard.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tests.frontend_sources import index_text, page_files, workbench_text  # noqa: E402


def test_workbench_results_render_dynamic_animation_card():
    source = workbench_text()

    required_markers = [
        "function extractAnimation(run)",
        "rec.animation",
        'class="anim-card"',
        ".anim-card video",
        "<video controls loop muted",
        "artifact/anim.mp4",
        "动画 · 逐帧动力学响应",
        "this.closest('.anim-card').style.display='none'",
    ]

    missing_markers = [marker for marker in required_markers if marker not in source]
    assert missing_markers == []


def test_evidence_vault_smoke_verify_detail_renders_nested_demo_pack_summary():
    source = index_text()

    required_markers = [
        "function renderEvidenceVaultBundleVerification(data)",
        "data.copied_demo_pack_verification || null",
        "detail.copied_demo_pack_verification = {",
        "nestedDemoPack.overall_status",
        "nestedDemoPack.zip_path",
        "nestedDemoPack.checked_file_count",
        "data-vault-verify-smoke-id",
        "verifyEvidenceVaultSmoke(vaultId)",
    ]

    missing_markers = [marker for marker in required_markers if marker not in source]
    assert missing_markers == []


def test_local_cli_smoke_result_renders_nested_demo_pack_verification():
    source = index_text()

    required_markers = [
        "function renderLocalCliSmokeResult(data)",
        "verify.copied_demo_pack_verification || {}",
        "copied demo pack verify:",
        "nestedVerify.overall_status",
        "nestedVerify.checked_file_count",
        "${nestedVerifyLine}",
    ]

    missing_markers = [marker for marker in required_markers if marker not in source]
    assert missing_markers == []


def test_mobile_layout_keeps_main_workspace_responsive():
    source = index_text()

    required_markers = [
        "@media (max-width: 720px)",
        ".evidence-area {\n  flex: 1;\n  min-width: 0;",
        ".evidence-column {\n  min-width: 0;",
        ".evidence-box {\n  min-width: 0;",
        "overflow-wrap: anywhere;",
        "word-break: break-word;",
        "grid-template-columns: minmax(0, 1fr);",
        "grid-template-rows: 42px auto minmax(0, 1fr);",
        "flex-direction: row;",
        "overflow-x: auto;",
        "border-bottom: 1px solid var(--border);",
        ".main {\n    grid-row: 3;\n    min-width: 0;",
        ".prompt-area > div > div[style*=\"display:flex\"]",
        ".evidence-actions .btn",
        ".evidence-status {\n    flex: 1 0 100%;\n    margin-left: 0;",
        "@media (max-width: 460px)",
        ".evidence-verdict {\n    grid-template-columns: 1fr;",
    ]

    missing_markers = [marker for marker in required_markers if marker not in source]
    assert missing_markers == []


def test_copilot_first_screen_and_api_contract_markers_exist():
    source = index_text()

    required_markers = [
        'data-panel="copilot"',
        'id="panel-copilot"',
        "Abaqus/CAE Copilot",
        "Codex 本机认证",
        "/api/copilot/status",
        "/api/copilot/plugin-guide",
        "/api/copilot/release-gate",
        "/api/copilot/alpha-package.zip",
        "/api/copilot/alpha-package/verify",
        "/api/copilot/plan",
        "/api/copilot/execute",
        "/api/copilot/sessions/${encodeURIComponent(sessionId)}/activate",
        "/api/copilot/sessions/${encodeURIComponent(sessionId)}",
        "插件已指向当前会话",
        "插件执行状态",
        "CAE 内执行路径",
        "Alpha Gate",
        "下载 Alpha 包",
        "下载插件和证据包",
        "Alpha 包自检",
        "ALPHA_READY_WITH_GUI_BLOCKER",
        "interactive_cae_gui_visual",
        "abaqus-agent-copilot-install-plugin --plugin-dir",
        "ABAQUS_AGENT_SERVER_URL",
        "AbaqusAgent Copilot: Open Sidecar",
        "AbaqusAgent Copilot: Run Current Plan",
        "AbaqusAgent Copilot: Execute Next Action",
        "AbaqusAgent Copilot: Check Session Status",
        "btn-copilot-refresh",
        "btn-copilot-package",
        "Abaqus/CAE 菜单点击",
        "function loadCopilotPluginGuide()",
        "function loadCopilotReleaseGate()",
        "function loadCopilotPackageVerify()",
        "function renderCopilotReleaseGate(data, packageVerify = state.copilotPackageVerify)",
        "function renderCopilotPluginGuide(data, sessionId = '')",
        "function renderCopilotPlan(plan)",
        "function renderCopilotSessionStatus(data)",
        "btn-copilot-execute",
        # Cursor-style CAE workspace panes (model tree / viewport / queue / errors)
        'id="copilot-model-tree"',
        'id="copilot-viewport"',
        'id="copilot-errors"',
        "copilot-pane-tree",
        "copilot-pane-viewport",
        "copilot-pane-queue",
        "copilot-pane-errors",
        "模型树",
        "视口快照",
        "动作队列",
        "报错诊断",
        "AbaqusAgent Copilot: Sync Model To Sidecar",
        "function renderCopilotModelTree(data)",
        "function renderCopilotViewport(sessionId, capturedAt, srcOverride)",
        "function renderCopilotErrors(errors)",
        "function updateCopilotQueueStatuses(data)",
        "function startCopilotPolling(sessionId)",
        "/model-state",
        "/viewport.png?t=",
        "让 Copilot 修复",
    ]

    missing_markers = [marker for marker in required_markers if marker not in source]
    assert missing_markers == []


def test_copilot_workspace_ships_replay_mode_for_no_abaqus_demo():
    source = index_text()

    required_markers = [
        # entry point: a viewer without Abaqus can replay a recorded real session
        'id="btn-copilot-replay"',
        "播放真实录像",
        "async function runCopilotReplay()",
        "function applyCopilotReplayFrame(frame)",
        "function cancelCopilotReplay()",
        "function resetCopilotPanesForReplay()",
        "/api/copilot/replay",
        # replay viewports are inlined PNGs, not live server fetches
        "data:image/png;base64,${frame.png_base64}",
        # a new live session must take over from a running replay
        "cancelCopilotReplay();\n  if (copilotStream) copilotStream.close();",
        # replay pacing compresses solver dead time
        "REPLAY_MAX_GAP_S",
        "REPLAY_MIN_GAP_S",
    ]

    missing_markers = [marker for marker in required_markers if marker not in source]
    assert missing_markers == []


def test_copilot_error_pane_shows_diagnosis_and_one_click_fix():
    source = index_text()

    required_markers = [
        # plain-language diagnosis card renders above the raw traceback
        "copilot-error-diagnosis",
        "copilot-error-diagnosis-title",
        "err.diagnosis.title",
        "err.diagnosis.explanation",
        "err.diagnosis.suggestion",
        "怎么办：",
        # fix is one click: fill the prompt AND generate the repaired plan
        "document.getElementById('btn-copilot-plan').click()",
        "请按诊断修复并给出新的操作计划",
    ]

    missing_markers = [marker for marker in required_markers if marker not in source]
    assert missing_markers == []


def test_copilot_first_visit_discovers_replay_without_abaqus():
    source = index_text()

    required_markers = [
        # the empty action-queue card advertises the recorded demo
        'id="copilot-replay-hint"',
        "先看一段真实会话录像",
        "runCopilotReplay(); return false;",
        # hint only appears when a recording actually exists
        "detectCopilotReplayAvailability",
        "if (!recordings.length) return;",
    ]

    missing_markers = [marker for marker in required_markers if marker not in source]
    assert missing_markers == []


def test_copilot_replay_ends_with_conversion_guidance_and_enter_sends():
    source = index_text()

    required_markers = [
        # after the replay, viewers are told the two concrete next steps
        "想在你自己的模型上用？",
        "生成计划不需要 Abaqus",
        # replay button doubles as a progress indicator (the label itself now
        # lives in the i18n catalogue, so the contract is split in two: the
        # call still feeds it the live frame counters, and the Chinese string
        # still spends them on a stop-replay label)
        "t('copilot.btn.replayStopProgress', { current: i + 1, total: frames.length })",
        '"⏹ 停止回放 {current}/{total}"',
        # Enter submits, Shift+Enter newline, IME composition ignored
        "e.key === 'Enter' && !e.shiftKey && !e.isComposing",
    ]

    missing_markers = [marker for marker in required_markers if marker not in source]
    assert missing_markers == []


def test_copilot_error_pane_renders_solver_doctor_findings():
    source = index_text()

    required_markers = [
        "err.solver_doctor ? `",
        "求解日志会诊",
        "err.solver_doctor.primary_category",
        "err.solver_doctor.summary",
        "(err.solver_doctor.findings || []).slice(0, 3)",
        "f.recommendation",
        # the one-click fix prompt carries the solver diagnosis too
        "err.solver_doctor?.summary",
    ]

    missing_markers = [marker for marker in required_markers if marker not in source]
    assert missing_markers == []


def test_copilot_workspace_reattaches_to_last_session_on_load():
    source = index_text()

    required_markers = [
        "resumeActiveCopilotSession",
        "/api/copilot/sessions/active",
        "已恢复上次会话",
        # resumed plan must be executable, not display-only
        "state.copilotPlan = data.plan;",
        "startCopilotPolling(data.session_id);",
    ]

    missing_markers = [marker for marker in required_markers if marker not in source]
    assert missing_markers == []


def test_copilot_history_picker_restores_stored_sessions():
    source = index_text()

    required_markers = [
        'id="copilot-history-select"',
        "async function loadCopilotSessionHistory()",
        "async function restoreCopilotSession(data, note)",
        "/api/copilot/sessions/${encodeURIComponent(sid)}/full",
        # switching sessions must also repoint the CAE plugin
        "await activateCopilotSession(sid); // point the CAE plugin at it too",
        "已切换到会话",
        # history refreshes when a new plan is generated
        "loadCopilotSessionHistory();\n    toast(data.backend === 'codex_app_server'",
    ]

    missing_markers = [marker for marker in required_markers if marker not in source]
    assert missing_markers == []


def test_copilot_replay_scenario_picker_contract():
    source = index_text()

    required_markers = [
        'id="copilot-replay-select"',
        "/api/copilot/replays",
        "?name=${encodeURIComponent(picked)}",
        # picker only appears when more than one recording exists
        "recordings.length > 1",
    ]

    missing_markers = [marker for marker in required_markers if marker not in source]
    assert missing_markers == []


def test_doctor_panel_shows_cae_pattern_gallery():
    source = index_text()

    required_markers = [
        "CAE 报错模式（插件侧，人话诊断）",
        'id="doctor-cae-patterns"',
        'id="doctor-cae-pattern-count"',
        "async function loadDoctorCaePatterns()",
        "/api/doctor/cae-patterns",
    ]

    missing_markers = [marker for marker in required_markers if marker not in source]
    assert missing_markers == []


def test_doctor_panel_self_service_traceback_diagnosis():
    source = index_text()

    required_markers = [
        'id="doctor-cae-input"',
        'id="btn-doctor-cae-diagnose"',
        "诊断我的报错",
        "/api/doctor/cae-diagnose",
        "（未匹配已知模式）",
    ]

    missing_markers = [marker for marker in required_markers if marker not in source]
    assert missing_markers == []


def test_copilot_status_card_renders_live_kpis():
    source = index_text()

    required_markers = [
        "function renderCopilotKpis(kpis)",
        "COPILOT_KPI_LABELS",
        "求解结果 · ",
        "最大 Mises",
        "应力集中系数 Kt",
        "一阶固有频率",
        "kpis.natural_frequencies_hz",
        "${renderCopilotKpis(data.kpis)}",
    ]

    missing_markers = [marker for marker in required_markers if marker not in source]
    assert missing_markers == []


def test_workbench_surfaces_the_solver_backend_and_its_limits():
    """A run that solved nothing must never render as if Abaqus produced it.

    The markers this pinned until 2026-08-15 were about a CalculiX fallback
    degrading in place. There is no fallback now, so the same screen has to
    carry the harder message — nothing ran — and still say why.
    """
    source = workbench_text()

    required_markers = [
        "backend.supported === false",
        "backend.unavailable.title",
        "未求解：本机没有 Abaqus",
        "ABAQUS_AGENT_ABAQUS_CMD",
        'class="backend-banner"',
        "run.visuals_notice",
        "const noVisualsWhy = (run && run.visuals_notice)",
        "status === 'REFUSED'",
        "已拒绝求解",
        "prov.abaqus_equivalent === false",
        "不参与达标判定",
        ".schip.skipped",
    ]

    missing_markers = [marker for marker in required_markers if marker not in source]
    assert missing_markers == []


def test_the_workbench_no_longer_offers_a_second_solver():
    """A leftover branch would light a LED for a backend that cannot exist."""
    source = workbench_text()

    for gone in ("calculix", "CalculiX", "calculix_available",
                 "backend.fallback", "sb.release.degraded"):
        assert gone not in source, gone


def test_preview_parse_problems_survive_every_stats_rewrite():
    """Parse warnings ride the stats bar itself (P2-d #3).

    meta / part / done handlers in BOTH preview paths rewrite stats.innerHTML,
    so a separately rendered warning would be erased by whichever handler
    fired last. The contract is therefore on previewStatsHtml, the one
    function every rewrite goes through.
    """
    source = workbench_text()

    for marker in [
        "meta.problems",
        'class="vp-parse-warn"',
        ".vp-parse-warn {",
    ]:
        assert marker in source, marker


def test_slider_rebuild_failure_clears_the_viewport():
    """A failed rebuild must not leave slider-cheat-scaled geometry on screen.

    At error time the mesh in the viewport is the OLD proposal scaled live by
    the sliders — not the spec being shown. With only a small status text, the
    user reads it as the new model.
    """
    source = workbench_text()

    apply_fn = source.split("async function applySliders()", 1)[1]
    apply_fn = apply_fn.split("async function submitAccept", 1)[0]

    assert apply_fn.count("state.previewViewport.dispose()") >= 2, (
        "both the error event and the catch branch must dispose the viewport")
    assert apply_fn.count("canvas.innerHTML = ''") >= 3  # meta + error + catch
    # The wording moved into the i18n catalogue, so both halves are pinned: the
    # failure path still says so, and it still says so in Chinese.
    assert "vp.rebuildFailed" in apply_fn
    assert '"vp.rebuildFailed": "重建失败: {msg}"' in source


# ── the release the UI shows must come from the solver, not from a literal ──

def _schema_release_years() -> list[str]:
    import json
    schema_path = Path(__file__).resolve().parent.parent / "schema" / "spec_schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    return schema["properties"]["meta"]["properties"]["abaqus_release"]["enum"]


def test_release_selector_offers_every_schema_year():
    """The old list was 2023/2024/2025 only, so a user on 2021 — this build's
    own machine — could not pick their own release, and the spec that got
    generated carried a year the machine did not have."""
    source = index_text()
    block = source.split('<select id="abaqus-version"', 1)[1].split("</select>", 1)[0]

    for year in _schema_release_years():
        assert 'value="%s"' % year in block, (
            "schema allows Abaqus %s but the selector does not offer it" % year)


def test_release_selector_is_driven_by_the_health_probe():
    source = index_text()

    assert "function applyDetectedRelease(" in source
    assert "applyDetectedRelease(data.abaqus_release)" in source, (
        "/health already reports the installed release; the selector must use it")
    # A user's explicit choice must not be silently overwritten on the next poll.
    assert "userPicked" in source
    apply_fn = source.split("function applyDetectedRelease(", 1)[1]
    apply_fn = apply_fn.split("\nfunction ", 1)[0]
    assert "userPicked" in apply_fn


def test_client_validator_accepts_every_schema_year():
    """validateSpecText rejected anything outside 2023/2024/2025, telling a
    2021 user their perfectly valid spec was invalid."""
    source = index_text()
    validator = source.split("function validateSpecText(", 1)[1]
    validator = validator.split("\nfunction ", 1)[0]

    release_line = [ln for ln in validator.splitlines() if "abaqus_release:" in ln]
    assert release_line, "validator no longer checks abaqus_release at all"
    joined = " ".join(release_line)
    for year in _schema_release_years():
        assert year in joined, (
            "client validator would reject the schema-valid release %s" % year)


# ── one design system, two surfaces ─────────────────────────────────────────

DESIGN_SYSTEM = Path(__file__).resolve().parent.parent / "frontend" / "design-system.css"


def test_both_surfaces_link_the_shared_design_system():
    """They used to carry separate :root blocks that had drifted into
    different products — near-black + Google fonts on one, cool graphite +
    system fonts on the other. Same application, two skins."""
    assert DESIGN_SYSTEM.is_file()
    for page in (FRONTEND_INDEX, FRONTEND_WORKBENCH):
        source = page.read_text(encoding="utf-8")
        assert '<link rel="stylesheet" href="/static/design-system.css">' in source, page.name
        assert 'class="ds"' in source.split(">", 2)[1] + ">", (
            "%s must opt into the system on <html>" % page.name)


def test_no_page_declares_its_own_token_vocabulary():
    """A second :root block is how the drift started. Tokens live in one file.

    Every file the page is built from, not just its markup: once the workbench
    stylesheet moved to workbench.css, checking only the .html would have let a
    local :root back in through the exact file most likely to grow one.
    """
    for page in (FRONTEND_INDEX, FRONTEND_WORKBENCH):
        for path in page_files(page.name):
            if path.name == "design-system.css":
                continue                       # the one file that owns them
            assert ":root {" not in path.read_text(encoding="utf-8"), (
                "%s redefines tokens locally; add them to design-system.css "
                "instead" % path.name)


def test_no_external_font_or_asset_requests():
    """An engineering tool that phones out to a CDN on load leaks usage and
    fails outright on the air-gapped workstations this targets."""
    import re

    # Every file, not just the markup: a stylesheet is the classic place for
    # an @import of a webfont, and the workbench stylesheet is its own file now.
    for page in (FRONTEND_INDEX, FRONTEND_WORKBENCH):
        for path in page_files(page.name):
            source = path.read_text(encoding="utf-8")
            # Comments do not make requests, and the comment recording *why*
            # the Google Fonts link was removed necessarily names it.
            live = re.sub(r"<!--.*?-->", "", source, flags=re.S)
            live = re.sub(r"/\*.*?\*/", "", live, flags=re.S)
            live = re.sub(r"^\s*//.*$", "", live, flags=re.M)
            for host in ("fonts.googleapis.com", "fonts.gstatic.com",
                         "cdn.jsdelivr.net", "unpkg.com", "cdnjs.cloudflare.com"):
                assert host not in live, "%s still fetches from %s" % (path.name, host)


def test_the_two_surfaces_link_to_each_other():
    index = index_text()
    workbench = workbench_text()

    assert 'href="/workbench"' in index, (
        "the product's main surface was unreachable from its own home page")
    assert 'href="/"' in workbench, "no way back to the tools page"


def test_the_workbench_empty_state_offers_a_way_in():
    """At rest this pane was a 1000px void of grid lines with one grey line of
    text. It is the first screen every new user sees."""
    source = workbench_text()

    assert 'id="spec-empty" class="onboard"' in source
    assert source.count("onboard-card") >= 4          # style + 3 cards
    assert "data-seed=" in source
    # Cards that only decorate would be worse than none: they must seed the
    # prompt exactly like the existing quick chips do.
    assert "document.querySelectorAll('.onboard-card')" in source
    assert "card.dataset.seed" in source
    # The global `button { height: 24px }` rule clipped the third line.
    onboard_card = source.split(".onboard-card {", 1)[1].split("}", 1)[0]
    assert "height: auto" in onboard_card


def test_the_deleted_licensing_badge_stays_deleted():
    source = index_text()
    markup = source.split("<body", 1)[1] if "<body" in source else source
    # Allowed in the explanatory comment, never as a rendered element.
    for line in markup.splitlines():
        if "NO LICENSE REQ" in line:
            assert line.strip().startswith(("<!--", "*", "-")) or "used to sit here" in line, (
                "licensing badge markup is back: %s" % line.strip())
