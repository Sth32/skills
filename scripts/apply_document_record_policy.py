#!/usr/bin/env python3
"""Apply the canonical external recorder policy across this repository."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = ROOT / "skills"
DESIGN = ROOT / "docs" / "skill-development" / "design.md"
README = ROOT / "README.md"

EXTERNAL_RECORD_RULE = (
    "**外部记录硬限制：每次逻辑上的文档变更完成后，只通过 `sth32-skills-record append` 提交本次变更的最小结构化事实；"
    "记录存储属于仓库外部基础设施，Agent 不得查找、定位、读取、搜索、解析或直接修改任何历史记录、记录文件或 recorder 实现，也不得为了写记录而扫描工作区中的 record 文件。"
    "同一原因、同一轮的原子变更只提交一次，携带实际变化文档、trigger、reason、change summary、validation、outcome 与必要 feedback；正常进度不得虚构问题、根因或预防建议。"
    "用户改变需求使用 `user_change`，用户指出 Agent/文档错误使用 `user_correction`。命令不可用或失败时，明确报告记录未写入，但不得通过 shell 重定向、通用文本 API 或直接文件操作绕过 recorder。**"
)

OLD_RULE_RE = re.compile(r"\*\*文档变更记录硬限制：.*?\*\*", re.DOTALL)
NEW_RULE_RE = re.compile(r"\*\*外部记录硬限制：.*?\*\*", re.DOTALL)
VERSION_RE = re.compile(r'(\n\s*version:\s*")(\d+)\.(\d+)\.(\d+)("\s*\n)')


def bump_patch_version(text: str) -> str:
    match = VERSION_RE.search(text)
    if not match:
        raise ValueError("missing semantic metadata version")
    major, minor, patch = map(int, match.group(2, 3, 4))
    return text[: match.start()] + f'{match.group(1)}{major}.{minor}.{patch + 1}{match.group(5)}' + text[match.end() :]


def patch_skill(text: str, path: Path) -> str:
    if EXTERNAL_RECORD_RULE in text:
        return text
    if NEW_RULE_RE.search(text):
        return bump_patch_version(NEW_RULE_RE.sub(EXTERNAL_RECORD_RULE, text, count=1))
    if OLD_RULE_RE.search(text):
        return bump_patch_version(OLD_RULE_RE.sub(EXTERNAL_RECORD_RULE, text, count=1))
    raise ValueError(f"{path}: missing record policy rule")


def patch_design(text: str) -> str:
    text = text.replace("历史过程通过 Git、日志和 `record.jsonl` 追溯。", "历史过程通过 Git 与外部审计记录追溯。")
    text = re.sub(r"\n└── record\.jsonl", "", text)
    text = text.replace(
        "`收尾事项.md` 的变更仍遵守本目录 `record.jsonl` 的审计规则；同一原因、同一轮与阶段文档一起变化时可合并为一条原子记录。",
        "`收尾事项.md` 的变更同样通过外部 recorder 记录；同一原因、同一轮与阶段文档一起变化时合并为一次原子提交。",
    )
    section = (
        "## 7. 外部审计记录\n\n"
        + EXTERNAL_RECORD_RULE
        + "\n\n"
        "记录系统是仓库外部 telemetry 基础设施，不属于需求目录、阶段文档或项目知识空间。正常开发 Agent 只拥有 append 接口，不以历史记录作为当前任务上下文。\n\n"
        "Agent 侧只依赖稳定命令接口：\n\n"
        "```bash\n"
        "sth32-skills-record append ...\n"
        "```\n\n"
        "存储路径、文件名、编码、schema 持久化细节和历史查询能力均属于 recorder 实现细节，不在 skill、阶段文档或普通 Agent 规则中暴露。需要分析历史反馈时，应由独立的 skill-maintenance / record-analysis 流程执行，而不是由正常开发 Agent 读取记录。\n\n"
        "记录只保留改进所需的最小事实，不写完整提示词、聊天原文、文档正文、用户敏感信息或内部思维过程。\n"
    )
    if re.search(r"## 7\. .*?(?=\n## 8\.)", text, flags=re.DOTALL):
        text = re.sub(r"## 7\. .*?(?=\n## 8\.)", section.rstrip() + "\n", text, count=1, flags=re.DOTALL)
    else:
        raise ValueError("design: missing section 7")
    return text


def patch_readme(text: str) -> str:
    text = text.replace(
        "[`docs/skill-development/design.md`](docs/skill-development/design.md)：仓库级设计，包含工作流模型、权威文档模型、阶段门禁、变更传播和 `record.jsonl` 等具体机制。",
        "[`docs/skill-development/design.md`](docs/skill-development/design.md)：仓库级设计，包含工作流模型、权威文档模型、阶段门禁、变更传播和外部审计记录机制。",
    )
    return text


def write_if_changed(path: Path, text: str, *, check: bool) -> bool:
    old = path.read_text(encoding="utf-8")
    if old == text:
        return False
    if not check:
        path.write_text(text, encoding="utf-8", newline="\n")
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    changed: list[Path] = []
    try:
        for skill_file in sorted(SKILLS_DIR.glob("*/SKILL.md")):
            old = skill_file.read_text(encoding="utf-8")
            if write_if_changed(skill_file, patch_skill(old, skill_file), check=args.check):
                changed.append(skill_file)

        old_design = DESIGN.read_text(encoding="utf-8")
        if write_if_changed(DESIGN, patch_design(old_design), check=args.check):
            changed.append(DESIGN)

        old_readme = README.read_text(encoding="utf-8")
        if write_if_changed(README, patch_readme(old_readme), check=args.check):
            changed.append(README)

        # Bundled record writers make the storage implementation discoverable to normal Agents.
        for writer in sorted(SKILLS_DIR.glob("*/scripts/document_record.py")):
            changed.append(writer)
            if not args.check:
                writer.unlink()
    except (OSError, ValueError) as exc:
        print(f"policy application failed: {exc}", file=sys.stderr)
        return 2

    if changed:
        prefix = "NEEDS UPDATE" if args.check else "UPDATED"
        for path in changed:
            print(f"{prefix} {path.relative_to(ROOT)}")
        return 1 if args.check else 0

    print("External recorder policy is up to date.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())