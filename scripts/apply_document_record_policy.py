#!/usr/bin/env python3
"""Apply canonical stage-document policies across this repository."""

from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = ROOT / "skills"
README = ROOT / "README.md"
VALIDATOR = ROOT / "scripts" / "validate_skills.py"
CANONICAL_WRITER = ROOT / "scripts" / "document_record.py"
BUNDLED_WRITER_RELATIVE = Path("scripts/document_record.py")

DOCUMENT_TIMING_RULE = (
    "**文档更新时序硬限制：任何新事实、确认、执行结果或验证结果只要改变本阶段内容，"
    "必须在同一轮立即原位更新本阶段唯一文档，并明确告知用户已更新的文件路径；"
    "不得等到阶段结束、批次结束或用户再次提醒。发现结论会改变更早阶段文档时，"
    "必须主动说明受影响文档和拟修改内容，先获得用户确认，再更新上游文档；"
    "未确认前不得静默改写。**"
)

DOCUMENT_CONSISTENCY_RULE = (
    "**阶段完成一致性硬限制：在宣布本阶段完成、确认或移交前，必须对本阶段权威文档做一次一致性收敛。"
    "同一事项不得同时保留互斥的当前状态、数值、操作要求或验证结论；发现冲突时，必须依据最新用户确认、"
    "实际源、代码或配置、生成物以及验证证据判定唯一当前事实并原位改写，删除被覆盖、错误、过时或仅用于过程追踪的内容。"
    "若证据不足无法判定，则该事项保持未完成或阻塞，只保留唯一待确认点，不得以“已完成”结束阶段。**"
)

DOCUMENT_RECORD_RULE = (
    "**文档变更记录硬限制：每次创建、修改、删除或重命名本阶段文档后，必须在目标文档所在目录的 "
    "`record.jsonl` 追加一条 JSON 记录；`record.jsonl` 是审计元数据，不属于阶段过程文档，记录文件自身的追加不触发再次记录。"
    "新记录使用 schema v3，并区分“实际使用 skill”和“未使用 skill”：只要当前 Agent 实际加载/执行了本 skill（即使用户没有显式写出 skill 名称），"
    "就必须调用本 skill 自带的 `scripts/document_record.py append --skill <当前skill>`，写入 `skill_usage=used`，"
    "`skill_version` 由写入器从当前 `SKILL.md` 的 `metadata.version` 自动读取，禁止 Agent 手填、猜测或沿用历史值；"
    "若一次变更实际没有使用任何 skill，才可使用 `--no-skill`，写入 `skill_usage=not_used`、`skill=null`、`skill_version=null`，"
    "不得挑选一个“最接近”的 skill 冒充来源。用户是否显式声明 skill 不是归因依据，实际是否加载/执行才是。"
    "写入器 append 前只校验已有文件仍可逐行解析为 UTF-8 JSON object；历史行的 schema 字段缺失或语义错误（例如旧 schema v2 缺少 `skill_version`）"
    "必须由 `check` 报告，但不得阻塞后续独立追加，也不得静默修改旧行；只有非 UTF-8、非法 JSON、非 object 等存储层损坏才拒绝 append。"
    "历史 schema v1 或非法 v2 无版本记录在查询和统计时统一视为 `skill_version=unknown`；no-skill v3 视为 `skill=none`、"
    "`skill_version=not_applicable`，不得回填猜测版本。禁止使用 `>`、`>>`、`echo`、PowerShell "
    "`Add-Content`/`Set-Content`/`Out-File` 或通用文本写入 API 直接修改 `record.jsonl`，脚本失败时也不得降级绕过。"
    "记录至少包含时间、skill usage、skill/版本归因、运行环境、模型、思考等级、动作、文档路径、触发原因、问题与根因、修改摘要、验证结果、"
    "结果状态和预防建议；无法获知的模型、思考等级或运行环境写 `unknown`，不得猜测。评估滚动更新的 skill 时必须只使用 "
    "`skill_usage=used` 且按 `skill_version` 过滤或分组，不能把 no-skill、版本未知或多个版本直接混为同一版本效果。"
    "禁止写入完整提示词、文档正文、用户敏感信息或思维过程。需要评审记录时，只能按条件查询或读取最近有限条目，不得把全文注入上下文。**"
)

