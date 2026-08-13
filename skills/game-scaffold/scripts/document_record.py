#!/usr/bin/env python3
"""Append/query bounded UTF-8 document-change records."""
from __future__ import annotations

import argparse, json, os, re, sys
from collections import Counter, deque
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = 4
UNKNOWN = "unknown"
NOT_APPLICABLE = "not_applicable"
MAX_TEXT_LENGTH = 1000
MAX_QUERY_TAIL = 200
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")
PATTERN_RE = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
SKILL_NAME_RE = re.compile(r'(?m)^name:\s*["\']?([^"\'\n]+)["\']?\s*$')
SKILL_VERSION_RE = re.compile(r'(?m)^\s{2}version:\s*["\']?(\d+\.\d+\.\d+)["\']?\s*$')
ACTIONS = ("create", "update", "delete", "rename")
TRIGGERS = ("initial_generation", "user_change", "user_correction", "user_feedback", "self_check", "review_feedback", "test_failure", "code_change", "upstream_change", "other")
VALIDATION_STATUSES = ("passed", "partial", "failed", "not_run")
OUTCOMES = ("success", "partial", "failed")
SKILL_USAGES = ("used", "not_used")
FEEDBACK_SIGNALS = ("none", "candidate", "actionable")
FEEDBACK_CATEGORIES = ("skill", "template", "eval", "tooling", "project_context", "agent_execution")
FEEDBACK_SEVERITIES = ("low", "medium", "high")
LEGACY_TARGETS = (*FEEDBACK_CATEGORIES[:-1], "none")


def bounded(value: str | None, field: str, allow_empty: bool = True) -> str:
    value = (value or "").strip()
    if not allow_empty and not value:
        raise ValueError(f"{field} must not be empty")
    if len(value) > MAX_TEXT_LENGTH:
        raise ValueError(f"{field} exceeds {MAX_TEXT_LENGTH} characters")
    return value


def documents(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        value = value.strip().replace("\\", "/")
        if value and value not in result:
            result.append(value)
    if not result:
        raise ValueError("at least one --document is required")
    return result


def skill_identity(expected: str) -> tuple[str, str]:
    skill_file = Path(__file__).resolve().parents[1] / "SKILL.md"
    if not skill_file.is_file():
        raise ValueError("invoke the writer bundled under <skill-root>/scripts/document_record.py")
    try:
        text = skill_file.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{skill_file} is not valid UTF-8") from exc
    name = SKILL_NAME_RE.search(text)
    version = SKILL_VERSION_RE.search(text)
    if not name or not version:
        raise ValueError(f"{skill_file} is missing frontmatter name or semantic metadata.version")
    actual, version_text = name.group(1).strip(), version.group(1)
    if actual != expected:
        raise ValueError(f"--skill={expected!r} does not match bundled SKILL.md name={actual!r}")
    return actual, version_text


def decode(path: Path, line: int, raw: bytes) -> dict[str, Any] | None:
    try:
        text = raw.decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise ValueError(f"{path}:{line} is not UTF-8") from exc
    if not text:
        return None
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path}:{line} is not valid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{path}:{line} must contain one JSON object")
    return value


def validate_attribution(path: Path, line: int, value: dict[str, Any], schema: int) -> None:
    usage, skill, version = value.get("skill_usage"), value.get("skill"), value.get("skill_version")
    if usage not in SKILL_USAGES:
        raise ValueError(f"{path}:{line} schema v{schema} requires skill_usage=used|not_used")
    if usage == "used":
        if not isinstance(skill, str) or not skill.strip() or not isinstance(version, str) or not SEMVER_RE.fullmatch(version):
            raise ValueError(f"{path}:{line} schema v{schema} skill_usage=used requires skill and semantic skill_version")
    elif skill is not None or version is not None:
        raise ValueError(f"{path}:{line} schema v{schema} skill_usage=not_used requires skill/version=null")


