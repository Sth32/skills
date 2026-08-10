#!/usr/bin/env python3
"""Append and inspect bounded UTF-8 document-change records."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter, deque
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = 3
UNKNOWN = "unknown"
NOT_APPLICABLE = "not_applicable"
MAX_TEXT_LENGTH = 1000
MAX_QUERY_TAIL = 200
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")
SKILL_NAME_RE = re.compile(r'(?m)^name:\s*["\']?([^"\'\n]+)["\']?\s*$')
SKILL_VERSION_RE = re.compile(
    r'(?m)^\s{2}version:\s*["\']?(\d+\.\d+\.\d+)["\']?\s*$'
)

ACTIONS = ("create", "update", "delete", "rename")
TRIGGERS = (
    "initial_generation",
    "user_feedback",
    "self_check",
    "review_feedback",
    "test_failure",
    "code_change",
    "upstream_change",
    "other",
)
VALIDATION_STATUSES = ("passed", "partial", "failed", "not_run")
OUTCOMES = ("success", "partial", "failed")
IMPROVEMENT_TARGETS = (
    "skill",
    "template",
    "eval",
    "tooling",
    "project_context",
    "none",
)
SKILL_USAGES = ("used", "not_used")


def bounded(value: str | None, field: str, *, allow_empty: bool = True) -> str:
    value = (value or "").strip()
    if not allow_empty and not value:
        raise ValueError(f"{field} must not be empty")
    if len(value) > MAX_TEXT_LENGTH:
        raise ValueError(f"{field} exceeds {MAX_TEXT_LENGTH} characters")
    return value


def normalized_documents(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        item = value.strip().replace("\\", "/")
        if not item:
            continue
        if item not in result:
            result.append(item)
    if not result:
        raise ValueError("at least one --document is required")
    return result


def read_current_skill_identity(expected_skill: str) -> tuple[str, str]:
    """Resolve the installed skill identity from the writer's own skill root."""
    skill_file = Path(__file__).resolve().parents[1] / "SKILL.md"
    if not skill_file.is_file():
        raise ValueError(
            "cannot resolve skill version: invoke the writer bundled under "
            "<skill-root>/scripts/document_record.py"
        )

    try:
        text = skill_file.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{skill_file} is not valid UTF-8") from exc

    if not text.startswith("---\n"):
        raise ValueError(f"{skill_file} is missing YAML frontmatter")
    try:
        _, frontmatter, _ = text.split("---", 2)
    except ValueError as exc:
        raise ValueError(f"{skill_file} has incomplete YAML frontmatter") from exc

    name_match = SKILL_NAME_RE.search(frontmatter)
    version_match = SKILL_VERSION_RE.search(frontmatter)
    if not name_match:
        raise ValueError(f"{skill_file} is missing frontmatter name")
    if not version_match:
        raise ValueError(f"{skill_file} is missing semantic metadata.version")

    actual_skill = name_match.group(1).strip()
    skill_version = version_match.group(1).strip()
    if actual_skill != expected_skill:
        raise ValueError(
            f"--skill={expected_skill!r} does not match bundled SKILL.md name={actual_skill!r}"
        )
    if not SEMVER_RE.fullmatch(skill_version):
        raise ValueError(f"invalid skill version in {skill_file}: {skill_version!r}")
    return actual_skill, skill_version


def decode_jsonl_line(path: Path, line_number: int, raw: bytes) -> dict[str, Any] | None:
    """Decode only storage-level JSONL structure, without enforcing record schema."""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(
            f"{path}:{line_number} is not UTF-8; repair the record before continuing"
        ) from exc

    text = text.strip()
    if not text:
        return None
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path}:{line_number} is not valid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{path}:{line_number} must contain one JSON object")
    return value


