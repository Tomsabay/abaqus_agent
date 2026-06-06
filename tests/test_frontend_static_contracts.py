from pathlib import Path

FRONTEND_INDEX = Path(__file__).resolve().parent.parent / "frontend" / "index.html"


def test_evidence_vault_smoke_verify_detail_renders_nested_demo_pack_summary():
    source = FRONTEND_INDEX.read_text(encoding="utf-8")

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
    source = FRONTEND_INDEX.read_text(encoding="utf-8")

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
    source = FRONTEND_INDEX.read_text(encoding="utf-8")

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
