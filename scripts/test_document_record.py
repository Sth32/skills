#!/usr/bin/env python3
"""Runtime regression test for version-aware document records."""

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
WRONG_WRITER = ROOT / "skills" / "game-spec" / "scripts" / "document_record.py"
VERSION_RE = re.compile(r'(?m)^\s{2}version:\s*["\']?(\d+\.\d+\.\d+)["\']?\s*$')


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args],
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


def main() -> int:
    text = TARGET_SKILL_FILE.read_text(encoding="utf-8")
    match = VERSION_RE.search(text)
    if not match:
        return fail(f"cannot parse {TARGET_SKILL_FILE} version")
    expected_version = match.group(1)

    with tempfile.TemporaryDirectory() as tmp:
        record = Path(tmp) / "record.jsonl"
        legacy = {
            "schema_version": 1,
            "timestamp": "2026-01-01T00:00:00+00:00",
            "skill": TARGET_SKILL,
            "runtime": "legacy",
            "model": "legacy",
            "reasoning_effort": "legacy",
            "action": "update",
            "documents": ["legacy.md"],
            "trigger": "self_check",
            "problem": "legacy record",
            "root_cause": "unknown",
            "change_summary": "legacy change",
            "validation": {"status": "passed", "evidence": "legacy"},
            "outcome": "success",
            "improvement": {"target": "none", "prevention": ""},
            "commit": None,
        }
        record.write_text(json.dumps(legacy, ensure_ascii=False) + "\n", encoding="utf-8")

        append = run(
            str(TARGET_WRITER),
            "append",
            "--record",
            str(record),
            "--skill",
            TARGET_SKILL,
            "--runtime",
            "ci",
            "--model",
            "test-model",
            "--reasoning-effort",
            "test",
            "--action",
            "update",
            "--document",
            "docs/requirements/test/04-配置规划.md",
            "--trigger",
            "self_check",
            "--problem",
            "verify automatic skill version",
            "--change",
            "append versioned test record",
            "--validation-status",
            "passed",
            "--validation",
            "runtime smoke test",
            "--outcome",
            "success",
            "--improvement-target",
            "none",
        )
        if append.returncode != 0:
            return fail("versioned append failed", append)

        lines = record.read_text(encoding="utf-8").splitlines()
        if len(lines) != 2:
            return fail(f"expected 2 records, found {len(lines)}")
        current = json.loads(lines[1])
        if current.get("schema_version") != 2:
            return fail(f"expected schema_version=2, got {current.get('schema_version')!r}")
        if current.get("skill") != TARGET_SKILL:
            return fail(f"unexpected skill {current.get('skill')!r}")
        if current.get("skill_version") != expected_version:
            return fail(
                f"expected skill_version={expected_version!r}, got {current.get('skill_version')!r}"
            )

        query_current = run(
            str(TARGET_WRITER),
            "query",
            "--record",
            str(record),
            "--skill",
            TARGET_SKILL,
            "--skill-version",
            expected_version,
            "--tail",
            "20",
        )
        if query_current.returncode != 0:
            return fail("version-filtered query failed", query_current)
        current_rows = [line for line in query_current.stdout.splitlines() if line.strip()]
        if len(current_rows) != 1 or json.loads(current_rows[0]).get("schema_version") != 2:
            return fail("version-filtered query did not isolate current version", query_current)

        query_legacy = run(
            str(TARGET_WRITER),
            "query",
            "--record",
            str(record),
            "--skill",
            TARGET_SKILL,
            "--skill-version",
            "unknown",
            "--tail",
            "20",
        )
        if query_legacy.returncode != 0:
            return fail("legacy-version query failed", query_legacy)
        legacy_rows = [line for line in query_legacy.stdout.splitlines() if line.strip()]
        if len(legacy_rows) != 1 or json.loads(legacy_rows[0]).get("schema_version") != 1:
            return fail("legacy schema v1 record was not isolated as unknown", query_legacy)

        stats = run(
            str(TARGET_WRITER),
            "stats",
            "--record",
            str(record),
            "--skill",
            TARGET_SKILL,
        )
        if stats.returncode != 0:
            return fail("stats failed", stats)
        payload = json.loads(stats.stdout)
        versions = payload.get("skill_version", {})
        releases = payload.get("skill_release", {})
        if versions.get("unknown") != 1 or versions.get(expected_version) != 1:
            return fail(f"unexpected skill_version stats: {versions!r}")
        if releases.get(f"{TARGET_SKILL}@unknown") != 1:
            return fail(f"legacy release bucket missing: {releases!r}")
        if releases.get(f"{TARGET_SKILL}@{expected_version}") != 1:
            return fail(f"current release bucket missing: {releases!r}")

        before = record.read_bytes()
        mismatch = run(
            str(WRONG_WRITER),
            "append",
            "--record",
            str(record),
            "--skill",
            TARGET_SKILL,
            "--action",
            "update",
            "--document",
            "wrong-writer.md",
            "--trigger",
            "self_check",
            "--problem",
            "must reject wrong bundled writer",
            "--change",
            "should not be written",
            "--validation-status",
            "not_run",
            "--outcome",
            "failed",
            "--improvement-target",
            "none",
        )
        if mismatch.returncode == 0:
            return fail("wrong skill writer unexpectedly succeeded", mismatch)
        if record.read_bytes() != before:
            return fail("wrong skill writer modified record before rejecting")

    print(f"PASS document record runtime: {TARGET_SKILL}@{expected_version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
