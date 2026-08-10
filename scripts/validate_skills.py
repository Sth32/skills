#!/usr/bin/env python3
"""Minimal static validator for this repository's Agent Skills."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = ROOT / "skills"
CANONICAL_RECORD_WRITER = ROOT / "scripts" / "document_record.py"
NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
DOCUMENT_TIMING_RULE = (
    "**文档更新时序硬限制：任何新事实、确认、执行结果或验证结果只要改变本阶段内容，必须在同一轮立即原位更新本阶段唯一文档，并明确告知用户已更新的文件路径；不得等到阶段结束、批次结束或用户再次提醒。发现结"
    "论会改变更早阶段文档时，必须主动说明受影响文档和拟修改内容，先获得用户确认，再更新上游文档；未确认前不得静默改写。**"
)

DOCUMENT_CONSISTENCY_RULE = (
    "**阶段完成一致性硬限制：在宣布本阶段完成、确认或移交前，必须对本阶段权威文档做一次一致性收敛。同一事项不得同时保留互斥的当前状态、数值、操作要求或验证结论；发现冲突时，必须依据最新用户确认、实际源、"
    "代码或配置、生成物以及验证证据判定唯一当前事实并原位改写，删除被覆盖、错误、过时或仅用于过程追踪的内容。若证据不足无法判定，则该事项保持未完成或阻塞，只保留唯一待确认点，不得以“已完成”结束阶段。**"
)

DOCUMENT_RECORD_RULE = (
    "**文档变更记录硬限制：每次创建、修改、删除或重命名本阶段文档后，必须在目标文档所在目录的 `record.jsonl` 追加一条 JSON 记录；`record.jsonl` 是审计元数据，不属于阶"
    "段过程文档，记录文件自身的追加不触发再次记录。新记录使用 schema v3，并区分“实际使用 skill”和“未使用 skill”：只要当前 Agent 实际加载/执行了本 skill（即使用户没有"
    "显式写出 skill 名称），就必须调用本 skill 自带的 `scripts/document_record.py append --skill <当前skill>`，写入 `skill_usag"
    "e=used`，`skill_version` 由写入器从当前 `SKILL.md` 的 `metadata.version` 自动读取，禁止 Agent 手填、猜测或沿用历史值；若一次变更实际没有使"
    "用任何 skill，才可使用 `--no-skill`，写入 `skill_usage=not_used`、`skill=null`、`skill_version=null`，不得挑选一个“最接近”的"
    " skill 冒充来源。用户是否显式声明 skill 不是归因依据，实际是否加载/执行才是。写入器 append 前只校验已有文件仍可逐行解析为 UTF-8 JSON object；历史行的 sche"
    "ma 字段缺失或语义错误（例如旧 schema v2 缺少 `skill_version`）必须由 `check` 报告，但不得阻塞后续独立追加，也不得静默修改旧行；只有非 UTF-8、非法 JSON"
    "、非 object 等存储层损坏才拒绝 append。历史 schema v1 或非法 v2 无版本记录在查询和统计时统一视为 `skill_version=unknown`；no-skill v3 "
    "视为 `skill=none`、`skill_version=not_applicable`，不得回填猜测版本。禁止使用 `>`、`>>`、`echo`、PowerShell `Add-Content"
    "`/`Set-Content`/`Out-File` 或通用文本写入 API 直接修改 `record.jsonl`，脚本失败时也不得降级绕过。记录至少包含时间、skill usage、skill/版"
    "本归因、运行环境、模型、思考等级、动作、文档路径、触发原因、问题与根因、修改摘要、验证结果、结果状态和预防建议；无法获知的模型、思考等级或运行环境写 `unknown`，不得猜测。评估滚动更新的 sk"
    "ill 时必须只使用 `skill_usage=used` 且按 `skill_version` 过滤或分组，不能把 no-skill、版本未知或多个版本直接混为同一版本效果。禁止写入完整提示词、文档"
    "正文、用户敏感信息或思维过程。需要评审记录时，只能按条件查询或读取最近有限条目，不得把全文注入上下文。**"
)

BRANCHABLE_SKILLS = frozenset(
    {
        "game-discovery",
        "game-tech-clarify",
        "game-config",
        "game-scaffold",
        "game-implement",
        "game-client-handoff",
    }
)
BRANCH_RULE_MARKER = "**分支工作流硬限制："
SPEC_ROOT_RULE_MARKER = "**根文档硬限制："
REVIEW_MERGE_RULE_MARKER = "**Review 汇合硬限制："
BRANCH_INDEX_NAME = "00-工作流索引.md"
REVIEW_BRANCH_FORBIDDEN_MARKER = "禁止创建 `07-Uxx-*`"

REQUIRED_REPO_FILES = (
    "scripts/document_record.py",
    "docs/skill-development/document-change-record.md",
    "evals/document-recording.md",
    "docs/skill-development/branch-workflow.md",
    "evals/branch-workflow.md",
)


def parse_frontmatter(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValueError("missing opening YAML frontmatter delimiter")
    try:
        _, raw, _ = text.split("---", 2)
    except ValueError as exc:
        raise ValueError("missing closing YAML frontmatter delimiter") from exc

    result: dict[str, str] = {}
    for line in raw.splitlines():
        if not line or line.startswith(" ") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        result[key.strip()] = value.strip().strip('"')
    return result


def validate_skill(skill_dir: Path) -> list[str]:
    errors: list[str] = []
    skill_file = skill_dir / "SKILL.md"
    if not skill_file.is_file():
        return ["missing SKILL.md"]

    text = skill_file.read_text(encoding="utf-8")

    try:
        fm = parse_frontmatter(skill_file)
    except ValueError as exc:
        return [str(exc)]

    name = fm.get("name", "")
    description = fm.get("description", "")

    if name != skill_dir.name:
        errors.append(f"name '{name}' does not match directory '{skill_dir.name}'")
    if not NAME_RE.fullmatch(name):
        errors.append("name must contain lowercase letters, numbers, and single hyphens only")
    if not 1 <= len(name) <= 64:
        errors.append("name length must be 1-64 characters")
    if not 1 <= len(description) <= 1024:
        errors.append("description length must be 1-1024 characters")
    if DOCUMENT_TIMING_RULE not in text:
        errors.append("missing canonical stage-document update timing rule")
    if DOCUMENT_CONSISTENCY_RULE not in text:
        errors.append("missing canonical stage-completion consistency rule")
    if DOCUMENT_RECORD_RULE not in text:
        errors.append("missing canonical document change record rule")

    if name == "game-spec":
        if SPEC_ROOT_RULE_MARKER not in text:
            errors.append("missing original-requirement single-root rule")
        if "01-Uxx" not in text:
            errors.append("game-spec must explicitly forbid branched 01 documents")

    if name in BRANCHABLE_SKILLS:
        if BRANCH_RULE_MARKER not in text:
            errors.append("missing branch-workflow rule")
        if BRANCH_INDEX_NAME not in text:
            errors.append("branchable skill must reference the workflow index")
        if "禁止" not in text or "子目录" not in text:
            errors.append("branchable skill must explicitly forbid branch subdirectories")

    if name == "game-review":
        if REVIEW_MERGE_RULE_MARKER not in text:
            errors.append("missing mandatory review convergence rule")
        if BRANCH_INDEX_NAME not in text:
            errors.append("game-review must understand branched workflow indexes")
        if REVIEW_BRANCH_FORBIDDEN_MARKER not in text:
            errors.append("game-review must explicitly forbid 07-Uxx review documents")

    if name == "game-docs" and BRANCH_INDEX_NAME not in text:
        errors.append("game-docs must locate converged branch inputs through the workflow index")

    bundled_writer = skill_dir / "scripts" / "document_record.py"
    if not bundled_writer.is_file():
        errors.append("missing bundled UTF-8 document record writer")
    elif bundled_writer.read_bytes() != CANONICAL_RECORD_WRITER.read_bytes():
        errors.append("bundled document record writer differs from canonical writer")

    line_count = len(text.splitlines())
    if line_count > 500:
        errors.append(f"SKILL.md has {line_count} lines; recommended maximum is 500")

    return errors


def main() -> int:
    failed = False
    for relative_path in REQUIRED_REPO_FILES:
        if not (ROOT / relative_path).is_file():
            failed = True
            print(f"FAIL missing required file: {relative_path}")
    for skill_dir in sorted(path for path in SKILLS_DIR.iterdir() if path.is_dir()):
        errors = validate_skill(skill_dir)
        if errors:
            failed = True
            print(f"FAIL {skill_dir.name}")
            for error in errors:
                print(f"  - {error}")
        else:
            print(f"PASS {skill_dir.name}")

    if failed:
        return 1
    print("All skills passed static validation.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