def validate_entry_schema(path: Path, line_number: int, value: dict[str, Any]) -> None:
    """Validate version/skill attribution semantics for explicit health checks."""
    schema_version = value.get("schema_version")
    if schema_version == 1:
        return
    if schema_version == 2:
        skill_version = value.get("skill_version")
        if not isinstance(skill_version, str) or not SEMVER_RE.fullmatch(skill_version):
            raise ValueError(
                f"{path}:{line_number} schema v2 requires semantic skill_version"
            )
        return
    if schema_version == 3:
        usage = value.get("skill_usage")
        if usage not in SKILL_USAGES:
            raise ValueError(
                f"{path}:{line_number} schema v3 requires skill_usage=used|not_used"
            )
        skill = value.get("skill")
        skill_version = value.get("skill_version")
        if usage == "used":
            if not isinstance(skill, str) or not skill.strip():
                raise ValueError(
                    f"{path}:{line_number} schema v3 skill_usage=used requires skill"
                )
            if not isinstance(skill_version, str) or not SEMVER_RE.fullmatch(skill_version):
                raise ValueError(
                    f"{path}:{line_number} schema v3 skill_usage=used requires semantic skill_version"
                )
        else:
            if skill is not None or skill_version is not None:
                raise ValueError(
                    f"{path}:{line_number} schema v3 skill_usage=not_used requires "
                    "skill=null and skill_version=null"
                )
        return
    raise ValueError(
        f"{path}:{line_number} has unsupported schema_version={schema_version!r}"
    )


def validate_append_safety(path: Path) -> None:
    """Block only storage corruption that would break JSONL framing/UTF-8.

    Historical schema mistakes are independent rows and must not make a valid
    later row impossible to append.
    """
    if not path.exists():
        return
    if not path.is_file():
        raise ValueError(f"record path is not a file: {path}")
    with path.open("rb") as handle:
        for line_number, raw in enumerate(handle, start=1):
            decode_jsonl_line(path, line_number, raw)


def validate_existing_record(path: Path) -> None:
    """Strict health check: storage plus schema semantics for every non-empty row."""
    if not path.exists():
        return
    if not path.is_file():
        raise ValueError(f"record path is not a file: {path}")
    with path.open("rb") as handle:
        for line_number, raw in enumerate(handle, start=1):
            value = decode_jsonl_line(path, line_number, raw)
            if value is not None:
                validate_entry_schema(path, line_number, value)


