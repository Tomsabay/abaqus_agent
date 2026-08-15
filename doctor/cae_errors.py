"""
cae_errors.py
-------------
Plain-language diagnosis for Abaqus/CAE plugin execution failures.

The Copilot plugin posts raw Python tracebacks when an action fails inside
CAE. Beginners can't read those. This module maps the common failure shapes
to a Chinese explanation + concrete next step, shown in the workspace error
pane above the raw traceback.

Deterministic, no LLM, no Abaqus: safe to run on every action-result POST.

Matching notes:
- First match wins, so specific shapes sit above broad ones.
- Tracebacks from ``exec``-ed action scripts show ``File "<string>"`` with no
  source line, so repository-lookup failures surface as a bare ``KeyError:
  'Name'`` — the broad missing-object pattern near the bottom catches those.
"""

from __future__ import annotations

import re
from typing import Any

_CAE_ERROR_PATTERNS: list[dict[str, str]] = [
    {
        "id": "stale_lock_or_readonly_cae",
        "regex": r"(\.cae['\"]?:?\s*Permission denied|\.lck|database .* is locked|MdbError.*lock)",
        "title": "模型数据库被锁定或无法写入",
        "explanation": "工作目录里残留了上次 CAE 会话崩溃留下的 .lck 锁文件，或者同名 .cae 文件是只读/被别的程序占用。",
        "suggestion": "删除同名 .lck 文件、确认 .cae 可写（没被别的 Abaqus 会话打开）后重新执行计划即可，模型本身没有问题。",
    },
    {
        "id": "license_checkout_failed",
        "regex": r"(license|LICENSE|DSLS|FlexNet|lmgrd)",
        "title": "Abaqus 许可证获取失败",
        "explanation": "CAE 拿不到求解/前处理许可证，通常是许可证服务器不可达或 token 用完。",
        "suggestion": "确认许可证服务器在线（LM_LICENSE_FILE 指向的端口）、token 有空余，再重试。",
    },
    {
        "id": "geometry_selection_failed",
        "regex": r"(could not find the left fixed face|could not find right-end load nodes|could not find the (left|right) support edge nodes|could not find mid-span load nodes|getByBoundingBox)",
        "title": "几何选择失败",
        "explanation": "按坐标框选支撑面/加载点时没有选中任何几何，通常是尺寸参数与实际模型对不上，或网格还没有生成。",
        "suggestion": "检查长/高/宽参数是否与模型一致、确认已生成网格，再重新生成计划。",
    },
    {
        "id": "odb_missing_or_unreadable",
        "regex": r"(OdbError|openOdb|\.odb.*(not|cannot|No such))",
        "title": "找不到或打不开结果文件 (ODB)",
        "explanation": "求解没有正常产出 ODB，多半是作业提交后中途失败了。",
        "suggestion": "查看同目录的 .msg/.sta/.log，把内容粘到 Solver Doctor 面板做求解诊断。",
    },
    {
        "id": "job_aborted",
        "regex": r"(Job .* aborted|job .* aborted|exited with an error|Analysis Input File Processor error)",
        "title": "求解作业中途失败",
        "explanation": "作业提交成功但求解器报错退出了。",
        "suggestion": "看下方的求解日志会诊卡；需要更深入时把 .msg/.dat/.sta 交给 Solver Doctor 面板定位收敛/材料/约束问题。",
    },
    {
        "id": "name_already_in_use",
        "regex": r"(is already in use|already exists)",
        "title": "对象重名",
        "explanation": "要创建的模型/作业/集合等名字已被占用，通常是重复执行了同一个建模动作。",
        "suggestion": "点“让 Copilot 修复”重新生成计划（模板会先删除同名对象），或手动换个名字/删掉旧对象。",
    },
    {
        "id": "feature_creation_failed",
        "regex": r"(FeatureError|Feature creation failed|Cannot continue yet|invalid.*sketch|sketch.*invalid)",
        "title": "几何特征创建失败",
        "explanation": "草图或特征参数自相矛盾（比如尺寸为 0、拉伸方向非法），CAE 拒绝生成几何。",
        "suggestion": "检查几何尺寸是否为正、单位是否一致，然后重新生成计划。",
    },
    {
        "id": "generated_code_syntax_error",
        "regex": r"(SyntaxError|IndentationError)",
        "title": "生成的脚本有语法错误",
        "explanation": "这一步的 Abaqus Python 代码本身写坏了（AI 生成代码偶发问题），还没执行到建模就失败了。",
        "suggestion": "点“让 Copilot 修复”重新生成这一步；如果反复出现请切换到模板演示后端。",
    },
    {
        "id": "api_parameter_mismatch",
        "regex": r"TypeError[\s\S]{0,160}(unexpected keyword argument|takes .* argument|got multiple values|keyword error)",
        "title": "Abaqus API 参数不匹配",
        "explanation": "脚本用的参数名/个数和当前 Abaqus 版本的 API 对不上——不同版本参数名经常有差异。",
        "suggestion": "把报错里的参数名和你的 Abaqus 版本告诉 Copilot 重新生成，或查对应版本的 Scripting Reference。",
    },
    {
        "id": "disk_full",
        "regex": r"(No space left|[Dd]isk (is )?full|ENOSPC)",
        "title": "磁盘空间不足",
        "explanation": "求解器/CAE 写文件时磁盘满了。",
        "suggestion": "清理工作盘（旧的 .odb/.stt/.res 最占空间）后重跑。",
    },
    {
        "id": "file_not_found",
        "regex": r"(No such file or directory|FileNotFoundError|Errno 2\b)",
        "title": "文件或路径不存在",
        "explanation": "脚本要读写的文件不在当前工作目录，常见于换了目录执行或引用了上一次会话的产物。",
        "suggestion": "确认 Abaqus 的工作目录（File → Set Work Directory）和文件名，再重新执行。",
    },
    {
        "id": "permission_denied",
        "regex": r"(Permission denied|Errno 13\b)",
        "title": "文件被占用或没有写权限",
        "explanation": "目标文件被别的程序占用（比如结果文件正被查看器打开）或目录没有写权限。",
        "suggestion": "关掉占用该文件的程序、换一个有写权限的工作目录后重试。",
    },
    {
        "id": "out_of_memory",
        "regex": r"MemoryError",
        "title": "内存不足",
        "explanation": "模型规模超出当前可用内存。",
        "suggestion": "减小网格密度或关掉其他大程序；求解内存问题另见 Solver Doctor 的 MEMORY 建议。",
    },
    {
        "id": "section_or_material_missing",
        "regex": r"(without section|missing property definition|no section assigned|section .* not (been )?assigned)",
        "title": "单元缺少截面/材料",
        "explanation": "有单元没有赋截面（或截面没绑材料），求解前的一致性检查不通过。",
        "suggestion": "确认建模动作里的 SectionAssignment 覆盖了所有区域，重新从第 1 步执行完整计划。",
    },
    {
        # exec-ed scripts show File "<string>" with no source line, so a missing
        # model/part/instance/set lookup surfaces as a bare KeyError.
        "id": "model_or_part_missing",
        "regex": r"(KeyError|NameError[\s\S]{0,80}COPILOT_|NameError.*not defined)",
        "title": "找不到引用的对象（模型/部件/实例/集合）",
        "explanation": "这个动作引用的对象还不存在——通常是前面的建模动作没有执行、执行失败，或者换了新的 CAE 会话。",
        "suggestion": "从第 1 步重新执行完整计划（先建模再加边界条件），不要单独跳步执行。",
    },
]


