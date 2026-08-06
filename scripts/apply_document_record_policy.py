#!/usr/bin/env python3
"""Apply the canonical document-change recording policy across this repository."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = ROOT / "skills"
README = ROOT / "README.md"
VALIDATOR = ROOT / "scripts" / "validate_skills.py"

DOCUMENT_RECORD_RULE = (
    "**文档变更记录硬限制：每次创建、修改、删除或重命名本阶段文档后，必须在目标文档所在目录的 "
    "`record.jsonl` 追加一条 JSON 记录；`record.jsonl` 是审计元数据，不属于阶段过程文档，记录文件自身的追加不触发再次记录。"
    "写入只能使用单次 append，禁止为了记录而读取、重写或总结历史全文。记录至少包含时间、skill、运行环境、模型、思考等级、动作、"
    "文档路径、触发原因、问题与根因、修改摘要、验证结果、结果状态和预防建议；无法获知的模型、思考等级或运行环境写 `unknown`，不得猜测。"
    "禁止写入完整提示词、文档正文、用户敏感信息或思维过程。需要评审记录时，只能按条件查询或读取最近有限条目，不得把全文注入上下文。**"
)

TIMING_RULE_RE = re.compile(r"(\*\*文档更新时序硬限制：.*?\*\*)", re.DOTALL)
VERSION_RE = re.compile(r'(\n\s*version:\s*")(\d+)\.(\d+)\.(\d+)("\s*\n)')

README_RECORD_SECTION = f"""## 文档变更记录

每个文档目录维护一个 append-only 的 `record.jsonl`，用于把实际失误、修正原因和验证结果反馈给 skill 开发者。它是审计元数据，不是第二份阶段文档，因此不违反“一个阶段一份权威文档”。

{DOCUMENT_RECORD_RULE}

推荐使用：

```bash
python scripts/document_record.py append --record docs/requirements/<feature>/record.jsonl \\
  --skill game-spec --runtime codex-cli --model gpt-5.6 --reasoning-effort high \\
  --action update --document docs/requirements/<feature>/01-原始需求.md \\
  --trigger user_feedback --problem "同一规则重复出现" \\
  --root-cause "固定分类标题拆散同一问题" \\
  --change "合并规则并删除重复内容" \\
  --validation-status passed --validation "语义去重检查通过" \\
  --outcome success --improvement-target eval \\
  --prevention "增加重复事实回归场景"
```

查询时禁止全文读取。只允许有限尾部查询或流式聚合：

```bash
python scripts/document_record.py query --record <path>/record.jsonl --tail 20 --skill game-spec
python scripts/document_record.py stats --record <path>/record.jsonl
```

记录的目标不是保存操作流水，而是形成可执行反馈：重复出现的问题应转化为 skill 硬规则、模板约束、静态检查或 eval 回归场景。

"""

VALIDATOR_CONSTANT = f'''DOCUMENT_RECORD_RULE = (
    "{DOCUMENT_RECORD_RULE.replace('"', '\"')}"
)
REQUIRED_DOCUMENT_RECORD_FILES = (
    "scripts/document_record.py",
    "docs/skill-development/document-change-record.md",
    "evals/document-recording.md",
)
'''


def bump_patch_version(text: str) -> str:
    match = VERSION_RE.search(text)
    if not match:
        raise ValueError("missing semantic metadata version")
    major, minor, patch = map(int, match.group(2, 3, 4))
    replacement = f'{match.group(1)}{major}.{minor}.{patch + 1}{match.group(5)}'
    return text[: match.start()] + replacement + text[match.end() :]


def patch_skill(text: str, path: Path) -> str:
    if DOCUMENT_RECORD_RULE in text:
        return text
    match = TIMING_RULE_RE.search(text)
    if not match:
        raise ValueError(f"{path}: missing document timing rule anchor")
    text = text[: match.end()] + "\n\n" + DOCUMENT_RECORD_RULE + text[match.end() :]
    return bump_patch_version(text)


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

    if "## 文档变更记录" not in text:
        anchor = "## 文档更新时序\n"
        if anchor not in text:
            raise ValueError("README: document timing section anchor not found")
        text = text.replace(anchor, README_RECORD_SECTION + anchor, 1)

    old_validation = (
        "验证器会要求每个 `SKILL.md` 包含统一的“文档更新时序硬限制”，"
        "防止后续维护时某个阶段退回到延迟更新或静默修改上游文档。"
    )
    new_validation = (
        "验证器会要求每个 `SKILL.md` 同时包含统一的“文档更新时序硬限制”和“文档变更记录硬限制”，"
        "防止后续维护时退回到延迟更新、静默修改上游文档或无反馈记录。"
    )
    if old_validation in text:
        text = text.replace(old_validation, new_validation, 1)
    elif new_validation not in text:
        raise ValueError("README: validator description anchor not found")

    return text


def patch_validator(text: str) -> str:
    if "DOCUMENT_RECORD_RULE = (" not in text:
        anchor = ")\n\n\ndef parse_frontmatter"
        index = text.find(anchor)
        if index < 0:
            raise ValueError("validator: constant insertion anchor not found")
        insert_at = index + 2
        text = text[:insert_at] + "\n\n" + VALIDATOR_CONSTANT.rstrip() + text[insert_at:]

    check = (
        '    if DOCUMENT_RECORD_RULE not in text:\n'
        '        errors.append("missing canonical document change record rule")\n'
    )
    if check not in text:
        anchor = (
            '    if DOCUMENT_TIMING_RULE not in text:\n'
            '        errors.append("missing canonical stage-document update timing rule")\n'
        )
        if anchor not in text:
            raise ValueError("validator: timing-rule check anchor not found")
        text = text.replace(anchor, anchor + check, 1)

    required_check = (
        '    for relative_path in REQUIRED_DOCUMENT_RECORD_FILES:\n'
        '        if not (ROOT / relative_path).is_file():\n'
        '            failed = True\n'
        '            print(f"FAIL missing required file: {relative_path}")\n'
    )
    if required_check not in text:
        anchor = '    failed = False\n'
        if anchor not in text:
            raise ValueError("validator: main entry anchor not found")
        text = text.replace(anchor, anchor + required_check, 1)

    return text


def write_if_changed(path: Path, new_text: str, *, check: bool) -> bool:
    old_text = path.read_text(encoding="utf-8")
    if old_text == new_text:
        return False
    if not check:
        path.write_text(new_text, encoding="utf-8")
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    changed: list[Path] = []
    try:
        for skill_file in sorted(SKILLS_DIR.glob("*/SKILL.md")):
            old = skill_file.read_text(encoding="utf-8")
            new = patch_skill(old, skill_file)
            if write_if_changed(skill_file, new, check=args.check):
                changed.append(skill_file)

        old_readme = README.read_text(encoding="utf-8")
        if write_if_changed(README, patch_readme(old_readme), check=args.check):
            changed.append(README)

        old_validator = VALIDATOR.read_text(encoding="utf-8")
        if write_if_changed(VALIDATOR, patch_validator(old_validator), check=args.check):
            changed.append(VALIDATOR)
    except (OSError, ValueError) as exc:
        print(f"policy application failed: {exc}", file=sys.stderr)
        return 2

    if changed:
        prefix = "NEEDS UPDATE" if args.check else "UPDATED"
        for path in changed:
            print(f"{prefix} {path.relative_to(ROOT)}")
        return 1 if args.check else 0

    print("Document record policy is up to date.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
