#!/usr/bin/env python3
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