TIMING_RULE_RE = re.compile(r"(\*\*文档更新时序硬限制：.*?\*\*)", re.DOTALL)
CONSISTENCY_RULE_RE = re.compile(r"\*\*阶段完成一致性硬限制：.*?\*\*", re.DOTALL)
RECORD_RULE_RE = re.compile(r"\*\*文档变更记录硬限制：.*?\*\*", re.DOTALL)
VERSION_RE = re.compile(r'(\n\s*version:\s*")(\d+)\.(\d+)\.(\d+)("\s*\n)')
VALIDATOR_RULE_BLOCK_RE = re.compile(
    r"DOCUMENT_TIMING_RULE = \(\n.*?\n\)\n+"
    r"DOCUMENT_CONSISTENCY_RULE = \(\n.*?\n\)\n+"
    r"DOCUMENT_RECORD_RULE = \(\n.*?\n\)",
    re.DOTALL,
)

README_VALIDATOR_PARAGRAPH = (
    "验证器会要求每个 `SKILL.md` 包含统一的文档更新、阶段完成一致性与记录硬限制；"
    "对 `02`–`06` 和客户端对接技能额外检查分支工作流协议，对 `game-review` 检查 07 汇合协议，"
    "并检查每个 skill 自带的 UTF-8 写入器与仓库规范版本完全一致。"
)


def bump_patch_version(text: str) -> str:
    match = VERSION_RE.search(text)
    if not match:
        raise ValueError("missing semantic metadata version")
    major, minor, patch = map(int, match.group(2, 3, 4))
    replacement = f'{match.group(1)}{major}.{minor}.{patch + 1}{match.group(5)}'
    return text[: match.start()] + replacement + text[match.end() :]


def patch_skill(text: str, path: Path) -> str:
    changed = False

    if DOCUMENT_CONSISTENCY_RULE not in text:
        if CONSISTENCY_RULE_RE.search(text):
            text = CONSISTENCY_RULE_RE.sub(DOCUMENT_CONSISTENCY_RULE, text, count=1)
        else:
            timing = TIMING_RULE_RE.search(text)
            if not timing:
                raise ValueError(f"{path}: missing document timing rule anchor")
            text = text[: timing.end()] + "\n\n" + DOCUMENT_CONSISTENCY_RULE + text[timing.end() :]
        changed = True

    if DOCUMENT_RECORD_RULE not in text:
        if RECORD_RULE_RE.search(text):
            text = RECORD_RULE_RE.sub(DOCUMENT_RECORD_RULE, text, count=1)
        else:
            consistency = CONSISTENCY_RULE_RE.search(text)
            if not consistency:
                raise ValueError(f"{path}: missing document consistency rule anchor")
            text = text[: consistency.end()] + "\n\n" + DOCUMENT_RECORD_RULE + text[consistency.end() :]
        changed = True

    return bump_patch_version(text) if changed else text


def insert_rule_after_heading(text: str, heading: str, rule: str, label: str) -> str:
    anchor = heading + "\n"
    if anchor not in text:
        raise ValueError(f"README: {label} section anchor not found")
    return text.replace(anchor, anchor + "\n" + rule + "\n", 1)


def patch_readme(text: str) -> str:
    if DOCUMENT_RECORD_RULE not in text:
        if RECORD_RULE_RE.search(text):
            text = RECORD_RULE_RE.sub(DOCUMENT_RECORD_RULE, text, count=1)
        else:
            text = insert_rule_after_heading(
                text, "## 文档变更记录", DOCUMENT_RECORD_RULE, "document record"
            )

    if DOCUMENT_CONSISTENCY_RULE not in text:
        if CONSISTENCY_RULE_RE.search(text):
            text = CONSISTENCY_RULE_RE.sub(DOCUMENT_CONSISTENCY_RULE, text, count=1)
        else:
            text = insert_rule_after_heading(
                text, "## 阶段完成一致性收敛", DOCUMENT_CONSISTENCY_RULE, "consistency"
            )

    if README_VALIDATOR_PARAGRAPH not in text:
        validation_re = re.compile(
            r"验证器会要求每个 `SKILL\.md` 包含.*?(?=\n\n`evals/)",
            re.DOTALL,
        )
        if not validation_re.search(text):
            raise ValueError("README: validator description anchor not found")
        text = validation_re.sub(README_VALIDATOR_PARAGRAPH, text, count=1)

    return text


def validator_constant(name: str, value: str) -> str:
    escaped_parts: list[str] = []
    remaining = value
    while remaining:
        part, remaining = remaining[:100], remaining[100:]
        escaped = part.replace("\\", "\\\\").replace('"', '\\"')
        escaped_parts.append(f'    "{escaped}"')
    return f"{name} = (\n" + "\n".join(escaped_parts) + "\n)"


