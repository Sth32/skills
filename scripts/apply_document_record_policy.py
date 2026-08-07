#!/usr/bin/env python3
"""Apply canonical stage-document policies across this repository."""

from __future__ import annotations

import argparse
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
    "写入必须调用本 skill 自带的 `scripts/document_record.py append`；该脚本使用 UTF-8（无 BOM）字节单次追加，并在追加前静默校验已有文件仍是 UTF-8 JSONL。"
    "禁止使用 `>`、`>>`、`echo`、PowerShell `Add-Content`/`Set-Content`/`Out-File` 或通用文本写入 API 直接修改 `record.jsonl`，脚本失败时也不得降级绕过；"
    "找不到脚本、现有文件编码异常或追加失败时，必须明确告知用户并停止记录写入。记录至少包含时间、skill、运行环境、模型、思考等级、动作、"
    "文档路径、触发原因、问题与根因、修改摘要、验证结果、结果状态和预防建议；无法获知的模型、思考等级或运行环境写 `unknown`，不得猜测。"
    "禁止写入完整提示词、文档正文、用户敏感信息或思维过程。需要评审记录时，只能按条件查询或读取最近有限条目，不得把全文注入上下文。**"
)

TIMING_RULE_RE = re.compile(r"(\*\*文档更新时序硬限制：.*?\*\*)", re.DOTALL)
CONSISTENCY_RULE_RE = re.compile(r"\*\*阶段完成一致性硬限制：.*?\*\*", re.DOTALL)
RECORD_RULE_RE = re.compile(r"\*\*文档变更记录硬限制：.*?\*\*", re.DOTALL)
VERSION_RE = re.compile(r'(\n\s*version:\s*")(\d+)\.(\d+)\.(\d+)("\s*\n)')
VALIDATOR_RULE_BLOCK_RE = re.compile(
    r"DOCUMENT_TIMING_RULE = \(\n.*?\n\)\n+DOCUMENT_RECORD_RULE = \(\n.*?\n\)\nREQUIRED_DOCUMENT_RECORD_FILES =",
    re.DOTALL,
)

README_RECORD_SECTION = f"""## 文档变更记录

每个文档目录维护一个 append-only 的 `record.jsonl`，用于把实际失误、修正原因和验证结果反馈给 skill 开发者。它是审计元数据，不是第二份阶段文档，因此不违反“一个阶段一份权威文档”。

{DOCUMENT_RECORD_RULE}

每个 skill 目录都自带同一份 UTF-8 写入器。即使只复制单个 `skills/<skill-name>/` 目录，也必须使用该 skill 内的脚本，不得退回 Shell 追加：

```bash
python <skill-root>/scripts/document_record.py append --record docs/requirements/<feature>/record.jsonl \\
  --skill game-spec --runtime codex-cli --model gpt-5.6 --reasoning-effort high \\
  --action update --document docs/requirements/<feature>/01-原始需求.md \\
  --trigger user_feedback --problem "预期同一规则只出现一次，实际在多个章节重复" \\
  --root-cause "固定分类标题拆散同一问题" \\
  --change "合并规则并删除重复内容" \\
  --validation-status passed --validation "语义去重检查通过" \\
  --outcome success --improvement-target eval \\
  --prevention "增加重复事实回归场景"
```

查询时禁止全文读取。只允许有限尾部查询或流式聚合：

```bash
python <skill-root>/scripts/document_record.py check --record <path>/record.jsonl
python <skill-root>/scripts/document_record.py query --record <path>/record.jsonl --tail 20 --skill game-spec
python <skill-root>/scripts/document_record.py stats --record <path>/record.jsonl
```

`append` 会在进程内部流式校验已有文件，但不会把历史内容返回给 Agent。发现旧文件不是 UTF-8 JSONL 时必须停止追加并报告，不能继续制造混合编码；历史修复应作为一次显式迁移处理。

记录的目标不是保存操作流水，而是形成可执行反馈。当前暂不收紧记录触发范围；`problem` 应尽量写清预期与实际差异，`validation.evidence` 保存修复后的最小验证证据，`improvement.prevention` 写防复发机制而不是项目待办。

"""

README_CONSISTENCY_SECTION = f"""## 阶段完成一致性收敛

{DOCUMENT_CONSISTENCY_RULE}

阶段文档承担的是“当前真相”，不是过程日志。历史尝试、旧状态和被新证据推翻的判断依赖 Git、diff、日志或 `record.jsonl` 追溯；正文只保留会影响后续决策和执行的唯一当前事实。

"""


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


