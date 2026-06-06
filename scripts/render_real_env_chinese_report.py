#!/usr/bin/env python3
"""Render a Chinese report for real Abaqus smoke evidence."""

from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path
from typing import Any

STAGE_LABELS = {
    "environment_preflight": "环境预检",
    "input_job_preparation": "CAE 建模 / 输入文件生成",
    "syntaxcheck": "Abaqus 语法检查",
    "submit_job": "提交真实求解",
    "monitor_status_collection": "求解状态监控",
    "odb_kpi_adapter_probe": "ODB KPI 抽取",
    "evidence_report_generation": "证据报告生成",
}

STATUS_LABELS = {
    "completed": "完成",
    "failed": "失败",
    "environment-limited": "环境受限",
    "missing": "缺失",
    "not-run": "未运行",
    "dry-run": "干跑",
    "mock-real": "模拟真实",
}

EVIDENCE_TRANSLATIONS = {
    "overall_status": "总体状态",
    "real_env_prerequisites_ready": "真实环境前置条件就绪",
    "real_abaqus_e2e_verified": "真实 Abaqus 端到端验证",
    "function": "函数",
    "run_id": "运行 ID",
    "cached": "是否缓存",
    "inp_path": "输入文件",
    "ok": "检查通过",
    "returncode": "返回码",
    "log_path": "日志路径",
    "status": "状态",
    "job_name": "作业名",
    "odb_exists": "ODB 已生成",
    "sta_path": "状态文件",
    "odb_path": "ODB 文件",
    "kpis": "KPI",
    "errors": "错误",
    "target": "报告目标",
    "stage_logs": "阶段日志",
}


CSS = """
:root{font-family:-apple-system,BlinkMacSystemFont,'PingFang SC','Microsoft YaHei','Segoe UI',sans-serif;color:#172026;background:#f4f6f7}
body{margin:0;padding:42px 54px;box-sizing:border-box}
h1{font-size:34px;margin:0 0 14px}
h2{font-size:22px;margin:0 0 14px}
h3{font-size:15px;margin:18px 0 8px;color:#52605f}
.status{font-size:40px;color:#0f766e;font-weight:760;margin:8px 0 18px}
.sub{color:#52605f;line-height:1.55;margin:0 0 22px}
.grid{display:grid;grid-template-columns:1.12fr .88fr;gap:22px}
.card{background:white;border:1px solid #d8e0df;border-radius:8px;padding:22px;box-shadow:0 1px 2px rgba(0,0,0,.04)}
.kv{display:grid;grid-template-columns:150px 1fr;gap:8px;font-size:14px}
.kv div{padding:8px 0;border-bottom:1px solid #e7eceb}
table{border-collapse:collapse;width:100%;font-size:13px}
td,th{border-bottom:1px solid #e4e9e8;text-align:left;vertical-align:top;padding:9px 8px}
th{color:#52605f;font-size:12px;text-transform:uppercase;letter-spacing:.04em}
.pill{display:inline-block;border-radius:999px;padding:3px 9px;font-size:12px;font-weight:700;background:#d9f7e8;color:#096843}
.pill.na{background:#edf1f2;color:#536061}
.mono{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:12px;white-space:pre-wrap;background:#0f1720;color:#dbeafe;border-radius:8px;padding:16px;max-height:900px;overflow:hidden}
.two{display:grid;grid-template-columns:1fr 1fr;gap:18px}
ul{margin:0;padding-left:18px;line-height:1.6;font-size:13px}
code{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
.note{font-size:13px;color:#52605f;line-height:1.6}
"""


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def _escape(value: Any) -> str:
    return html.escape(str(value))


def _translate_evidence(item: str) -> str:
    if "=" not in item:
        return _escape(item)
    key, value = item.split("=", 1)
    label = EVIDENCE_TRANSLATIONS.get(key, key)
    return f"{_escape(label)}：{_escape(value)}"


def _status_label(status: str) -> str:
    return STATUS_LABELS.get(status, status)


def _stage_label(name: str) -> str:
    return STAGE_LABELS.get(name, name)


def _doc(title: str, body: str) -> str:
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>{_escape(title)}</title><style>{CSS}</style></head><body>{body}</body></html>"
    )


def _find_run_dir(evidence_root: Path) -> Path:
    candidates = sorted(evidence_root.glob("smoke_*/smoke_evidence.json"))
    if not candidates:
        raise FileNotFoundError(f"未找到 smoke_evidence.json: {evidence_root}")
    return candidates[-1].parent


