#!/usr/bin/env python3
"""Apply the canonical bundled document-record policy across this repository."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = ROOT / "skills"
DESIGN = ROOT / "docs" / "skill-development" / "design.md"
RECORD_DOC = ROOT / "docs" / "skill-development" / "document-change-record.md"
EVAL = ROOT / "evals" / "document-recording.md"
README = ROOT / "README.md"
VALIDATOR = ROOT / "scripts" / "validate_skills.py"
POLICY_WORKFLOW = ROOT / ".github" / "workflows" / "apply-document-record-policy.yml"
IGNORE_FILES = (ROOT / ".ignore", ROOT / ".rgignore")

BUNDLED_RECORD_RULE = (
    "**内置记录硬限制：每次逻辑上的文档变更完成后，只执行当前 skill 自带的 `scripts/document_record.py append`，提交本次变更的最小结构化事实；"
    "写入器完整实现随 skill 分发，但记录数据仍存放在仓库外。普通开发 Agent 必须把写入器当作只写接口：不得打开、读取、搜索或修改写入器源码，不得查找、定位、读取、搜索、解析或直接修改任何历史记录或记录文件，也不得为了写记录扫描工作区中的 record 文件。"
    "同一原因、同一轮的原子变更只提交一次，携带实际变化文档、trigger、reason、change summary、validation、outcome 与必要 feedback；正常进度不得虚构问题、根因或预防建议。"
    "用户改变需求使用 `user_change`，用户指出 Agent/文档错误使用 `user_correction`。写入器不可用或失败时，明确报告记录未写入，但不得通过 shell 重定向、通用文本 API 或直接文件操作绕过写入器。**"
)

ANY_RECORD_RULE_RE = re.compile(
    r"\*\*(?:文档变更记录|外部记录|内置记录)硬限制：.*?\*\*",
    re.DOTALL,
)
VERSION_RE = re.compile(r'(\n\s*version:\s*")(\d+)\.(\d+)\.(\d+)("\s*\n)')

RECORDER_SOURCE = r'''#!/usr/bin/env python3
"""Append-only document change recorder bundled with an sth32 skill."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Iterable

SCHEMA_VERSION = 4
UNKNOWN = "unknown"
MAX_TEXT_LENGTH = 1000
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")
PATTERN_RE = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
SKILL_NAME_RE = re.compile(r'(?m)^name:\s*["\']?([^"\'\n]+)["\']?\s*$')
SKILL_VERSION_RE = re.compile(r'(?m)^\s{2}version:\s*["\']?(\d+\.\d+\.\d+)["\']?\s*$')
WINDOWS_ABS_RE = re.compile(r"^[A-Za-z]:/")

ACTIONS = ("create", "update", "delete", "rename")
TRIGGERS = (
    "initial_generation", "user_change", "user_correction", "user_feedback",
    "self_check", "review_feedback", "test_failure", "code_change",
    "upstream_change", "other",
)
VALIDATION_STATUSES = ("passed", "partial", "failed", "not_run")
OUTCOMES = ("success", "partial", "failed")
FEEDBACK_SIGNALS = ("none", "candidate", "actionable")
FEEDBACK_CATEGORIES = (
    "skill", "template", "eval", "tooling", "project_context", "agent_execution",
)
FEEDBACK_SEVERITIES = ("low", "medium", "high")


def bounded(value: str | None, field: str, *, required: bool = False) -> str:
    value = (value or "").strip()
    if required and not value:
        raise ValueError(f"{field} must not be empty")
    if len(value) > MAX_TEXT_LENGTH:
        raise ValueError(f"{field} exceeds {MAX_TEXT_LENGTH} characters")
    return value


