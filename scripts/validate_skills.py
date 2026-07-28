#!/usr/bin/env python3
"""Minimal static validator for this repository's Agent Skills."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = ROOT / "skills"
NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def parse_frontmatter(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValueError("missing opening YAML frontmatter delimiter")
    try:
        _, raw, _ = text.split("---", 2)
    except ValueError as exc:
        raise ValueError("missing closing YAML frontmatter delimiter") from exc

    result: dict[str, str] = {}
    for line in raw.splitlines():
        if not line or line.startswith(" ") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        result[key.strip()] = value.strip().strip('"')
    return result


def validate_skill(skill_dir: Path) -> list[str]:
    errors: list[str] = []
    skill_file = skill_dir / "SKILL.md"
    if not skill_file.is_file():
        return ["missing SKILL.md"]

    try:
        fm = parse_frontmatter(skill_file)
    except ValueError as exc:
        return [str(exc)]

    name = fm.get("name", "")
    description = fm.get("description", "")

    if name != skill_dir.name:
        errors.append(f"name '{name}' does not match directory '{skill_dir.name}'")
    if not NAME_RE.fullmatch(name):
        errors.append("name must contain lowercase letters, numbers, and single hyphens only")
    if not 1 <= len(name) <= 64:
        errors.append("name length must be 1-64 characters")
    if not 1 <= len(description) <= 1024:
        errors.append("description length must be 1-1024 characters")

    line_count = len(skill_file.read_text(encoding="utf-8").splitlines())
    if line_count > 500:
        errors.append(f"SKILL.md has {line_count} lines; recommended maximum is 500")

    return errors


def main() -> int:
    failed = False
    for skill_dir in sorted(path for path in SKILLS_DIR.iterdir() if path.is_dir()):
        errors = validate_skill(skill_dir)
        if errors:
            failed = True
            print(f"FAIL {skill_dir.name}")
            for error in errors:
                print(f"  - {error}")
        else:
            print(f"PASS {skill_dir.name}")

    if failed:
        return 1
    print("All skills passed static validation.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
