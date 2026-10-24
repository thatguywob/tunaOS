#!/usr/bin/env python3
"""Derive the adoption baseline for the monthly snapshot (tunaOS#3305).

ADOPTION-METRICS.md defines the monthly snapshot (first due 2026-11-01) and
Q4-MATURE-DEFINITION.md gates the Q4 "Mature" claim on ">=1 production adopter
listed in ADOPTERS.md with a verifiable reference". Until this script, every
number in that chain was transcribed by hand, which AGENTS.md rule 3 forbids:
the 08-14 ADOPTERS.md baseline and the ROADMAP's "56 stars, 3 forks" were both
stale weeks before the first snapshot was due (the API read 61 / 7 on
2026-10-24).

What this script derives, and from where:

* External production and evaluation entries -- parsed from the tables in
  ADOPTERS.md. Project self-use (the maintainer, TunaOS's own CI/hive) is
  counted separately and never toward the KPI, as ADOPTION-METRICS.md requires
  (#1348: the self-entries met the old ">=2 entries" target on the day it was
  written).
* GitHub stars / forks -- `gh api repos/<repo>`.
* GitHub Release asset downloads by flavor -- `gh api repos/<repo>/releases`.
  `download_count` is cumulative per asset, so the window figure is "downloads
  of assets on releases PUBLISHED in the window, as of the snapshot date", not
  "downloads that happened in the window". The output says so.

What it does NOT derive, and says so instead of inventing a number: R2 ISO
downloads (needs Cloudflare credentials, owner: ci-maintainer), docs analytics,
install telemetry, and adoption-call conversion.

A failed `gh` call raises. It never degrades to zero: a snapshot that quietly
reports "0 downloads" because the API flaked is worse than no snapshot (the
same failure mode gen-matrix-status.py hit on 2026-09-24).

Usage:
    scripts/adoption-snapshot.py [--offline] [--month YYYY-MM] [--json]
    scripts/adoption-snapshot.py --check-mature

    --offline       ADOPTERS.md counts only; no GitHub API calls
    --month         window for release downloads (default: previous month)
    --json          machine-readable output instead of Markdown
    --check-mature  exit 1 unless ADOPTERS.md lists >=1 external production
                    adopter with a link (the Q4 "Mature" adoption floor)
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parents[1]
ADOPTERS = REPO_ROOT / "ADOPTERS.md"
DEFAULT_REPO = "tuna-os/tunaos"

PRODUCTION_HEADING = "Production Users"
EVALUATION_HEADING = "Development & Evaluation"

# Project self-use. ADOPTERS.md keeps these rows as honest dogfooding records
# and marks them "**not** external adoption"; the KPI must not count them.
# Matched on the row's link, not its prose, so rewording a row cannot move it
# between columns.
SELF_GITHUB_OWNERS = frozenset({"hanthor", "tuna-os"})
SELF_HOST_SUFFIXES = ("tunaos.org",)

_LINK = re.compile(r"\[[^\]]*\]\((https?://[^)\s]+)\)")
_RELEASE_TAG = re.compile(r"^(?P<flavor>[a-z0-9]+(?:-[a-z0-9]+)*)-(?P<date>\d{8})$")


@dataclass
class Entry:
    name: str
    url: str | None
    self_reference: bool


@dataclass
class AdoptersCount:
    production: list[Entry] = field(default_factory=list)
    evaluation: list[Entry] = field(default_factory=list)

    @staticmethod
    def _external(entries: list[Entry]) -> list[Entry]:
        return [e for e in entries if not e.self_reference]

    @property
    def external_production(self) -> list[Entry]:
        return self._external(self.production)

    @property
    def external_evaluation(self) -> list[Entry]:
        return self._external(self.evaluation)

    @property
    def verifiable_external_production(self) -> list[Entry]:
        # Q4-MATURE-DEFINITION.md: "with a verifiable reference". A row with no
        # link is a claim nobody can check.
        return [e for e in self.external_production if e.url]


def is_self_reference(url: str | None) -> bool:
    if not url:
        return False
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if any(host == s or host.endswith("." + s) for s in SELF_HOST_SUFFIXES):
        return True
    if host == "github.com":
        owner = parsed.path.strip("/").split("/", 1)[0].lower()
        return owner in SELF_GITHUB_OWNERS
    return False


def _section_rows(text: str, heading: str) -> list[str]:
    """Data rows of every Markdown table under `## <heading>`."""
    rows: list[str] = []
    in_section = False
    for line in text.splitlines():
        if line.startswith("## "):
            in_section = line[3:].strip() == heading
            continue
        if not in_section or not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if all(re.fullmatch(r":?-{3,}:?", c) for c in cells if c):
            continue  # separator row
        rows.append(line)
    # The first row of each table is its header; a header has no link and its
    # first cell is a column title. Drop rows that look like headers.
    return [r for r in rows if not _is_header(r)]


def _is_header(row: str) -> bool:
    first = row.strip().strip("|").split("|", 1)[0].strip()
    return first.lower() in {"organization", "project", "name", "adopter"}


def _entry(row: str) -> Entry:
    first = row.strip().strip("|").split("|", 1)[0].strip()
    m = _LINK.search(first)
    url = m.group(1) if m else None
    name = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", first).strip()
    return Entry(name=name, url=url, self_reference=is_self_reference(url))


def parse_adopters(text: str) -> AdoptersCount:
    for heading in (PRODUCTION_HEADING, EVALUATION_HEADING):
        if not re.search(rf"^## {re.escape(heading)}\s*$", text, re.M):
            # A renamed heading would otherwise read as "0 adopters".
            raise ValueError(f"ADOPTERS.md has no '## {heading}' section")
    return AdoptersCount(
        production=[_entry(r) for r in _section_rows(text, PRODUCTION_HEADING)],
        evaluation=[_entry(r) for r in _section_rows(text, EVALUATION_HEADING)],
    )


def gh_api(path: str, paginate: bool = False):
    cmd = ["gh", "api"]
    if paginate:
        cmd += ["--paginate", "--slurp"]
    cmd.append(path)
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"{' '.join(cmd)} failed ({proc.returncode}): {proc.stderr.strip()}; "
            "refusing to report the figures it covers as zero"
        )
    data = json.loads(proc.stdout)
    if paginate:
        # --slurp wraps each page in an outer list.
        return [item for page in data for item in page]
    return data


def previous_month(today: dt.date) -> str:
    first = today.replace(day=1)
    return (first - dt.timedelta(days=1)).strftime("%Y-%m")


def release_downloads(releases: list[dict], month: str) -> dict:
    total: dict[str, int] = defaultdict(int)
    window: dict[str, int] = defaultdict(int)
    window_releases: dict[str, int] = defaultdict(int)
    for rel in releases:
        if rel.get("draft"):
            continue
        m = _RELEASE_TAG.match(rel.get("tag_name", ""))
        flavor = m.group("flavor") if m else "other"
        count = sum(a.get("download_count", 0) for a in rel.get("assets", []))
        total[flavor] += count
        published = rel.get("published_at") or ""
        if published.startswith(month):
            window[flavor] += count
            window_releases[flavor] += 1
    return {
        "month": month,
        "cumulative_by_flavor": dict(sorted(total.items())),
        "published_in_month_by_flavor": dict(sorted(window.items())),
        "releases_published_in_month_by_flavor": dict(sorted(window_releases.items())),
    }


def build_snapshot(adopters: AdoptersCount, repo: str, month: str, offline: bool) -> dict:
    snap: dict = {
        "generated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "repo": repo,
        "adopters": {
            "external_production": len(adopters.external_production),
            "external_production_verifiable": len(adopters.verifiable_external_production),
            "external_evaluation": len(adopters.external_evaluation),
            "self_use_excluded": sum(
                e.self_reference for e in adopters.production + adopters.evaluation
            ),
            "entries": {
                "production": [asdict(e) for e in adopters.production],
                "evaluation": [asdict(e) for e in adopters.evaluation],
            },
        },
        "not_measured": [
            "R2 ISO downloads (Cloudflare access logs; owner: ci-maintainer)",
            "docs site analytics",
            "install telemetry (Q4 design decision)",
            "adoption-call conversion (docs/ADOPTION-CALL.md Discussion)",
        ],
    }
    if offline:
        snap["github"] = None
        return snap
    meta = gh_api(f"repos/{repo}")
    releases = gh_api(f"repos/{repo}/releases?per_page=100", paginate=True)
    snap["github"] = {
        "stars": meta["stargazers_count"],
        "forks": meta["forks_count"],
        "release_downloads": release_downloads(releases, month),
    }
    return snap


def mature_floor_met(adopters: AdoptersCount) -> bool:
    return len(adopters.verifiable_external_production) >= 1


def render_markdown(snap: dict) -> str:
    a = snap["adopters"]
    out = [
        f"## Adoption snapshot — {snap['generated'][:10]}",
        "",
        f"Derived by `scripts/adoption-snapshot.py` at {snap['generated']} from "
        + ("ADOPTERS.md and the GitHub API" if snap.get("github") else "ADOPTERS.md")
        + ". Do not edit the numbers by hand; re-run it.",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| External production adopters (ADOPTERS.md) | {a['external_production']} |",
        f"| … with a verifiable link | {a['external_production_verifiable']} |",
        f"| External evaluation entries (ADOPTERS.md) | {a['external_evaluation']} |",
        f"| Project self-use rows (excluded from KPI) | {a['self_use_excluded']} |",
    ]
    gh = snap.get("github")
    if gh:
        rd = gh["release_downloads"]
        out += [
            f"| GitHub stars / forks | {gh['stars']} / {gh['forks']} |",
            "",
            f"### GitHub Release asset downloads ({rd['month']})",
            "",
            "`download_count` is cumulative per asset: the month column counts downloads,",
            "as of the snapshot date, of assets on releases published in that month.",
            "",
            "| Flavor | Releases in month | Downloads (month's releases) | Downloads (all time) |",
            "|---|---|---|---|",
        ]
        for flavor, cumulative in rd["cumulative_by_flavor"].items():
            out.append(
                f"| {flavor} | {rd['releases_published_in_month_by_flavor'].get(flavor, 0)} "
                f"| {rd['published_in_month_by_flavor'].get(flavor, 0)} | {cumulative} |"
            )
    else:
        out += ["| GitHub stars / forks | not queried (--offline) |"]
    floor = "met" if a["external_production_verifiable"] >= 1 else "**not met**"
    out += [
        "",
        f"Q4 \"Mature\" adoption floor (≥1 external production adopter with a verifiable "
        f"reference, Q4-MATURE-DEFINITION.md): {floor}.",
        "",
        "Not measured by this script: " + "; ".join(snap["not_measured"]) + ".",
        "",
    ]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    p.add_argument("--adopters", type=Path, default=ADOPTERS)
    p.add_argument("--repo", default=DEFAULT_REPO)
    p.add_argument("--month", default=None, help="YYYY-MM (default: previous month)")
    p.add_argument("--offline", action="store_true")
    p.add_argument("--json", action="store_true")
    p.add_argument("--check-mature", action="store_true")
    args = p.parse_args(argv)

    adopters = parse_adopters(args.adopters.read_text(encoding="utf-8"))

    if args.check_mature:
        n = len(adopters.verifiable_external_production)
        if n >= 1:
            print(f"Q4 adoption floor met: {n} external production adopter(s) with a link.")
            return 0
        print(
            "Q4 adoption floor NOT met: ADOPTERS.md lists 0 external production adopters "
            "with a verifiable reference. The \"Mature\" claim is blocked "
            "(Q4-MATURE-DEFINITION.md).",
            file=sys.stderr,
        )
        return 1

    month = args.month or previous_month(dt.date.today())
    if not re.fullmatch(r"\d{4}-\d{2}", month):
        p.error("--month must be YYYY-MM")
    snap = build_snapshot(adopters, args.repo, month, args.offline)
    if args.json:
        print(json.dumps(snap, indent=2))
    else:
        print(render_markdown(snap))
    return 0


if __name__ == "__main__":
    sys.exit(main())