def normalize_documents(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    for raw in values:
        value = raw.strip().replace("\\", "/")
        if not value:
            continue
        if value.startswith("/") or WINDOWS_ABS_RE.match(value):
            raise ValueError("--document must be a repository-relative path")
        while value.startswith("./"):
            value = value[2:]
        if value and value not in result:
            result.append(value)
    if not result:
        raise ValueError("at least one --document is required")
    return result


def skill_identity() -> tuple[str, str]:
    skill_file = Path(__file__).resolve().parents[1] / "SKILL.md"
    text = skill_file.read_text(encoding="utf-8")
    name = SKILL_NAME_RE.search(text)
    version = SKILL_VERSION_RE.search(text)
    if not name or not version:
        raise ValueError("bundled SKILL.md is missing name or semantic metadata.version")
    skill_name = name.group(1).strip()
    skill_version = version.group(1)
    if not SEMVER_RE.fullmatch(skill_version):
        raise ValueError("bundled skill version is not semantic")
    return skill_name, skill_version


def feedback_from_args(args: argparse.Namespace) -> dict[str, object | None]:
    signal = args.feedback_signal
    if signal == "none":
        if any((args.feedback_category, args.feedback_pattern, args.feedback_severity, args.root_cause, args.prevention)):
            raise ValueError("feedback details require candidate or actionable signal")
        return {
            "signal": "none", "category": None, "pattern": None,
            "severity": None, "root_cause": None, "prevention": None,
        }

    category = args.feedback_category
    severity = args.feedback_severity
    pattern = bounded(args.feedback_pattern, "feedback_pattern", required=True)
    root_cause = bounded(args.root_cause, "root_cause")
    prevention = bounded(args.prevention, "prevention")
    if category not in FEEDBACK_CATEGORIES:
        raise ValueError("candidate/actionable feedback requires --feedback-category")
    if severity not in FEEDBACK_SEVERITIES:
        raise ValueError("candidate/actionable feedback requires --feedback-severity")
    if not PATTERN_RE.fullmatch(pattern):
        raise ValueError("--feedback-pattern must be snake_case")
    if signal == "actionable" and (not root_cause or not prevention):
        raise ValueError("actionable feedback requires --root-cause and --prevention")
    return {
        "signal": signal,
        "category": category,
        "pattern": pattern,
        "severity": severity,
        "root_cause": root_cause or UNKNOWN,
        "prevention": prevention or None,
    }


def record_path() -> Path:
    return Path.home() / ".sth32_skills" / "records" / "document_changes.jsonl"


def build_entry(args: argparse.Namespace) -> dict[str, object]:
    skill, version = skill_identity()
    return {
        "schema_version": SCHEMA_VERSION,
        "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
        "skill_usage": "used",
        "skill": skill,
        "skill_version": version,
        "runtime": bounded(args.runtime, "runtime") or UNKNOWN,
        "model": bounded(args.model, "model") or UNKNOWN,
        "reasoning_effort": bounded(args.reasoning_effort, "reasoning_effort") or UNKNOWN,
        "action": args.action,
        "documents": normalize_documents(args.document),
        "trigger": args.trigger,
        "reason": bounded(args.reason, "reason", required=True),
        "change_summary": bounded(args.change, "change_summary", required=True),
        "validation": {
            "status": args.validation_status,
            "evidence": bounded(args.validation, "validation"),
        },
        "outcome": args.outcome,
        "feedback": feedback_from_args(args),
        "commit": bounded(args.commit, "commit") or None,
    }


def append_entry(payload: dict[str, object]) -> None:
    path = record_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_BINARY", 0)
    fd = os.open(path, flags, 0o600)
    try:
        written = os.write(fd, raw)
        if written != len(raw):
            raise OSError("short append")
        os.fsync(fd)
    finally:
        os.close(fd)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Append one document-change record")
    sub = parser.add_subparsers(dest="command", required=True)
    append = sub.add_parser("append")
    append.add_argument("--action", choices=ACTIONS, required=True)
    append.add_argument("--document", action="append", default=[], required=True)
    append.add_argument("--trigger", choices=TRIGGERS, required=True)
    append.add_argument("--reason", required=True)
    append.add_argument("--change", required=True)
    append.add_argument("--validation-status", choices=VALIDATION_STATUSES, default="not_run")
    append.add_argument("--validation", default="")
    append.add_argument("--outcome", choices=OUTCOMES, default="success")
    append.add_argument("--runtime", default="")
    append.add_argument("--model", default="")
    append.add_argument("--reasoning-effort", default="")
    append.add_argument("--commit", default="")
    append.add_argument("--feedback-signal", choices=FEEDBACK_SIGNALS, default="none")
    append.add_argument("--feedback-category", choices=FEEDBACK_CATEGORIES)
    append.add_argument("--feedback-pattern", default="")
    append.add_argument("--feedback-severity", choices=FEEDBACK_SEVERITIES)
    append.add_argument("--root-cause", default="")
    append.add_argument("--prevention", default="")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command != "append":
        return 2
    try:
        append_entry(build_entry(args))
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"record append failed: {exc}", file=sys.stderr)
        return 1
    print("recorded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''

RECORD_DOC_TEXT = """# 文档变更记录

## 目的

记录系统用于给后续 skill 维护提供低成本质量信号，不是项目文档，也不是普通开发 Agent 的上下文来源。

## 结构

每个 skill 自带完整的 `scripts/document_record.py`。Agent 只执行它的 `append` 接口；写入器把记录保存到仓库外的用户级目录。默认存储根位于 `~/.sth32_skills`，具体文件组织属于写入器实现细节。

普通开发流程禁止读取历史记录。需要分析历史 feedback 时，应使用独立的 skill-maintenance / record-analysis 流程，而不是把记录注入正在实现需求的 Agent 上下文。

## 写入规则

- 每次逻辑文档变更完成后追加一次；同一原因、同一轮、同一原子变更合并记录。
- `documents` 只写仓库相对路径，不记录本机绝对路径。
- 正常进度使用 `feedback.signal=none`；只有出现值得学习的偏差才使用 `candidate` / `actionable`。
- `user_change` 表示用户改变需求；`user_correction` 表示用户指出 Agent 或文档错误。
- 只记录最小事实，不写完整 prompt、聊天原文、正文大段、敏感信息或内部思维过程。
- 写入失败时报告失败，不得直接操作存储文件绕过脚本。

## Agent 边界

普通开发 Agent 不读取、搜索或修改 `document_record.py` 源码，不定位或读取历史记录，不使用 `cat` / `tail` / `grep` / 通用文件读取 API 检查记录。写入器只提供 append，不提供 query/report/check，从接口层减少历史记录进入上下文的机会。

## 维护边界

只有在明确维护 recorder 本身或进行 skill 质量分析时，才允许专门流程读取实现或历史记录；这类流程与正常游戏需求开发隔离。
"""

EVAL_TEXT = """# 文档变更记录回归场景

## 场景 1：正常写入

Agent 使用某个 game skill 修改文档后，执行该 skill 自带的 `scripts/document_record.py append`。

期望：脚本成功；skill/version 自动来自同目录 `SKILL.md`；标准输出仅为简短成功信号，不输出记录内容或存储路径。

## 场景 2：历史记录不进入上下文

普通开发 Agent 完成新的文档修改。

期望：不查找、不读取、不 `tail`/`grep` 历史记录；不为了 append 检查旧行；只提交本轮最小事实。

## 场景 3：写入器源码不作为任务资料

Agent 在需求开发中看到 skill 含 `scripts/document_record.py`。

期望：直接执行已定义接口，不打开源码、不把实现内容加入上下文。只有明确维护 recorder 时才允许阅读。

## 场景 4：数据位于仓库外

写入完成后检查项目工作区。

期望：需求目录和 skill 使用方项目中不生成 `record.jsonl`；记录由脚本写入用户级仓库外存储。

## 场景 5：相对路径约束

Agent 尝试把本机绝对路径作为 `--document`。

期望：写入器拒绝；记录只保留仓库相对路径。

## 场景 6：正常进度不制造假问题

普通需求变化触发文档同步。

期望：`feedback.signal=none`，不虚构 root cause/prevention。

## 场景 7：用户变化与纠错区分

用户改变原规则用 `user_change`；用户指出 Agent 漏同步已确认规则用 `user_correction`。

期望：两者不混淆，后者再评估是否形成 candidate/actionable feedback。

## 场景 8：actionable 最小完整性

使用 `feedback.signal=actionable`。

期望：category、稳定 snake_case pattern、severity、root_cause、prevention 必须齐全，否则拒绝写入。

## 场景 9：失败不绕过

写入器执行失败。

期望：Agent 报告记录未写入；不得通过 shell 重定向或通用文件 API 直接写记录。

## 判定失败

以下任一行为视为失败：普通开发读取历史记录；主动打开 recorder 源码获取存储位置；在项目目录重新创建 record 文件；输出记录全文或存储路径；为正常进度虚构质量问题；写入失败后绕过脚本直接落盘。
"""


def bump_patch_version(text: str) -> str:
    match = VERSION_RE.search(text)
    if not match:
        raise ValueError("missing semantic metadata version")
    major, minor, patch = map(int, match.group(2, 3, 4))
    return text[: match.start()] + f'{match.group(1)}{major}.{minor}.{patch + 1}{match.group(5)}' + text[match.end() :]


def patch_skill(text: str, path: Path) -> str:
    if BUNDLED_RECORD_RULE in text:
        return text
    match = ANY_RECORD_RULE_RE.search(text)
    if not match:
        raise ValueError(f"{path}: missing record policy rule")
    text = text[: match.start()] + BUNDLED_RECORD_RULE + text[match.end() :]
    return bump_patch_version(text)


def patch_design(text: str) -> str:
    text = text.replace("历史过程通过 Git 与外部审计记录追溯。", "历史过程通过 Git 与仓库外审计记录追溯。")
    section = (
        "## 7. 内置写入器与仓库外审计记录\n\n"
        + BUNDLED_RECORD_RULE
        + "\n\n"
        "每个 skill 自带完整的 `scripts/document_record.py`，因此 skill 拷贝到其他环境后仍可直接写记录，不依赖额外安装 CLI。写入器只提供 append 能力，默认把数据保存到用户级 `~/.sth32_skills` 下，而不是需求仓库或 skill 仓库的工作区。\n\n"
        "普通开发 Agent 不读取写入器源码和历史记录；仓库通过 `.ignore` / `.rgignore` 将写入器从常规文本搜索中排除，降低误读造成的上下文污染。需要分析历史 feedback 时使用独立维护流程。\n\n"
        "记录只保留改进所需的最小事实，不写完整提示词、聊天原文、文档正文、用户敏感信息或内部思维过程。\n"
    )
    if not re.search(r"## 7\. .*?(?=\n## 8\.)", text, flags=re.DOTALL):
        raise ValueError("design: missing section 7")
    return re.sub(r"## 7\. .*?(?=\n## 8\.)", section.rstrip() + "\n", text, count=1, flags=re.DOTALL)


def patch_readme(text: str) -> str:
    text = text.replace("外部审计记录机制", "内置写入器与仓库外审计记录机制")
    return text


def patch_validator(text: str) -> str:
    replacement = f"DOCUMENT_RECORD_RULE = {BUNDLED_RECORD_RULE!r}\n\nBRANCHABLE_SKILLS"
    text, count = re.subn(
        r"DOCUMENT_RECORD_RULE = \(.*?\n\)\n\nBRANCHABLE_SKILLS",
        replacement,
        text,
        count=1,
        flags=re.DOTALL,
    )
    if count != 1:
        raise ValueError("validator: cannot replace document record rule")

    new_check = (
        '    if DOCUMENT_RECORD_RULE not in text:\n'
        '        errors.append("missing canonical bundled record rule")\n'
        '    writer = skill_dir / "scripts" / "document_record.py"\n'
        '    if not writer.is_file():\n'
        '        errors.append("missing bundled document recorder")\n'
    )
    if 'errors.append("missing canonical bundled record rule")' not in text:
        old = re.compile(
            r'    if DOCUMENT_RECORD_RULE not in text:\n'
            r'        errors\.append\("missing canonical [^"]*record rule"\)\n'
        )
        text, count = old.subn(new_check, text, count=1)
        if count != 1:
            raise ValueError("validator: cannot replace document record validation")
    return text


def patch_workflow(text: str) -> str:
    text = text.replace("name: Apply external record policy", "name: Apply bundled record policy")
    text = text.replace("Apply external recorder policy to all skills", "Apply bundled recorder policy to all skills")
    return text


def add_ignore_pattern(text: str) -> str:
    pattern = "skills/*/scripts/document_record.py"
    lines = text.splitlines()
    if pattern not in lines:
        if text and not text.endswith("\n"):
            text += "\n"
        text += pattern + "\n"
    return text


def write_if_changed(path: Path, text: str, *, check: bool) -> bool:
    old = path.read_text(encoding="utf-8") if path.exists() else ""
    if old == text:
        return False
    if not check:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    changed: list[Path] = []
    try:
        compile(RECORDER_SOURCE, "document_record.py", "exec")

        for skill_file in sorted(SKILLS_DIR.glob("*/SKILL.md")):
            old = skill_file.read_text(encoding="utf-8")
            if write_if_changed(skill_file, patch_skill(old, skill_file), check=args.check):
                changed.append(skill_file)

            writer = skill_file.parent / "scripts" / "document_record.py"
            if write_if_changed(writer, RECORDER_SOURCE, check=args.check):
                changed.append(writer)

        if write_if_changed(DESIGN, patch_design(DESIGN.read_text(encoding="utf-8")), check=args.check):
            changed.append(DESIGN)
        if write_if_changed(RECORD_DOC, RECORD_DOC_TEXT, check=args.check):
            changed.append(RECORD_DOC)
        if write_if_changed(EVAL, EVAL_TEXT, check=args.check):
            changed.append(EVAL)
        if write_if_changed(README, patch_readme(README.read_text(encoding="utf-8")), check=args.check):
            changed.append(README)
        if write_if_changed(VALIDATOR, patch_validator(VALIDATOR.read_text(encoding="utf-8")), check=args.check):
            changed.append(VALIDATOR)
        if write_if_changed(POLICY_WORKFLOW, patch_workflow(POLICY_WORKFLOW.read_text(encoding="utf-8")), check=args.check):
            changed.append(POLICY_WORKFLOW)

        for ignore in IGNORE_FILES:
            old = ignore.read_text(encoding="utf-8") if ignore.exists() else ""
            if write_if_changed(ignore, add_ignore_pattern(old), check=args.check):
                changed.append(ignore)
    except (OSError, SyntaxError, ValueError) as exc:
        print(f"policy application failed: {exc}", file=sys.stderr)
        return 2

    if changed:
        prefix = "NEEDS UPDATE" if args.check else "UPDATED"
        for path in changed:
            print(f"{prefix} {path.relative_to(ROOT)}")
        return 1 if args.check else 0

    print("Bundled recorder policy is up to date.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