def diagnose_cae_traceback(traceback_text: str) -> dict[str, Any]:
    """Map a CAE plugin traceback to a plain-language diagnosis.

    Always returns a dict; ``matched`` is False when no known shape fits,
    in which case the last traceback line is surfaced as-is.
    """
    text = (traceback_text or "").strip()
    last_line = text.splitlines()[-1].strip() if text else ""
    for pattern in _CAE_ERROR_PATTERNS:
        if re.search(pattern["regex"], text, flags=re.IGNORECASE):
            return {
                "matched": True,
                "pattern_id": pattern["id"],
                "title": pattern["title"],
                "explanation": pattern["explanation"],
                "suggestion": pattern["suggestion"],
                "error_line": last_line,
            }
    return {
        "matched": False,
        "pattern_id": "unknown",
        "title": "未识别的 CAE 执行错误",
        "explanation": "这个报错还不在已知模式库里。",
        "suggestion": "点击“让 Copilot 修复”，把完整 traceback 交给 Copilot 重新规划；如果反复出现请反馈，我们会加入模式库。",
        "error_line": last_line,
    }


def list_cae_error_patterns() -> list[dict[str, str]]:
    """Expose the pattern catalog (for docs/tests/UI galleries)."""
    return [dict(pattern) for pattern in _CAE_ERROR_PATTERNS]