def validate_schema(path: Path, line: int, value: dict[str, Any]) -> None:
    schema = value.get("schema_version")
    if schema == 1:
        return
    if schema == 2:
        version = value.get("skill_version")
        if not isinstance(version, str) or not SEMVER_RE.fullmatch(version):
            raise ValueError(f"{path}:{line} schema v2 requires semantic skill_version")
        return
    if schema == 3:
        validate_attribution(path, line, value, 3)
        return
    if schema != 4:
        raise ValueError(f"{path}:{line} has unsupported schema_version={schema!r}")
    validate_attribution(path, line, value, 4)
    if not isinstance(value.get("reason"), str) or not value["reason"].strip():
        raise ValueError(f"{path}:{line} schema v4 requires non-empty reason")
    feedback = value.get("feedback")
    if not isinstance(feedback, dict) or feedback.get("signal") not in FEEDBACK_SIGNALS:
        raise ValueError(f"{path}:{line} schema v4 requires valid feedback object")
    signal = feedback["signal"]
    if signal == "none":
        if any(feedback.get(k) not in (None, "") for k in ("category", "pattern", "severity", "root_cause", "prevention")):
            raise ValueError(f"{path}:{line} feedback.signal=none requires null detail fields")
        return
    if feedback.get("category") not in FEEDBACK_CATEGORIES or feedback.get("severity") not in FEEDBACK_SEVERITIES:
        raise ValueError(f"{path}:{line} candidate/actionable feedback requires category and severity")
    pattern = feedback.get("pattern")
    if not isinstance(pattern, str) or not PATTERN_RE.fullmatch(pattern):
        raise ValueError(f"{path}:{line} feedback.pattern must be snake_case")
    if signal == "actionable" and any(not isinstance(feedback.get(k), str) or not feedback[k].strip() for k in ("root_cause", "prevention")):
        raise ValueError(f"{path}:{line} actionable feedback requires root_cause and prevention")


def scan(path: Path, strict: bool) -> Iterable[dict[str, Any]]:
    with path.open("rb") as handle:
        for line, raw in enumerate(handle, 1):
            if not raw.strip():
                continue
            value = decode(path, line, raw)
            if value is None:
                continue
            if strict:
                validate_schema(path, line, value)
            else:
                try:
                    validate_schema(path, line, value)
                except ValueError as exc:
                    print(f"warning: legacy/invalid schema row retained as best-effort data: {exc}", file=sys.stderr)
            yield value


def validate_append(path: Path) -> None:
    if not path.exists():
        return
    if not path.is_file():
        raise ValueError(f"record path is not a file: {path}")
    with path.open("rb") as handle:
        for line, raw in enumerate(handle, 1):
            decode(path, line, raw)


def feedback_from_args(args: argparse.Namespace) -> dict[str, Any]:
    signal, category = args.feedback_signal, args.feedback_category
    pattern = bounded(args.feedback_pattern, "feedback_pattern")
    severity = args.feedback_severity
    root_cause, prevention = bounded(args.root_cause, "root_cause"), bounded(args.prevention, "prevention")
    if signal == "none" and args.improvement_target != "none":
        signal, category, pattern, severity = "candidate", args.improvement_target, pattern or "legacy_unclassified", severity or "medium"
    if signal == "none":
        return {"signal": "none", "category": None, "pattern": None, "severity": None, "root_cause": None, "prevention": None}
    if category not in FEEDBACK_CATEGORIES or severity not in FEEDBACK_SEVERITIES:
        raise ValueError("candidate/actionable feedback requires --feedback-category and --feedback-severity")
    if not pattern or not PATTERN_RE.fullmatch(pattern):
        raise ValueError("--feedback-pattern is required and must be snake_case")
    if signal == "actionable" and (not root_cause or not prevention):
        raise ValueError("actionable feedback requires --root-cause and --prevention")
    return {"signal": signal, "category": category, "pattern": pattern, "severity": severity, "root_cause": root_cause or UNKNOWN, "prevention": prevention or None}


def build_entry(args: argparse.Namespace) -> dict[str, Any]:
    if args.no_skill:
        skill, version, usage = None, None, "not_used"
    else:
        skill, version = skill_identity(bounded(args.skill, "skill", False))
        usage = "used"
    return {
        "schema_version": 4,
        "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
        "skill_usage": usage,
        "skill": skill,
        "skill_version": version,
        "runtime": bounded(args.runtime, "runtime") or UNKNOWN,
        "model": bounded(args.model, "model") or UNKNOWN,
        "reasoning_effort": bounded(args.reasoning_effort, "reasoning_effort") or UNKNOWN,
        "action": args.action,
        "documents": documents(args.document),
        "trigger": args.trigger,
        "reason": bounded(args.reason, "reason", False),
        "change_summary": bounded(args.change, "change_summary", False),
        "validation": {"status": args.validation_status, "evidence": bounded(args.validation, "validation")},
        "outcome": args.outcome,
        "feedback": feedback_from_args(args),
        "commit": bounded(args.commit, "commit") or None,
    }


