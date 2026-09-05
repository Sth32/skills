#!/usr/bin/env python3
"""Minimal static validator for this repository's Agent Skills."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = ROOT / "skills"
NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
DOCUMENT_TIMING_RULE = (
    "**文档更新时序硬限制：任何新事实、确认、执行结果或验证结果只要改变本阶段内容，必须在同一轮立即原位更新本阶段唯一文档，并明确告知用户已更新的文件路径；不得等到阶段结束、批次结束或用户再次提醒。发现结"
    "论会改变更早阶段文档时，必须主动说明受影响文档和拟修改内容，先获得用户确认，再更新上游文档；未确认前不得静默改写。**"
)

DOCUMENT_IMPACT_RULE = (
    "**结构性变更影响传播硬限制：当范围、阶段状态、接口/RPC/事件合同、数据权威、工作单元依赖或配置真源发生变化时，必须在同一轮执行影响扫描，不得只修当前局部段落。当前阶段文档内至少核对顶部元信息、相"
    "关正文规则/矩阵、验证结论、阻塞与下一动作；同时定位已有且实际依赖该事实的上下游阶段文档、客户端合同与 `00-工作流索引.md` 中的旧引用。当前阶段和本 skill 允许直接维护的下游内容立即原位"
    "更新；若受影响的是需要用户确认才能改写的上游文档，必须明确列出受影响文件、旧事实与拟修改内容并等待确认，不得静默遗漏，也不得把未传播完成的结构性变化描述为已闭环。**"
)

DOCUMENT_CONSISTENCY_RULE = (
    "**阶段完成一致性硬限制：在宣布本阶段完成、确认或移交前，必须对本阶段权威文档做一次一致性收敛。同一事项不得同时保留互斥的当前状态、数值、操作要求或验证结论；发现冲突时，必须依据最新用户确认、实际源、"
    "代码或配置、生成物以及验证证据判定唯一当前事实并原位改写，删除被覆盖、错误、过时或仅用于过程追踪的内容。若证据不足无法判定，则该事项保持未完成或阻塞，只保留唯一待确认点，不得以“已完成”结束阶段。**"
)

DOCUMENT_RECORD_RULE = '**内置记录硬限制：每次逻辑上的文档变更完成后，只执行当前 skill 自带的 `scripts/document_record.py append`，提交本次变更的最小结构化事实；写入器完整实现随 skill 分发，但记录数据仍存放在仓库外。普通开发 Agent 必须把写入器当作只写接口：不得打开、读取、搜索或修改写入器源码，不得查找、定位、读取、搜索、解析或直接修改任何历史记录或记录文件，也不得为了写记录扫描工作区中的 record 文件。同一原因、同一轮的原子变更只提交一次，携带实际变化文档、trigger、reason、change summary、validation、outcome 与必要 feedback；正常进度不得虚构问题、根因或预防建议。用户改变需求使用 `user_change`，用户指出 Agent/文档错误使用 `user_correction`。写入器不可用或失败时，明确报告记录未写入，但不得通过 shell 重定向、通用文本 API 或直接文件操作绕过写入器。**'

LIGHTWEIGHT_SKILLS = frozenset(
    {
        "game-bugfix",
        "game-small-change",
        "game-refactor",
        "game-light-review",
        "game-hotfix",
    }
)
LIGHTWEIGHT_DOC_MARKER = "## 文档"
LIGHTWEIGHT_DEV_MARKER = "开发期默认"
HOTFIX_PREREQUISITE_MARKER = "## 使用前提"
HOTFIX_USER_CONFIRM_MARKER = "Agent 不得自行判断“项目已经上线”"
HOTFIX_DECOUPLING_MARKER = "不是 Hotfix 发布框架、事故响应流程或项目基础设施规范"

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
SPEC_BRANCH_RULE_MARKER = "**需求分支硬限制："
REVIEW_INDEPENDENT_RULE_MARKER = "**独立 Review 硬限制："
REVIEW_INTEGRATION_RULE_MARKER = "**整体 Review 硬限制："
BRANCH_INDEX_NAME = "00-工作流索引.md"
REVIEW_BRANCH_DOC_MARKER = "07-<Uxx>-<主题>-交叉评审.md"

TARGETED_RULE_MARKERS = {
    "game-tech-clarify": "**跨边界通信合同硬限制：",
    "game-scaffold": "**框架真实链路硬限制：",
    "game-implement": "**真实消费链验证硬限制：",
    "game-client-handoff": "**客户端合同可达性硬限制：",
}

REQUIRED_REPO_FILES = (
    "docs/skill-development/document-change-record.md",
    "docs/skill-development/branch-workflow.md",
    "docs/skill-development/maintenance-workflow.md",
    "evals/branch-workflow.md",
    "evals/maintenance-workflow.md",
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

    if name in LIGHTWEIGHT_SKILLS:
        if LIGHTWEIGHT_DOC_MARKER not in text:
            errors.append("lightweight maintenance skill must define optional documentation behavior")
        if "01–07" not in text:
            errors.append("lightweight maintenance skill must explicitly distinguish itself from the formal 01–07 workflow")
        if name == "game-hotfix":
            if HOTFIX_PREREQUISITE_MARKER not in text:
                errors.append("game-hotfix must define its production-use prerequisite")
            if HOTFIX_USER_CONFIRM_MARKER not in text:
                errors.append("game-hotfix must require user confirmation of production status")
            if HOTFIX_DECOUPLING_MARKER not in text:
                errors.append("game-hotfix must remain decoupled from project-specific hotfix infrastructure")
        elif LIGHTWEIGHT_DEV_MARKER not in text:
            errors.append("non-hotfix lightweight skill must define development-environment handling")
    else:
        if DOCUMENT_TIMING_RULE not in text:
            errors.append("missing canonical stage-document update timing rule")
        if DOCUMENT_IMPACT_RULE not in text:
            errors.append("missing canonical structural-change impact propagation rule")
        if DOCUMENT_CONSISTENCY_RULE not in text:
            errors.append("missing canonical stage-completion consistency rule")

    if DOCUMENT_RECORD_RULE not in text:
        errors.append("missing canonical bundled record rule")
    writer = skill_dir / "scripts" / "document_record.py"
    if not writer.is_file():
        errors.append("missing bundled document recorder")

    targeted_marker = TARGETED_RULE_MARKERS.get(name)
    if targeted_marker and targeted_marker not in text:
        errors.append("missing targeted cross-layer contract/runtime-chain rule")

    if name == "game-spec":
        if SPEC_BRANCH_RULE_MARKER not in text:
            errors.append("missing requirement-stage branch rule")
        if "01-Uxx" not in text or BRANCH_INDEX_NAME not in text:
            errors.append("game-spec must support requirement-stage work units and workflow index")

    if name in BRANCHABLE_SKILLS:
        if BRANCH_RULE_MARKER not in text:
            errors.append("missing branch-workflow rule")
        if BRANCH_INDEX_NAME not in text:
            errors.append("branchable skill must reference the workflow index")
        if "禁止" not in text or "子目录" not in text:
            errors.append("branchable skill must explicitly forbid branch subdirectories")

    if name == "game-review":
        if REVIEW_INDEPENDENT_RULE_MARKER not in text:
            errors.append("missing independent work-unit review rule")
        if REVIEW_INTEGRATION_RULE_MARKER not in text:
            errors.append("missing optional integration-review rule")
        if BRANCH_INDEX_NAME not in text:
            errors.append("game-review must understand branched workflow indexes")
        if REVIEW_BRANCH_DOC_MARKER not in text:
            errors.append("game-review must define per-work-unit 07 review documents")

    if name == "game-docs" and BRANCH_INDEX_NAME not in text:
        errors.append("game-docs must locate reviewed branch inputs through the workflow index")

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
