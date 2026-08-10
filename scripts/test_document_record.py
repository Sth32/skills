#!/usr/bin/env python3
"""Runtime regression tests for document-record attribution and append isolation."""

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


def append_args(record: Path, document: str) -> list[str]:
    return [
        "append",
        "--record",
        str(record),
        "--action",
        "update",
        "--document",
        document,
        "--trigger",
        "self_check",
        "--problem",
        "regression test",
        "--change",
        "append regression record",
        "--validation-status",
        "passed",
        "--validation",
        "runtime smoke test",
        "--outcome",
        "success",
        "--improvement-target",
        "none",
    ]


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
        record.write_text(
            json.dumps(legacy_v1, ensure_ascii=False)
            + "\n"
            + json.dumps(malformed_v2, ensure_ascii=False)
            + "\n",
            encoding="utf-8",
        )

        append = run(
            TARGET_WRITER,
            *append_args(record, "docs/requirements/test/04-配置规划.md"),
            "--skill",
            TARGET_SKILL,
        )
        if append.returncode != 0:
            return fail("skill-attributed append was blocked by malformed history", append)

        lines = record.read_text(encoding="utf-8").splitlines()
        if len(lines) != 3:
            return fail(f"expected 3 records after skill append, found {len(lines)}")
        current = json.loads(lines[-1])
        if current.get("schema_version") != 3:
            return fail(f"expected schema_version=3, got {current.get('schema_version')!r}")
        if current.get("skill_usage") != "used":
            return fail(f"expected skill_usage=used, got {current.get('skill_usage')!r}")
        if current.get("skill") != TARGET_SKILL:
            return fail(f"unexpected skill {current.get('skill')!r}")
        if current.get("skill_version") != expected_version:
            return fail(
                f"expected skill_version={expected_version!r}, "
                f"got {current.get('skill_version')!r}"
            )

        check = run(CANONICAL_WRITER, "check", "--record", str(record))
        if check.returncode == 0:
            return fail("strict check unexpectedly accepted malformed schema v2 history", check)
        if "schema v2 requires semantic skill_version" not in check.stderr:
            return fail("strict check did not identify missing historical skill_version", check)

        query_unknown = run(
            CANONICAL_WRITER,
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
        if query_unknown.returncode != 0:
            return fail("unknown-version query failed", query_unknown)
        unknown_rows = [
            json.loads(line)
            for line in query_unknown.stdout.splitlines()
            if line.strip()
        ]
        if len(unknown_rows) != 2:
            return fail(
                f"expected v1 + malformed v2 in unknown bucket, found {len(unknown_rows)}",
                query_unknown,
            )

        no_skill = run(
            CANONICAL_WRITER,
            *append_args(record, "manual-note.md"),
            "--no-skill",
        )
        if no_skill.returncode != 0:
            return fail("no-skill append failed", no_skill)
        no_skill_entry = json.loads(record.read_text(encoding="utf-8").splitlines()[-1])
        if no_skill_entry.get("schema_version") != 3:
            return fail("no-skill entry did not use schema v3")
        if no_skill_entry.get("skill_usage") != "not_used":
            return fail("no-skill entry missing skill_usage=not_used")
        if no_skill_entry.get("skill") is not None:
            return fail("no-skill entry must use skill=null")
        if no_skill_entry.get("skill_version") is not None:
            return fail("no-skill entry must use skill_version=null")

        stats = run(CANONICAL_WRITER, "stats", "--record", str(record))
        if stats.returncode != 0:
            return fail("stats failed", stats)
        payload = json.loads(stats.stdout)
        versions = payload.get("skill_version", {})
        usages = payload.get("skill_usage", {})
        releases = payload.get("skill_release", {})
        if versions.get("unknown") != 2:
            return fail(f"expected two unknown historical versions: {versions!r}")
        if versions.get(expected_version) != 1:
            return fail(f"current version bucket missing: {versions!r}")
        if versions.get("not_applicable") != 1:
            return fail(f"no-skill version bucket missing: {versions!r}")
        if usages.get("not_used") != 1:
            return fail(f"no-skill usage bucket missing: {usages!r}")
        if releases.get("none@not_applicable") != 1:
            return fail(f"no-skill release bucket missing: {releases!r}")

        before = record.read_bytes()
        mismatch = run(
            WRONG_WRITER,
            *append_args(record, "wrong-writer.md"),
            "--skill",
            TARGET_SKILL,
        )
        if mismatch.returncode == 0:
            return fail("wrong skill writer unexpectedly succeeded", mismatch)
        if record.read_bytes() != before:
            return fail("wrong skill writer modified record before rejecting")

        corrupt = Path(tmp) / "corrupt.jsonl"
        corrupt.write_bytes(b'{"schema_version":1}\n{"broken":\n')
        blocked = run(
            CANONICAL_WRITER,
            *append_args(corrupt, "blocked.md"),
            "--no-skill",
        )
        if blocked.returncode == 0:
            return fail("append continued after broken JSON framing", blocked)

    print(f"PASS document record runtime: {TARGET_SKILL}@{expected_version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
