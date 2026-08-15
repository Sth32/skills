#!/usr/bin/env python3
"""Apply the canonical stage-transition gate to all skills and README."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = ROOT / "skills"
README = ROOT / "README.md"

STAGE_TRANSITION_RULE = (
    "**阶段切换门禁硬限制：阶段文档顶部“状态”是阶段状态的唯一权威来源，聊天中的“完成”“可以进入下一阶段”"
    "不构成阶段完成。结束本阶段时，必须先满足本阶段完成/收敛条件，再在同一轮把顶部状态写为本阶段模板定义的可移交终态，"
    "同步最后更新时间、未解决计数、当前步骤等受影响元信息，并重新读取文档确认终态已经落盘；在这些动作完成前，不得宣称本阶段完成、"
    "移交或下一阶段可以开始。开始或恢复一个按工作流顺序进入的下游阶段时，在创建或修改本阶段文档、配置或代码之前，必须读取本 skill "
    "要求的上游阶段文档顶部状态；任一实际前置上游不是其正常可移交终态时，必须明确指出具体文件与当前状态并停止正常推进，返回对应上游闭环，"
    "不得用聊天记录、记忆或推断覆盖文档状态，也不得静默替上游补成已完成。若本 skill 明确允许独立、提前或并行执行，只检查它声明的实际前置；"
    "用户在看到状态警告后明确要求带未闭环上游并行推进时，只能进行不依赖未决上游结论的安全工作，并在当前阶段文档显式记录上游阻塞/例外，"
    "不得把这种例外描述成正常阶段切换。**"
)

CONSISTENCY_RULE_RE = re.compile(r"\*\*阶段完成一致性硬限制：.*?\*\*", re.DOTALL)
TRANSITION_RULE_RE = re.compile(r"\*\*阶段切换门禁硬限制：.*?\*\*", re.DOTALL)
VERSION_RE = re.compile(r'(\n\s*version:\s*")(\d+)\.(\d+)\.(\d+)("\s*\n)')
README_SECTION_RE = re.compile(r"## 阶段切换门禁\n.*?(?=## [^#]|\Z)", re.DOTALL)

README_SECTION = f"""## 阶段切换门禁

{STAGE_TRANSITION_RULE}

正常可移交终态以各阶段模板为准。当前主流程为：

| 阶段 | 权威文档 | 正常可移交终态 |
|---|---|---|
| 01 原始需求 | 未分支 `01-原始需求.md`；分支 `01-Uxx-<主题>-原始需求.md` | 叶文档 `整理完成`；父文档可为 `已拆分` |
| 02 需求挖掘 | `02-需求挖掘.md` | `已收敛` |
| 03 程序实现澄清 | `03-程序实现澄清.md` | `已收敛` |
| 04 配置规划 | `04-配置规划.md` | `已完成` |
| 05 框架实现 | `05-框架实现方案.md` | `骨架已完成` |
| 06 完整实现 | `06-完整实现方案.md` | `已完成` |
| 07 交叉评审 | 未分支/整体 `07-交叉评审.md`；分支 `07-Uxx-<主题>-交叉评审.md` | `通过`；`有条件通过` 仅按已明确接受的条件继续 |

顶部状态只表达**当前阶段自身**是否闭环。下游依赖必须留在事项内，例如配置阶段已经完成但仍有代码接入工作时，`04` 顶部应为 `已完成`，代码依赖写在对应配置事项中，而不是把阶段状态写成“待代码接入”。

"""


def bump_patch_version(text: str) -> str:
    match = VERSION_RE.search(text)
    if not match:
        raise ValueError("missing semantic metadata version")
    major, minor, patch = map(int, match.group(2, 3, 4))
    replacement = f'{match.group(1)}{major}.{minor}.{patch + 1}{match.group(5)}'
    return text[: match.start()] + replacement + text[match.end() :]


def patch_skill(text: str, path: Path) -> str:
    if STAGE_TRANSITION_RULE in text:
        return text

    if TRANSITION_RULE_RE.search(text):
        new_text = TRANSITION_RULE_RE.sub(STAGE_TRANSITION_RULE, text, count=1)
        return bump_patch_version(new_text)

    consistency = CONSISTENCY_RULE_RE.search(text)
    if not consistency:
        raise ValueError(f"{path}: missing stage completion consistency rule anchor")

    new_text = text[: consistency.end()] + "\n\n" + STAGE_TRANSITION_RULE + text[consistency.end() :]
    return bump_patch_version(new_text)


def patch_readme(text: str) -> str:
    if README_SECTION_RE.search(text):
        return README_SECTION_RE.sub(README_SECTION, text, count=1)

    anchor = "## 设计原则\n"
    if anchor not in text:
        raise ValueError("README: design-principles anchor not found")
    return text.replace(anchor, README_SECTION + anchor, 1)


def write_if_changed(path: Path, new_text: str, *, check: bool) -> bool:
    old_text = path.read_text(encoding="utf-8")
    if old_text == new_text:
        return False
    if not check:
        path.write_text(new_text, encoding="utf-8", newline="\n")
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
    except (OSError, ValueError) as exc:
        print(f"stage transition policy application failed: {exc}", file=sys.stderr)
        return 2

    if changed:
        prefix = "NEEDS UPDATE" if args.check else "UPDATED"
        for path in changed:
            print(f"{prefix} {path.relative_to(ROOT)}")
        return 1 if args.check else 0

    print("Stage transition policy is up to date.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
