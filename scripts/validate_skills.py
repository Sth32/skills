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
    "**文档更新时序硬限制：任何新事实、确认、执行结果或验证结果只要改变本阶段内容，"
    "必须在同一轮立即原位更新本阶段唯一文档，并明确告知用户已更新的文件路径；"
    "不得等到阶段结束、批次结束或用户再次提醒。发现结论会改变更早阶段文档时，"
    "必须主动说明受影响文档和拟修改内容，先获得用户确认，再更新上游文档；"
    "未确认前不得静默改写。**"
)


DOCUMENT_RECORD_RULE = (
    "**文档变更记录硬限制：每次创建、修改、删除或重命名本阶段文档后，必须在目标文档所在目录的 `record.jsonl` 追加一条 JSON 记录；`record.jsonl` 是审计元数据，不属于阶"
    "段过程文档，记录文件自身的追加不触发再次记录。写入必须调用本 skill 自带的 `scripts/document_record.py append`；该脚本使用 UTF-8（无 BOM）字节单次追"
    "加，并在追加前静默校验已有文件仍是 UTF-8 JSONL。禁止使用 `>`、`>>`、`echo`、PowerShell `Add-Content`/`Set-Content`/`Out-File`"
    " 或通用文本写入 API 直接修改 `record.jsonl`，脚本失败时也不得降级绕过；找不到脚本、现有文件编码异常或追加失败时，必须明确告知用户并停止记录写入。记录至少包含时间、skill、运行"
    "环境、模型、思考等级、动作、文档路径、触发原因、问题与根因、修改摘要、验证结果、结果状态和预防建议；无法获知的模型、思考等级或运行环境写 `unknown`，不得猜测。禁止写入完整提示词、文档正文、用"
    "户敏感信息或思维过程。需要评审记录时，只能按条件查询或读取最近有限条目，不得把全文注入上下文。**"
)
REQUIRED_DOCUMENT_RECORD_FILES = (
    "scripts/document_record.py",
    "docs/skill-development/document-change-record.md",
    "evals/document-recording.md",
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
    if DOCUMENT_RECORD_RULE not in text:
        errors.append("missing canonical document change record rule")
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
    for relative_path in REQUIRED_DOCUMENT_RECORD_FILES:
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