def append_record(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    validate_append(path)
    raw = (json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND | (getattr(os, "O_BINARY", 0))
    fd = os.open(path, flags, 0o666)
    try:
        if os.write(fd, raw) != len(raw):
            raise OSError("short append")
        os.fsync(fd)
    finally:
        os.close(fd)


def entry_skill(entry: dict[str, Any]) -> str:
    return "none" if entry.get("schema_version") in (3, 4) and entry.get("skill_usage") == "not_used" else (entry.get("skill") or UNKNOWN)


def entry_version(entry: dict[str, Any]) -> str:
    if entry.get("schema_version") in (3, 4) and entry.get("skill_usage") == "not_used":
        return NOT_APPLICABLE
    value = entry.get("skill_version")
    return value if isinstance(value, str) and SEMVER_RE.fullmatch(value) else UNKNOWN


def entry_usage(entry: dict[str, Any]) -> str:
    if entry.get("schema_version") in (3, 4):
        return entry.get("skill_usage") if entry.get("skill_usage") in SKILL_USAGES else UNKNOWN
    return "used" if entry_skill(entry) != UNKNOWN else UNKNOWN


def entry_feedback(entry: dict[str, Any]) -> dict[str, Any]:
    if entry.get("schema_version") == 4 and isinstance(entry.get("feedback"), dict):
        return entry["feedback"]
    legacy = entry.get("improvement")
    if isinstance(legacy, dict) and legacy.get("target") in FEEDBACK_CATEGORIES:
        return {"signal": "candidate", "category": legacy["target"], "pattern": "legacy_unclassified", "severity": "medium", "root_cause": entry.get("root_cause") or UNKNOWN, "prevention": legacy.get("prevention") or None}
    return {"signal": "none", "category": None, "pattern": None, "severity": None, "root_cause": None, "prevention": None}


def matches(entry: dict[str, Any], args: argparse.Namespace) -> bool:
    feedback = entry_feedback(entry)
    checks = (
        (getattr(args, "skill", None), entry_skill(entry)),
        (getattr(args, "skill_version", None), entry_version(entry)),
        (getattr(args, "skill_usage", None), entry_usage(entry)),
        (getattr(args, "trigger", None), entry.get("trigger")),
        (getattr(args, "outcome", None), entry.get("outcome")),
        (getattr(args, "feedback_signal", None), feedback.get("signal")),
        (getattr(args, "feedback_category", None), feedback.get("category")),
        (getattr(args, "feedback_pattern", None), feedback.get("pattern")),
    )
    if any(wanted and wanted != actual for wanted, actual in checks):
        return False
    if getattr(args, "document", None):
        needle = args.document.replace("\\", "/")
        return any(needle in str(path) for path in entry.get("documents") or [])
    return True


def command_append(args: argparse.Namespace) -> int:
    try:
        payload = build_entry(args)
        append_record(Path(args.record), payload)
    except (OSError, ValueError) as exc:
        print(f"record append failed: {exc}", file=sys.stderr)
        print("do not fall back to shell redirection or PowerShell text commands", file=sys.stderr)
        return 1
    print(json.dumps(payload, ensure_ascii=False))
    return 0


def command_check(args: argparse.Namespace) -> int:
    path = Path(args.record)
    if not path.is_file():
        print(f"record file not found: {path}", file=sys.stderr); return 1
    try:
        list(scan(path, True))
    except (OSError, ValueError) as exc:
        print(f"record check failed: {exc}", file=sys.stderr); return 1
    print(f"valid UTF-8 JSONL and record schema: {path}"); return 0


def command_query(args: argparse.Namespace) -> int:
    if not 1 <= args.tail <= MAX_QUERY_TAIL:
        print(f"--tail must be between 1 and {MAX_QUERY_TAIL}", file=sys.stderr); return 2
    path = Path(args.record)
    if not path.is_file():
        print(f"record file not found: {path}", file=sys.stderr); return 1
    selected = deque((entry for entry in scan(path, False) if matches(entry, args)), maxlen=args.tail)
    for entry in selected:
        print(json.dumps(entry, ensure_ascii=False, indent=2 if args.pretty else None, sort_keys=args.pretty, separators=None if args.pretty else (",", ":")))
    return 0


def filtered(path: Path, args: argparse.Namespace) -> Iterable[dict[str, Any]]:
    for entry in scan(path, False):
        if matches(entry, args):
            yield entry


def command_stats(args: argparse.Namespace) -> int:
    path = Path(args.record)
    if not path.is_file():
        print(f"record file not found: {path}", file=sys.stderr); return 1
    names = ("skill", "skill_version", "skill_usage", "skill_release", "schema_version", "trigger", "outcome", "feedback_signal", "feedback_category", "feedback_pattern", "feedback_severity")
    counters = {name: Counter() for name in names}
    total = 0
    for entry in filtered(path, args):
        total += 1; skill, version, usage, feedback = entry_skill(entry), entry_version(entry), entry_usage(entry), entry_feedback(entry)
        values = {"skill": skill, "skill_version": version, "skill_usage": usage, "skill_release": f"{skill}@{version}", "schema_version": str(entry.get("schema_version", UNKNOWN)), "trigger": str(entry.get("trigger", UNKNOWN)), "outcome": str(entry.get("outcome", UNKNOWN)), "feedback_signal": str(feedback.get("signal", UNKNOWN)), "feedback_category": feedback.get("category"), "feedback_pattern": feedback.get("pattern"), "feedback_severity": feedback.get("severity")}
        for name, value in values.items():
            if value:
                counters[name][str(value)] += 1
    print(json.dumps({"total": total, **{name: dict(counter.most_common()) for name, counter in counters.items()}}, ensure_ascii=False, indent=2, sort_keys=True)); return 0


def command_report(args: argparse.Namespace) -> int:
    path = Path(args.record)
    if not path.is_file():
        print(f"record file not found: {path}", file=sys.stderr); return 1
    rows = list(filtered(path, args)); total = len(rows)
    signals, categories, patterns, severities, metadata = Counter(), Counter(), Counter(), Counter(), Counter()
    explicit_v4 = 0
    for entry in rows:
        explicit_v4 += entry.get("schema_version") == 4
        feedback = entry_feedback(entry); signals[feedback["signal"]] += 1
        for counter, key in ((categories, "category"), (patterns, "pattern"), (severities, "severity")):
            if feedback.get(key): counter[str(feedback[key])] += 1
        for field in ("runtime", "model", "reasoning_effort"):
            if isinstance(entry.get(field), str) and entry[field] and entry[field] != UNKNOWN: metadata[field] += 1
    coverage = {field: {"known": metadata[field], "total": total, "percent": round(metadata[field] / total * 100, 1) if total else 0.0} for field in ("runtime", "model", "reasoning_effort")}
    result = {"total": total, "schema_v4": explicit_v4, "legacy_records": total - explicit_v4, "actionable_feedback": signals["actionable"], "candidate_feedback": signals["candidate"], "feedback_signal": dict(signals.most_common()), "feedback_category": dict(categories.most_common()), "top_patterns": [{"pattern": key, "count": count} for key, count in patterns.most_common(args.top)], "feedback_severity": dict(severities.most_common()), "metadata_coverage": coverage}
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)); return 0


