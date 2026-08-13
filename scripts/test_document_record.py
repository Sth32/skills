#!/usr/bin/env python3
"""Runtime regression tests for document-record attribution, v4 feedback, and append isolation."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET_SKILL = "game-config"
TARGET_SKILL_DIR = ROOT / "skills" / TARGET_SKILL
TARGET_SKILL_FILE = TARGET_SKILL_DIR / "SKILL.md"
TARGET_WRITER = TARGET_SKILL_DIR / "scripts" / "document_record.py"
CANONICAL_WRITER = ROOT / "scripts" / "document_record.py"
WRONG_WRITER = ROOT / "skills" / "game-spec" / "scripts" / "document_record.py"
VERSION_RE = re.compile(r'(?m)^\s{2}version:\s*["\']?(\d+\.\d+\.\d+)["\']?\s*$')


def run(writer: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(writer), *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def fail(message: str, result: subprocess.CompletedProcess[str] | None = None) -> int:
    print(f"FAIL {message}", file=sys.stderr)
    if result is not None:
        if result.stdout:
            print(result.stdout, file=sys.stderr)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
    return 1


def append_args(record: Path, docs: list[str]) -> list[str]:
    args = ["append", "--record", str(record), "--action", "update"]
    for document in docs:
        args += ["--document", document]
    args += [
        "--trigger", "self_check",
        "--reason", "regression test logical change",
        "--change", "append regression record",
        "--validation-status", "passed",
        "--validation", "runtime smoke test",
        "--outcome", "success",
    ]
    return args


def main() -> int:
    text = TARGET_SKILL_FILE.read_text(encoding="utf-8")
    match = VERSION_RE.search(text)
    if not match:
        return fail(f"cannot parse {TARGET_SKILL_FILE} version")
    expected_version = match.group(1)

    with tempfile.TemporaryDirectory() as tmp:
        record = Path(tmp) / "record.jsonl"
        legacy_v1 = {
            "schema_version": 1,
            "timestamp": "2026-01-01T00:00:00+00:00",
            "skill": TARGET_SKILL,
            "action": "update",
            "documents": ["legacy-v1.md"],
        }
        malformed_v2 = {
            "schema_version": 2,
            "timestamp": "2026-02-01T00:00:00+00:00",
            "skill": TARGET_SKILL,
            "action": "update",
            "documents": ["legacy-v2.md"],
        }
        legacy_v3 = {
            "schema_version": 3,
            "timestamp": "2026-03-01T00:00:00+00:00",
            "skill_usage": "used",
            "skill": TARGET_SKILL,
            "skill_version": expected_version,
            "runtime": "unknown",
            "model": "unknown",
            "reasoning_effort": "unknown",
            "action": "update",
            "documents": ["legacy-v3.md"],
            "trigger": "review_feedback",
            "problem": "legacy generalizable issue",
            "root_cause": "legacy cause",
            "change_summary": "legacy fix",
            "validation": {"status": "passed", "evidence": "legacy"},
            "outcome": "success",
            "improvement": {"target": "skill", "prevention": "legacy prevention"},
            "commit": None,
        }
        record.write_text(
            "\n".join(json.dumps(item, ensure_ascii=False) for item in (legacy_v1, malformed_v2, legacy_v3)) + "\n",
            encoding="utf-8",
        )

        append = run(
            TARGET_WRITER,
            *append_args(record, [
                "docs/requirements/test/03-程序实现澄清.md",
                "docs/requirements/test/05-框架实现方案.md",
            ]),
            "--skill", TARGET_SKILL,
        )
        if append.returncode != 0:
            return fail("skill-attributed v4 append was blocked by malformed history", append)

        lines = record.read_text(encoding="utf-8").splitlines()
        if len(lines) != 4:
            return fail(f"expected 4 records after grouped append, found {len(lines)}")
        current = json.loads(lines[-1])
        if current.get("schema_version") != 4:
            return fail(f"expected schema_version=4, got {current.get('schema_version')!r}")
        if current.get("skill_usage") != "used" or current.get("skill") != TARGET_SKILL:
            return fail("skill attribution missing from v4 record")
        if current.get("skill_version") != expected_version:
            return fail(f"expected skill_version={expected_version!r}, got {current.get('skill_version')!r}")
        if len(current.get("documents") or []) != 2:
            return fail("one logical change did not retain both document paths")
        if (current.get("feedback") or {}).get("signal") != "none":
            return fail("normal progress must default to feedback.signal=none")
        if "problem" in current or "improvement" in current:
            return fail("schema v4 must not emit legacy problem/improvement fields")

        actionable = run(
            TARGET_WRITER,
            *append_args(record, ["docs/requirements/test/06-完整实现方案.md"]),
            "--skill", TARGET_SKILL,
            "--trigger", "user_correction",
            "--feedback-signal", "actionable",
            "--feedback-category", "skill",
            "--feedback-pattern", "contract_propagation_gap",
            "--feedback-severity", "high",
            "--root-cause", "structural change was updated locally without propagation scan",
            "--prevention", "require impact propagation scan",
        )
        if actionable.returncode != 0:
            return fail("actionable feedback append failed", actionable)

        check = run(CANONICAL_WRITER, "check", "--record", str(record))
        if check.returncode == 0:
            return fail("strict check unexpectedly accepted malformed schema v2 history", check)
        if "schema v2 requires semantic skill_version" not in check.stderr:
            return fail("strict check did not identify missing historical skill_version", check)

        query_unknown = run(
            CANONICAL_WRITER, "query", "--record", str(record),
            "--skill", TARGET_SKILL, "--skill-version", "unknown", "--tail", "20",
        )
        if query_unknown.returncode != 0:
            return fail("unknown-version query failed", query_unknown)
        unknown_rows = [json.loads(line) for line in query_unknown.stdout.splitlines() if line.strip()]
        if len(unknown_rows) != 2:
            return fail(f"expected v1 + malformed v2 in unknown bucket, found {len(unknown_rows)}", query_unknown)

        no_skill = run(CANONICAL_WRITER, *append_args(record, ["manual-note.md"]), "--no-skill")
        if no_skill.returncode != 0:
            return fail("no-skill append failed", no_skill)
        no_skill_entry = json.loads(record.read_text(encoding="utf-8").splitlines()[-1])
        if no_skill_entry.get("schema_version") != 4 or no_skill_entry.get("skill_usage") != "not_used":
            return fail("no-skill entry did not use v4 not_used attribution")
        if no_skill_entry.get("skill") is not None or no_skill_entry.get("skill_version") is not None:
            return fail("no-skill entry must use skill/version=null")

        invalid_actionable = run(
            TARGET_WRITER,
            *append_args(record, ["invalid.md"]),
            "--skill", TARGET_SKILL,
            "--feedback-signal", "actionable",
            "--feedback-category", "skill",
            "--feedback-pattern", "missing_prevention",
            "--feedback-severity", "medium",
            "--root-cause", "known cause",
        )
        if invalid_actionable.returncode == 0:
            return fail("actionable feedback without prevention unexpectedly succeeded")

        stats = run(CANONICAL_WRITER, "stats", "--record", str(record))
        if stats.returncode != 0:
            return fail("stats failed", stats)
        payload = json.loads(stats.stdout)
        versions = payload.get("skill_version", {})
        usages = payload.get("skill_usage", {})
        patterns = payload.get("feedback_pattern", {})
        if versions.get("unknown") != 2:
            return fail(f"expected two unknown historical versions: {versions!r}")
        if versions.get(expected_version) != 3:
            return fail(f"expected legacy v3 + two v4 current-version rows: {versions!r}")
        if versions.get("not_applicable") != 1 or usages.get("not_used") != 1:
            return fail("no-skill stats bucket missing")
        if patterns.get("contract_propagation_gap") != 1 or patterns.get("legacy_unclassified") != 1:
            return fail(f"feedback patterns were not aggregated correctly: {patterns!r}")

        report = run(
            CANONICAL_WRITER, "report", "--record", str(record),
            "--skill", TARGET_SKILL, "--skill-version", expected_version,
        )
        if report.returncode != 0:
            return fail("report failed", report)
        report_payload = json.loads(report.stdout)
        if report_payload.get("actionable_feedback") != 1 or report_payload.get("candidate_feedback") != 1:
            return fail(f"report feedback counts wrong: {report_payload!r}")
        top_patterns = {row["pattern"]: row["count"] for row in report_payload.get("top_patterns", [])}
        if top_patterns.get("contract_propagation_gap") != 1:
            return fail(f"report top patterns missing explicit pattern: {top_patterns!r}")
        if "metadata_coverage" not in report_payload:
            return fail("report missing metadata coverage")

        before = record.read_bytes()
        mismatch = run(WRONG_WRITER, *append_args(record, ["wrong-writer.md"]), "--skill", TARGET_SKILL)
        if mismatch.returncode == 0:
            return fail("wrong skill writer unexpectedly succeeded", mismatch)
        if record.read_bytes() != before:
            return fail("wrong skill writer modified record before rejecting")

        corrupt = Path(tmp) / "corrupt.jsonl"
        corrupt.write_bytes(b'{"schema_version":1}\n{"broken":\n')
        blocked = run(CANONICAL_WRITER, *append_args(corrupt, ["blocked.md"]), "--no-skill")
        if blocked.returncode == 0:
            return fail("append continued after broken JSON framing", blocked)

    print(f"PASS document record runtime v4: {TARGET_SKILL}@{expected_version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