def read_string_constants(text: str, names: set[str]) -> dict[str, str]:
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        raise ValueError(f"validator: invalid Python syntax: {exc}") from exc

    result: dict[str, str] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name) or target.id not in names:
            continue
        try:
            value = ast.literal_eval(node.value)
        except (ValueError, TypeError) as exc:
            raise ValueError(f"validator: {target.id} is not a literal string") from exc
        if not isinstance(value, str):
            raise ValueError(f"validator: {target.id} is not a string")
        result[target.id] = value
    return result


def patch_validator(text: str) -> str:
    expected = {
        "DOCUMENT_TIMING_RULE": DOCUMENT_TIMING_RULE,
        "DOCUMENT_CONSISTENCY_RULE": DOCUMENT_CONSISTENCY_RULE,
        "DOCUMENT_RECORD_RULE": DOCUMENT_RECORD_RULE,
    }
    actual = read_string_constants(text, set(expected))
    if actual != expected:
        rule_block = (
            validator_constant("DOCUMENT_TIMING_RULE", DOCUMENT_TIMING_RULE)
            + "\n\n"
            + validator_constant("DOCUMENT_CONSISTENCY_RULE", DOCUMENT_CONSISTENCY_RULE)
            + "\n\n"
            + validator_constant("DOCUMENT_RECORD_RULE", DOCUMENT_RECORD_RULE)
        )
        if not VALIDATOR_RULE_BLOCK_RE.search(text):
            raise ValueError("validator: canonical rule block not found")
        text = VALIDATOR_RULE_BLOCK_RE.sub(rule_block, text, count=1)

    if 'CANONICAL_RECORD_WRITER = ROOT / "scripts" / "document_record.py"' not in text:
        anchor = 'SKILLS_DIR = ROOT / "skills"\n'
        if anchor not in text:
            raise ValueError("validator: skills-dir anchor not found")
        text = text.replace(
            anchor,
            anchor + 'CANONICAL_RECORD_WRITER = ROOT / "scripts" / "document_record.py"\n',
            1,
        )

    required_snippet = (
        '    bundled_writer = skill_dir / "scripts" / "document_record.py"\n'
        '    if not bundled_writer.is_file():\n'
        '        errors.append("missing bundled UTF-8 document record writer")\n'
        '    elif bundled_writer.read_bytes() != CANONICAL_RECORD_WRITER.read_bytes():\n'
        '        errors.append("bundled document record writer differs from canonical writer")\n'
    )
    if required_snippet not in text:
        anchor = (
            '    if DOCUMENT_RECORD_RULE not in text:\n'
            '        errors.append("missing canonical document change record rule")\n'
        )
        if anchor not in text:
            raise ValueError("validator: record-rule check anchor not found")
        text = text.replace(anchor, anchor + required_snippet, 1)
    return text


def write_text_if_changed(path: Path, new_text: str, *, check: bool) -> bool:
    old_text = path.read_text(encoding="utf-8")
    if old_text == new_text:
        return False
    if not check:
        path.write_text(new_text, encoding="utf-8", newline="\n")
    return True


def write_bytes_if_changed(path: Path, new_bytes: bytes, *, check: bool) -> bool:
    old_bytes = path.read_bytes() if path.exists() else None
    if old_bytes == new_bytes:
        return False
    if not check:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(new_bytes)
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    changed: list[Path] = []
    try:
        writer_bytes = CANONICAL_WRITER.read_bytes()
        for skill_file in sorted(SKILLS_DIR.glob("*/SKILL.md")):
            old = skill_file.read_text(encoding="utf-8")
            new = patch_skill(old, skill_file)
            if write_text_if_changed(skill_file, new, check=args.check):
                changed.append(skill_file)

            bundled_writer = skill_file.parent / BUNDLED_WRITER_RELATIVE
            if write_bytes_if_changed(bundled_writer, writer_bytes, check=args.check):
                changed.append(bundled_writer)

        old_readme = README.read_text(encoding="utf-8")
        if write_text_if_changed(README, patch_readme(old_readme), check=args.check):
            changed.append(README)

        old_validator = VALIDATOR.read_text(encoding="utf-8")
        if write_text_if_changed(VALIDATOR, patch_validator(old_validator), check=args.check):
            changed.append(VALIDATOR)
    except (OSError, ValueError) as exc:
        print(f"policy application failed: {exc}", file=sys.stderr)
        return 2

    if changed:
        prefix = "NEEDS UPDATE" if args.check else "UPDATED"
        for path in changed:
            print(f"{prefix} {path.relative_to(ROOT)}")
        return 1 if args.check else 0

    print("Stage document policy is up to date.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