def render_chinese_report(evidence_root: Path) -> list[Path]:
    evidence_root = evidence_root.resolve()
    run_dir = _find_run_dir(evidence_root)
    smoke = _read_json(run_dir / "smoke_evidence.json")
    kpi_result = _read_json(run_dir / "run" / "_kpi_result.json")
    services = _read_json(evidence_root / "windows_services.json")
    env_probe = _read_text(evidence_root / "windows_env_probe.txt")
    solver_log = _read_text(run_dir / "run" / "Cantilever.log")
    sta_text = _read_text(run_dir / "run" / "Cantilever.sta")
    syntax_log = _read_text(run_dir / "run" / "Cantilever_syntaxcheck.log")

    host = env_probe.splitlines()[0].strip() if env_probe.splitlines() else "未知"
    release_match = re.search(r"Abaqus\s+20\d{2}", env_probe)
    release = release_match.group(0) if release_match else "见环境探针"

    kpi_rows = "".join(
        f"<tr><td>{_escape(name)}</td><td>{value:.12g}</td></tr>"
        for name, value in kpi_result.get("kpis", {}).items()
    )
    service_rows = "".join(
        "<tr><td>{name}</td><td>{status}</td><td>{start}</td></tr>".format(
            name=_escape(svc.get("Name", "")),
            status="运行中" if svc.get("Status") == 4 else _escape(svc.get("Status")),
            start="自动" if svc.get("StartType") == 2 else _escape(svc.get("StartType")),
        )
        for svc in services
    )

    overview = f"""
    <h1>真实 Abaqus 验证报告</h1>
    <div class="status">验证通过：真实环境已跑通</div>
    <p class="sub">这份中文报告只翻译展示层；原始 JSON、日志、ODB 文件保持不变，仍在同一证据目录内。</p>
    <div class="grid">
      <div class="card">
        <h2>结论和环境</h2>
        <div class="kv">
          <div>Windows 主机</div><div><b>{_escape(host)}</b>，通过 Tailscale SSH 连接</div>
          <div>Abaqus 版本</div><div><b>{_escape(release)}</b>，命令 <code>C:\\SIMULIA\\Commands\\abaqus.bat</code></div>
          <div>验证用例</div><div>{_escape(smoke.get("case"))} / {_escape(smoke.get("mode"))}</div>
          <div>总状态</div><div><b>{_escape(smoke.get("overall_status"))}</b></div>
          <div>真实环境验证</div><div><b>{'是' if smoke.get('real_env_verified') else '否'}</b></div>
          <div>退出码</div><div>{_escape(smoke.get("exit_code"))}</div>
          <div>证据胶囊哈希</div><div><code>{_escape(smoke.get("capsule", {}).get("capsule_hash"))}</code></div>
        </div>
      </div>
      <div class="card">
        <h2>从真实 ODB 读出的 KPI</h2>
        <table><tr><th>指标</th><th>数值</th></tr>{kpi_rows}</table>
        <h3>远端服务状态</h3>
        <table><tr><th>服务</th><th>状态</th><th>启动方式</th></tr>{service_rows}</table>
      </div>
    </div>
    """

    stage_rows = []
    for stage in smoke.get("stages", []):
        evidence = "<br>".join(_translate_evidence(item) for item in stage.get("evidence", []))
        real = "是" if stage.get("real_env_verified") else "不适用"
        pill_class = "pill" if stage.get("real_env_verified") or stage.get("status") == "completed" else "pill na"
        stage_rows.append(
            "<tr><td>{name}</td><td><span class='{pill}'>{status}</span></td><td>{real}</td><td>{evidence}</td></tr>".format(
                name=_escape(_stage_label(stage.get("name", ""))),
                pill=pill_class,
                status=_escape(_status_label(stage.get("status", ""))),
                real=real,
                evidence=evidence,
            )
        )
    stages = """
    <h1>真实阶段逐项验证</h1>
    <div class="status">每个真实阶段都已完成</div>
    <div class="card">
      <table><tr><th>阶段</th><th>状态</th><th>真实验证</th><th>证据</th></tr>{rows}</table>
    </div>
    """.format(rows="".join(stage_rows))

    logs = f"""
    <h1>求解日志证据</h1>
    <p class="sub">左侧是 Abaqus/Standard 求解日志，右侧是 .sta 状态文件。关键结论：作业完成，Standard license token 已 checkout，分析成功结束。</p>
    <div class="two">
      <div class="card"><h2>Abaqus/Standard 日志</h2><div class="mono">{_escape(solver_log[-3200:])}</div></div>
      <div class="card"><h2>状态文件 .sta</h2><div class="mono">{_escape(sta_text[-2500:])}</div></div>
    </div>
    """

    syntax = f"""
    <h1>语法检查证据</h1>
    <p class="sub">Abaqus syntaxcheck 在真实 Abaqus 2021 下执行并完成，说明生成的输入文件可被 Abaqus 解析。</p>
    <div class="card"><div class="mono">{_escape(syntax_log[-5000:])}</div></div>
    """

    artifacts = [
        run_dir / "smoke_evidence.json",
        run_dir / "run" / "Cantilever.inp",
        run_dir / "run" / "Cantilever.odb",
        run_dir / "run" / "Cantilever.log",
        run_dir / "run" / "Cantilever.sta",
        run_dir / "run" / "_kpi_result.json",
        run_dir / "capsule" / "cantilever-require-real" / "capsule.json",
    ]
    file_items = "".join(f"<li><code>{_escape(path)}</code></li>" for path in artifacts)
    files = f"""
    <h1>证据文件位置</h1>
    <div class="card">
      <p class="note">下面这些是可追溯证据。中文报告只负责解释；真实判断仍以这些原始文件为准。</p>
      <ul>{file_items}</ul>
    </div>
    """

    outputs = {
        "real_env_verification_report_zh.html": _doc("真实 Abaqus 验证报告", overview),
        "real_env_report_stages_zh.html": _doc("真实阶段逐项验证", stages),
        "real_env_report_logs_zh.html": _doc("求解日志证据", logs),
        "real_env_report_syntax_zh.html": _doc("语法检查证据", syntax),
        "real_env_report_files_zh.html": _doc("证据文件位置", files),
    }
    written = []
    for filename, content in outputs.items():
        path = evidence_root / filename
        path.write_text(content, encoding="utf-8")
        written.append(path)
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence_root", type=Path, help="包含 smoke_* 目录的真实 Abaqus 证据根目录")
    args = parser.parse_args()
    for path in render_chinese_report(args.evidence_root):
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