def append_single_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    validate_append_safety(path)
    raw = (
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    fd = os.open(path, flags, 0o666)
    try:
        written = os.write(fd, raw)
        if written != len(raw):
            raise OSError(f"short append: wrote {written} of {len(raw)} bytes")
        os.fsync(fd)
    finally:
        os.close(fd)


def build_entry(args: argparse.Namespace) -> dict[str, Any]:
    if args.no_skill:
        skill = None
        skill_version = None
        skill_usage = "not_used"
    else:
        skill, skill_version = read_current_skill_identity(
            bounded(args.skill, "skill", allow_empty=False)
        )
        skill_usage = "used"

    root_cause = bounded(args.root_cause, "root_cause") or (
        "not_applicable" if args.trigger == "initial_generation" else UNKNOWN
    )
    prevention = bounded(args.prevention, "prevention")
    if args.improvement_target != "none" and not prevention:
        raise ValueError("--prevention is required unless --improvement-target=none")

    return {
        "schema_version": SCHEMA_VERSION,
        "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
        "skill_usage": skill_usage,
        "skill": skill,
        "skill_version": skill_version,
        "runtime": bounded(args.runtime, "runtime") or UNKNOWN,
        "model": bounded(args.model, "model") or UNKNOWN,
        "reasoning_effort": bounded(args.reasoning_effort, "reasoning_effort") or UNKNOWN,
        "action": args.action,
        "documents": normalized_documents(args.document),
        "trigger": args.trigger,
        "problem": bounded(args.problem, "problem", allow_empty=False),
        "root_cause": root_cause,
        "change_summary": bounded(args.change, "change_summary", allow_empty=False),
        "validation": {
            "status": args.validation_status,
            "evidence": bounded(args.validation, "validation"),
        },
        "outcome": args.outcome,
        "improvement": {
            "target": args.improvement_target,
            "prevention": prevention,
        },
        "commit": bounded(args.commit, "commit") or None,
    }


def iter_entries(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("rb") as handle:
        for line_number, raw in enumerate(handle, start=1):
            if not raw.strip():
                continue
            try:
                value = decode_jsonl_line(path, line_number, raw)
            except ValueError as exc:
                print(f"warning: skipped unreadable record: {exc}", file=sys.stderr)
                continue
            if value is None:
                continue
            try:
                validate_entry_schema(path, line_number, value)
            except ValueError as exc:
                print(
                    f"warning: legacy/invalid schema row retained as best-effort data: {exc}",
                    file=sys.stderr,
                )
            yield value


def entry_skill(entry: dict[str, Any]) -> str:
    if entry.get("schema_version") == 3 and entry.get("skill_usage") == "not_used":
        return "none"
    value = entry.get("skill")
    return value if isinstance(value, str) and value else UNKNOWN


def entry_skill_version(entry: dict[str, Any]) -> str:
    if entry.get("schema_version") == 3 and entry.get("skill_usage") == "not_used":
        return NOT_APPLICABLE
    value = entry.get("skill_version")
    if isinstance(value, str) and SEMVER_RE.fullmatch(value):
        return value
    return UNKNOWN


def entry_skill_usage(entry: dict[str, Any]) -> str:
    if entry.get("schema_version") == 3:
        value = entry.get("skill_usage")
        return value if value in SKILL_USAGES else UNKNOWN
    return "used" if entry_skill(entry) != UNKNOWN else UNKNOWN


def matches(entry: dict[str, Any], args: argparse.Namespace) -> bool:
    if args.skill and entry_skill(entry) != args.skill:
        return False
    if args.skill_version and entry_skill_version(entry) != args.skill_version:
        return False
    if getattr(args, "skill_usage", None) and entry_skill_usage(entry) != args.skill_usage:
        return False
    if args.trigger and entry.get("trigger") != args.trigger:
        return False
    if args.outcome and entry.get("outcome") != args.outcome:
        return False
    if args.improvement_target:
        target = (entry.get("improvement") or {}).get("target")
        if target != args.improvement_target:
            return False
    if args.document:
        documents = entry.get("documents") or []
        needle = args.document.replace("\\", "/")
        if not any(needle in str(document) for document in documents):
            return False
    return True


def command_append(args: argparse.Namespace) -> int:
    try:
        entry = build_entry(args)
        append_single_write(Path(args.record), entry)
    except (OSError, ValueError) as exc:
        print(f"record append failed: {exc}", file=sys.stderr)
        print(
            "do not fall back to shell redirection or PowerShell text commands",
            file=sys.stderr,
        )
        return 1
    print(json.dumps(entry, ensure_ascii=False))
    return 0


def command_check(args: argparse.Namespace) -> int:
    path = Path(args.record)
    if not path.is_file():
        print(f"record file not found: {path}", file=sys.stderr)
        return 1
    try:
        validate_existing_record(path)
    except (OSError, ValueError) as exc:
        print(f"record check failed: {exc}", file=sys.stderr)
        return 1
    print(f"valid UTF-8 JSONL and record schema: {path}")
    return 0


def command_query(args: argparse.Namespace) -> int:
    if not 1 <= args.tail <= MAX_QUERY_TAIL:
        print(f"--tail must be between 1 and {MAX_QUERY_TAIL}", file=sys.stderr)
        return 2

    path = Path(args.record)
    if not path.is_file():
        print(f"record file not found: {path}", file=sys.stderr)
        return 1

    selected: deque[dict[str, Any]] = deque(maxlen=args.tail)
    for entry in iter_entries(path):
        if matches(entry, args):
            selected.append(entry)

    for entry in selected:
        if args.pretty:
            print(json.dumps(entry, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            print(json.dumps(entry, ensure_ascii=False, separators=(",", ":")))
    return 0


def command_stats(args: argparse.Namespace) -> int:
    path = Path(args.record)
    if not path.is_file():
        print(f"record file not found: {path}", file=sys.stderr)
        return 1

    counters = {
        "skill": Counter(),
        "skill_version": Counter(),
        "skill_usage": Counter(),
        "skill_release": Counter(),
        "schema_version": Counter(),
        "trigger": Counter(),
        "outcome": Counter(),
        "improvement_target": Counter(),
    }
    total = 0
    for entry in iter_entries(path):
        if not matches(entry, args):
            continue
        total += 1
        skill = entry_skill(entry)
        skill_version = entry_skill_version(entry)
        usage = entry_skill_usage(entry)
        counters["skill"][skill] += 1
        counters["skill_version"][skill_version] += 1
        counters["skill_usage"][usage] += 1
        counters["skill_release"][f"{skill}@{skill_version}"] += 1
        counters["schema_version"][str(entry.get("schema_version", UNKNOWN))] += 1
        counters["trigger"][str(entry.get("trigger", UNKNOWN))] += 1
        counters["outcome"][str(entry.get("outcome", UNKNOWN))] += 1
        target = (entry.get("improvement") or {}).get("target", UNKNOWN)
        counters["improvement_target"][str(target)] += 1

    result = {
        "total": total,
        **{name: dict(counter.most_common()) for name, counter in counters.items()},
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def add_filters(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--skill",
        help="exact skill name; use 'none' for schema v3 records created without a skill",
    )
    parser.add_argument(
        "--skill-version",
        help="exact version; legacy invalid/missing versions are 'unknown', no-skill is 'not_applicable'",
    )
    parser.add_argument("--skill-usage", choices=SKILL_USAGES)
    parser.add_argument("--trigger", choices=TRIGGERS)
    parser.add_argument("--outcome", choices=OUTCOMES)
    parser.add_argument("--improvement-target", choices=IMPROVEMENT_TARGETS)
    parser.add_argument("--document", help="substring match against document paths")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Append or inspect bounded UTF-8 JSONL document-change records."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    append_parser = subparsers.add_parser(
        "append", help="append exactly one UTF-8 JSONL record"
    )
    append_parser.add_argument("--record", required=True)
    skill_group = append_parser.add_mutually_exclusive_group(required=True)
    skill_group.add_argument("--skill")
    skill_group.add_argument(
        "--no-skill",
        action="store_true",
        help="record a change where no Agent skill was actually used",
    )
    append_parser.add_argument("--runtime", default=UNKNOWN)
    append_parser.add_argument("--model", default=UNKNOWN)
    append_parser.add_argument("--reasoning-effort", default=UNKNOWN)
    append_parser.add_argument("--action", choices=ACTIONS, required=True)
    append_parser.add_argument("--document", action="append", required=True)
    append_parser.add_argument("--trigger", choices=TRIGGERS, required=True)
    append_parser.add_argument("--problem", required=True)
    append_parser.add_argument("--root-cause", default="")
    append_parser.add_argument("--change", required=True)
    append_parser.add_argument(
        "--validation-status", choices=VALIDATION_STATUSES, required=True
    )
    append_parser.add_argument("--validation", default="")
    append_parser.add_argument("--outcome", choices=OUTCOMES, required=True)
    append_parser.add_argument(
        "--improvement-target", choices=IMPROVEMENT_TARGETS, default="none"
    )
    append_parser.add_argument("--prevention", default="")
    append_parser.add_argument("--commit", default="")
    append_parser.set_defaults(func=command_append)

    check_parser = subparsers.add_parser(
        "check", help="strictly validate UTF-8 JSONL plus record schema"
    )
    check_parser.add_argument("--record", required=True)
    check_parser.set_defaults(func=command_check)

    query_parser = subparsers.add_parser(
        "query", help="print only the latest bounded matching records"
    )
    query_parser.add_argument("--record", required=True)
    query_parser.add_argument("--tail", type=int, default=20)
    query_parser.add_argument("--pretty", action="store_true")
    add_filters(query_parser)
    query_parser.set_defaults(func=command_query)

    stats_parser = subparsers.add_parser(
        "stats", help="stream the log and print aggregate counts only"
    )
    stats_parser.add_argument("--record", required=True)
    add_filters(stats_parser)
    stats_parser.set_defaults(func=command_stats)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