def patch_readme(text: str) -> str:
    if "└── record.jsonl" not in text:
        old_tree = (
            "├── <主题名>-客户端对接文档.md（独立对接阶段，按需）\n"
            "└── 07-交叉评审.md"
        )
        new_tree = (
            "├── <主题名>-客户端对接文档.md（独立对接阶段，按需）\n"
            "├── 07-交叉评审.md\n"
            "└── record.jsonl（append-only 审计元数据）"
        )
        if old_tree not in text:
            raise ValueError("README: process-document tree anchor not found")
        text = text.replace(old_tree, new_tree, 1)

    record_section_re = re.compile(r"## 文档变更记录\n.*?(?=## 文档更新时序\n)", re.DOTALL)
    if record_section_re.search(text):
        text = record_section_re.sub(README_RECORD_SECTION, text, count=1)
    else:
        anchor = "## 文档更新时序\n"
        if anchor not in text:
            raise ValueError("README: document timing section anchor not found")
        text = text.replace(anchor, README_RECORD_SECTION + anchor, 1)

    consistency_section_re = re.compile(r"## 阶段完成一致性收敛\n.*?(?=## 设计原则\n)", re.DOTALL)
    if consistency_section_re.search(text):
        text = consistency_section_re.sub(README_CONSISTENCY_SECTION, text, count=1)
    else:
        anchor = "## 设计原则\n"
        if anchor not in text:
            raise ValueError("README: design-principles anchor not found")
        text = text.replace(anchor, README_CONSISTENCY_SECTION + anchor, 1)

    old_validation = (
        "验证器会要求每个 `SKILL.md` 包含统一的文档更新与记录硬限制，并检查每个 skill 自带的 UTF-8 写入器与仓库规范版本完全一致，"
        "防止后续维护时退回到延迟更新、静默修改上游文档、Shell 直接追加或编码漂移。"
    )
    new_validation = (
        "验证器会要求每个 `SKILL.md` 包含统一的文档更新、阶段完成一致性与记录硬限制，并检查每个 skill 自带的 UTF-8 写入器与仓库规范版本完全一致，"
        "防止后续维护时退回到延迟更新、带矛盾状态完成阶段、静默修改上游文档、Shell 直接追加或编码漂移。"
    )
    if old_validation in text:
        text = text.replace(old_validation, new_validation, 1)
    elif new_validation not in text:
        raise ValueError("README: validator description anchor not found")

    return text


def validator_constant(name: str, value: str) -> str:
    escaped_parts: list[str] = []
    remaining = value
    while remaining:
        part, remaining = remaining[:100], remaining[100:]
        escaped = part.replace("\\", "\\\\").replace('"', '\\"')
        escaped_parts.append(f'    "{escaped}"')
    return f"{name} = (\n" + "\n".join(escaped_parts) + "\n)"


def patch_validator(text: str) -> str:
    rule_block = (
        validator_constant("DOCUMENT_TIMING_RULE", DOCUMENT_TIMING_RULE)
        + "\n\n"
        + validator_constant("DOCUMENT_CONSISTENCY_RULE", DOCUMENT_CONSISTENCY_RULE)
        + "\n\n"
        + validator_constant("DOCUMENT_RECORD_RULE", DOCUMENT_RECORD_RULE)
        + "\nREQUIRED_DOCUMENT_RECORD_FILES ="
    )
    if not VALIDATOR_RULE_BLOCK_RE.search(text):
        raise ValueError("validator: canonical rule block not found")
    text = VALIDATOR_RULE_BLOCK_RE.sub(rule_block, text, count=1)

    timing_check = (
        '    if DOCUMENT_TIMING_RULE not in text:\n'
        '        errors.append("missing canonical stage-document update timing rule")\n'
    )
    consistency_check = (
        '    if DOCUMENT_CONSISTENCY_RULE not in text:\n'
        '        errors.append("missing canonical stage-completion consistency rule")\n'
    )
    if consistency_check not in text:
        if timing_check not in text:
            raise ValueError("validator: timing-rule check anchor not found")
        text = text.replace(timing_check, timing_check + consistency_check, 1)

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
    if 'CANONICAL_RECORD_WRITER = ROOT / "scripts" / "document_record.py"' not in text:
        anchor = 'SKILLS_DIR = ROOT / "skills"\n'
        text = text.replace(
            anchor,
            anchor + 'CANONICAL_RECORD_WRITER = ROOT / "scripts" / "document_record.py"\n',
            1,
        )
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
