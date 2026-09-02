#!/usr/bin/env python3
"""Runtime regression test for bundled append-only document recorder."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / "skills" / "game-config"
WRITER = SKILL_DIR / "scripts" / "document_record.py"
SKILL_FILE = SKILL_DIR / "SKILL.md"
VERSION_RE = re.compile(r'(?m)^\s{2}version:\s*["\']?(\d+\.\d+\.\d+)["\']?\s*$')


def run(home: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)
    return subprocess.run(
        [sys.executable, str(WRITER), *args],
        cwd=ROOT,
        env=env,
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
    match = VERSION_RE.search(SKILL_FILE.read_text(encoding="utf-8"))
    if not match:
        return fail("cannot parse game-config version")
    expected_version = match.group(1)

    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        record = home / ".sth32_skills" / "records" / "document_changes.jsonl"

        result = run(
            home,
            "append",
            "--action", "update",
            "--document", "docs/requirements/demo/04-配置规划.md",
            "--trigger", "self_check",
            "--reason", "runtime regression test",
            "--change", "verify bundled append-only writer",
            "--validation-status", "passed",
            "--validation", "test evidence",
            "--outcome", "success",
        )
        if result.returncode != 0:
            return fail("valid append failed", result)
        if result.stdout.strip() != "recorded":
            return fail("writer must return only a compact success signal", result)
        if not record.is_file():
            return fail("record was not created under the external user directory")

        lines = record.read_text(encoding="utf-8").splitlines()
        if len(lines) != 1:
            return fail(f"expected one record, found {len(lines)}")
        entry = json.loads(lines[0])
        if entry.get("skill") != "game-config" or entry.get("skill_version") != expected_version:
            return fail(f"wrong skill attribution: {entry!r}")
        if entry.get("documents") != ["docs/requirements/demo/04-配置规划.md"]:
            return fail("repository-relative document path was not preserved")
        if (entry.get("feedback") or {}).get("signal") != "none":
            return fail("normal progress must default to feedback.signal=none")

        absolute = run(
            home,
            "append",
            "--action", "update",
            "--document", "/tmp/private.md",
            "--trigger", "self_check",
            "--reason", "must reject absolute path",
            "--change", "should not append",
        )
        if absolute.returncode == 0:
            return fail("absolute document path unexpectedly succeeded", absolute)
        if len(record.read_text(encoding="utf-8").splitlines()) != 1:
            return fail("failed append modified the record")

        actionable = run(
            home,
            "append",
            "--action", "update",
            "--document", "docs/requirements/demo/04-配置规划.md",
            "--trigger", "user_correction",
            "--reason", "missing prevention must fail",
            "--change", "should not append",
            "--feedback-signal", "actionable",
            "--feedback-category", "skill",
            "--feedback-pattern", "runtime_test_gap",
            "--feedback-severity", "medium",
            "--root-cause", "known cause",
        )
        if actionable.returncode == 0:
            return fail("actionable feedback without prevention unexpectedly succeeded", actionable)

        query = run(home, "query")
        if query.returncode == 0:
            return fail("normal writer unexpectedly exposes a history query command", query)

    print(f"PASS bundled append-only recorder: game-config@{expected_version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
