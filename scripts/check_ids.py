"""Check that every ID referenced in the documentation is defined.

IDs and where they are defined:
  US-n, REQ-AREA-n, NFR-n, AC-n.m   docs/requirements.md
  C-n, A-n                          docs/architecture.md
  Q-n                               docs/mvp.md
  ADR-NNNN                          a file docs/adr/NNNN-*.md

Also checks that requirement IDs and acceptance criteria are defined only once,
and that the story overview (requirements.md 3.1) lists exactly the stories that are specified.

Ranges such as "REQ-USR-2…4", "REQ-ING-1..4" or "US-1…US-15" are expanded,
and "AC-7.x" requires at least one acceptance criterion for US-7.

Usage: python scripts/check_ids.py   (exit code 1 if a problem is found)
"""

from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REQUIREMENTS = ROOT / "docs" / "requirements.md"
ARCHITECTURE = ROOT / "docs" / "architecture.md"
MVP = ROOT / "docs" / "mvp.md"
ADR_DIR = ROOT / "docs" / "adr"

EXCLUDED_DIRS = {".git", ".obsidian", "node_modules"}
EXCLUDED_PATHS = {ADR_DIR / "template"}

# IDs that are deliberately referenced without being defined, per file.
ALLOWED_UNDEFINED = {
    # ai-usage.md documents the history of the requirements and cites IDs of draft v0.
    ("docs/ai-usage.md", "REQ-VIEW-6"),
}

ID_PATTERN = re.compile(
    r"\b(US-\d+|REQ-[A-Z]+-\d+|NFR-\d+|AC-\d+\.(?:\d+|x)|ADR-\d{4}|[CAQ]-\d+)\b"
)
RANGE_PATTERN = re.compile(r"\b(REQ-[A-Z]+-|US-|NFR-)(\d+)(?:\.\.|…)(?:\1)?(\d+)\b")

errors: list[str] = []


def error(path: Path, line: int, message: str) -> None:
    relative = path.relative_to(ROOT).as_posix()
    # GitHub Actions shows this format as an annotation on the file and line.
    errors.append(f"::error file={relative},line={line}::{message}")


def lines_of(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def collect_definitions() -> tuple[dict[str, list[tuple[Path, int]]], set[str], set[str]]:
    """Return all defined IDs with their locations, plus the story IDs of the overview and of the story sections."""
    definitions: dict[str, list[tuple[Path, int]]] = defaultdict(list)
    overview: set[str] = set()
    specified: set[str] = set()

    section = ""
    for number, line in enumerate(lines_of(REQUIREMENTS), start=1):
        if line.startswith("### "):
            section = line
        if m := re.match(r"\| (US-\d+) \|", line):
            (overview if "Overview" in section else specified).add(m.group(1))
        if m := re.match(r"#### (US-\d+) ", line):
            specified.add(m.group(1))
        if m := re.match(r"- \*\*(REQ-[A-Z]+-\d+|NFR-\d+)\b", line):
            definitions[m.group(1)].append((REQUIREMENTS, number))
        if m := re.match(r"\| (AC-\d+\.\d+) \|", line):
            definitions[m.group(1)].append((REQUIREMENTS, number))
    for story in overview | specified:
        definitions[story].append((REQUIREMENTS, 0))

    for number, line in enumerate(lines_of(ARCHITECTURE), start=1):
        if m := re.match(r"(?:\| |- \*\*)([CA]-\d+)\b", line):
            definitions[m.group(1)].append((ARCHITECTURE, number))

    for number, line in enumerate(lines_of(MVP), start=1):
        if m := re.match(r"- \*\*(Q-\d+)\*\*", line):
            definitions[m.group(1)].append((MVP, number))

    for adr in ADR_DIR.glob("[0-9][0-9][0-9][0-9]-*.md"):
        definitions[f"ADR-{adr.name[:4]}"].append((adr, 0))

    return definitions, overview, specified


def check_unique(definitions: dict[str, list[tuple[Path, int]]]) -> None:
    for id_, places in definitions.items():
        if id_.startswith(("REQ-", "NFR-", "AC-")) and len(places) > 1:
            for path, line in places[1:]:
                error(path, line, f"{id_} is defined more than once (first at line {places[0][1]})")


def check_overview(overview: set[str], specified: set[str]) -> None:
    for story in sorted(specified - overview):
        error(REQUIREMENTS, 1, f"{story} is specified but missing from the story overview (section 3.1)")
    for story in sorted(overview - specified):
        error(REQUIREMENTS, 1, f"{story} is listed in the story overview but not specified")


def markdown_files() -> list[Path]:
    files = []
    for path in ROOT.rglob("*.md"):
        if EXCLUDED_DIRS & set(path.relative_to(ROOT).parts):
            continue
        if any(path.is_relative_to(excluded) for excluded in EXCLUDED_PATHS):
            continue
        files.append(path)
    return sorted(files)


def check_references(defined: set[str]) -> None:
    stories_with_acs = {id_.split(".")[0].replace("AC-", "US-") for id_ in defined if id_.startswith("AC-")}

    for path in markdown_files():
        relative = path.relative_to(ROOT).as_posix()
        for number, line in enumerate(lines_of(path), start=1):
            referenced = set(ID_PATTERN.findall(line))
            for prefix, start, end in RANGE_PATTERN.findall(line):
                referenced |= {f"{prefix}{n}" for n in range(int(start), int(end) + 1)}

            for id_ in sorted(referenced):
                if (relative, id_) in ALLOWED_UNDEFINED:
                    continue
                if id_.endswith(".x"):
                    story = id_[:-2].replace("AC-", "US-")
                    if story not in stories_with_acs:
                        error(path, number, f"{id_} refers to {story}, which has no acceptance criteria")
                elif id_ not in defined:
                    error(path, number, f"{id_} is referenced but not defined")


def main() -> int:
    definitions, overview, specified = collect_definitions()
    check_unique(definitions)
    check_overview(overview, specified)
    check_references(set(definitions))

    for message in errors:
        print(message)
    print(f"{len(errors)} problem(s) found." if errors else "All referenced IDs are defined.")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