def add_filters(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--skill")
    parser.add_argument("--skill-version")
    parser.add_argument("--skill-usage", choices=SKILL_USAGES)
    parser.add_argument("--trigger", choices=TRIGGERS)
    parser.add_argument("--outcome", choices=OUTCOMES)
    parser.add_argument("--feedback-signal", choices=FEEDBACK_SIGNALS)
    parser.add_argument("--feedback-category", choices=FEEDBACK_CATEGORIES)
    parser.add_argument("--feedback-pattern")
    parser.add_argument("--document")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Append or inspect bounded UTF-8 JSONL document-change records.")
    subs = parser.add_subparsers(dest="command", required=True)
    append = subs.add_parser("append", help="append one record for one logical change")
    append.add_argument("--record", required=True)
    skill = append.add_mutually_exclusive_group(required=True); skill.add_argument("--skill"); skill.add_argument("--no-skill", action="store_true")
    append.add_argument("--runtime", default=UNKNOWN); append.add_argument("--model", default=UNKNOWN); append.add_argument("--reasoning-effort", default=UNKNOWN)
    append.add_argument("--action", choices=ACTIONS, required=True); append.add_argument("--document", action="append", required=True); append.add_argument("--trigger", choices=TRIGGERS, required=True)
    append.add_argument("--reason", "--problem", dest="reason", required=True); append.add_argument("--change", required=True); append.add_argument("--validation-status", choices=VALIDATION_STATUSES, required=True); append.add_argument("--validation", default=""); append.add_argument("--outcome", choices=OUTCOMES, required=True)
    append.add_argument("--feedback-signal", choices=FEEDBACK_SIGNALS, default="none"); append.add_argument("--feedback-category", choices=FEEDBACK_CATEGORIES); append.add_argument("--feedback-pattern", default=""); append.add_argument("--feedback-severity", choices=FEEDBACK_SEVERITIES); append.add_argument("--root-cause", default=""); append.add_argument("--prevention", default="")
    append.add_argument("--improvement-target", choices=LEGACY_TARGETS, default="none", help=argparse.SUPPRESS); append.add_argument("--commit", default=""); append.set_defaults(func=command_append)
    check = subs.add_parser("check"); check.add_argument("--record", required=True); check.set_defaults(func=command_check)
    query = subs.add_parser("query"); query.add_argument("--record", required=True); query.add_argument("--tail", type=int, default=20); query.add_argument("--pretty", action="store_true"); add_filters(query); query.set_defaults(func=command_query)
    stats = subs.add_parser("stats"); stats.add_argument("--record", required=True); add_filters(stats); stats.set_defaults(func=command_stats)
    report = subs.add_parser("report"); report.add_argument("--record", required=True); report.add_argument("--top", type=int, default=10); add_filters(report); report.set_defaults(func=command_report)
    return parser


def main() -> int:
    parser = build_parser(); args = parser.parse_args()
    if getattr(args, "top", 1) < 1: parser.error("--top must be >= 1")
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
