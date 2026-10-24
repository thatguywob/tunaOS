#!/usr/bin/env python3
"""The adoption snapshot derives its numbers and never invents them (#3305).

scripts/adoption-snapshot.py is the source for the monthly snapshot in
ADOPTION-METRICS.md and for the Q4 "Mature" adoption floor in
Q4-MATURE-DEFINITION.md. These tests hold the three properties that make it
evidence rather than a transcription:

1. Project self-use (the maintainer, TunaOS's own CI/hive) never counts toward
   the external KPI -- #1348 measured that counting it met the old ">=2
   entries" target with zero external adopters.
2. The "Mature" floor needs an external PRODUCTION row with a link; an
   evaluation row, a self-entry, or an unlinked claim does not satisfy it.
3. A failed `gh` call raises instead of reporting zero downloads.

Falsification: drop the `not e.self_reference` filter in AdoptersCount and
test_self_entries_are_excluded fails; make gh_api
return [] on a non-zero exit and test_a_failed_gh_call_raises fails.
"""

import importlib.util
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "adoption-snapshot.py"

_spec = importlib.util.spec_from_file_location("adoption_snapshot", SCRIPT)
snap = importlib.util.module_from_spec(_spec)
sys.modules["adoption_snapshot"] = snap
_spec.loader.exec_module(snap)

HEADER = "| Organization | Use Case | Variant(s) | Since |\n|---|---|---|---|\n"


def adopters_md(production: str = "", evaluation: str = "") -> str:
    return (
        "# TunaOS Adopters\n\n"
        "## Production Users\n\n"
        + (HEADER + production if production else "_(None listed yet)_\n")
        + "\n## Development & Evaluation\n\n"
        + HEADER
        + evaluation
        + "\n## Upstream & Ecosystem Dependencies\n\n"
        "| Project | What TunaOS uses it for | Link |\n|---|---|---|\n"
        "| [Debian](https://www.debian.org) | Base OS | [debian.org](https://www.debian.org) |\n"
    )


SELF_ROWS = (
    "| [@hanthor](https://github.com/hanthor) (Project Maintainer) | daily | Yellowfin | 2026-04 |\n"
    "| [TunaOS Hive Agents](https://hive.tunaos.org) | CI | Albacore | 2026-05 |\n"
)


class ParseAdopters(unittest.TestCase):
    def test_live_adopters_file_counts_no_self_use_as_external(self):
        # The live file must parse (a renamed heading raises), its maintainer
        # and hive rows must stay classified as self-use, and the derived
        # production count must agree with the file's own placeholder: the
        # "None listed yet" line and a counted production adopter cannot
        # coexist. This holds before and after the first real adopter lands.
        text = (ROOT / "ADOPTERS.md").read_text()
        counts = snap.parse_adopters(text)
        for e in counts.production + counts.evaluation:
            if e.url and ("github.com/hanthor" in e.url or "hive.tunaos.org" in e.url):
                self.assertTrue(e.self_reference, e)
        placeholder = "(None listed yet" in text
        self.assertEqual(placeholder, counts.external_production == [])

    def test_self_entries_are_excluded(self):
        counts = snap.parse_adopters(adopters_md(evaluation=SELF_ROWS))
        self.assertEqual(len(counts.evaluation), 2)
        self.assertEqual(counts.external_evaluation, [])
        self.assertFalse(snap.mature_floor_met(counts))

    def test_dependency_table_is_not_counted(self):
        counts = snap.parse_adopters(adopters_md(evaluation=SELF_ROWS))
        names = [e.name for e in counts.production + counts.evaluation]
        self.assertNotIn("Debian", names)

    def test_external_production_with_link_meets_the_floor(self):
        row = "| [Example Lab](https://example.org/case-study) | fleet | Yellowfin | 2026-10 |\n"
        counts = snap.parse_adopters(adopters_md(production=row, evaluation=SELF_ROWS))
        self.assertEqual(len(counts.external_production), 1)
        self.assertTrue(snap.mature_floor_met(counts))

    def test_unlinked_production_claim_does_not_meet_the_floor(self):
        row = "| Example Lab | fleet | Yellowfin | 2026-10 |\n"
        counts = snap.parse_adopters(adopters_md(production=row))
        self.assertEqual(len(counts.external_production), 1)
        self.assertFalse(snap.mature_floor_met(counts))

    def test_self_entry_in_production_does_not_meet_the_floor(self):
        row = "| [TunaOS](https://github.com/tuna-os) | dogfood | all | 2026-04 |\n"
        counts = snap.parse_adopters(adopters_md(production=row))
        self.assertFalse(snap.mature_floor_met(counts))

    def test_external_evaluation_does_not_meet_the_floor(self):
        row = "| [Uni Lab](https://lab.example.edu) | trial | Albacore | 2026-10 |\n"
        counts = snap.parse_adopters(adopters_md(evaluation=row))
        self.assertEqual(len(counts.external_evaluation), 1)
        self.assertFalse(snap.mature_floor_met(counts))

    def test_a_renamed_section_raises_instead_of_reading_as_zero(self):
        text = adopters_md().replace("## Production Users", "## Production")
        with self.assertRaises(ValueError):
            snap.parse_adopters(text)

    def test_lookalike_hosts_are_external(self):
        self.assertFalse(snap.is_self_reference("https://nottunaos.org"))
        self.assertFalse(snap.is_self_reference("https://github.com/hanthorfan"))
        self.assertTrue(snap.is_self_reference("https://docs.tunaos.org/x"))
        self.assertTrue(snap.is_self_reference("https://github.com/tuna-os/tunaos"))


class ReleaseDownloads(unittest.TestCase):
    RELEASES = [
        {"tag_name": "gnome-20261023", "published_at": "2026-10-23T16:05:40Z",
         "assets": [{"download_count": 2}, {"download_count": 3}]},
        {"tag_name": "gnome-20260930", "published_at": "2026-09-30T16:05:40Z",
         "assets": [{"download_count": 10}]},
        {"tag_name": "gnome-nvidia-20261001", "published_at": "2026-10-01T00:00:00Z",
         "assets": [{"download_count": 1}]},
        {"tag_name": "kde-20261023", "published_at": "2026-10-23T16:13:10Z",
         "draft": True, "assets": [{"download_count": 99}]},
    ]

    def test_window_counts_only_releases_published_in_month(self):
        rd = snap.release_downloads(self.RELEASES, "2026-10")
        self.assertEqual(rd["published_in_month_by_flavor"], {"gnome": 5, "gnome-nvidia": 1})
        self.assertEqual(rd["cumulative_by_flavor"], {"gnome": 15, "gnome-nvidia": 1})
        self.assertEqual(rd["releases_published_in_month_by_flavor"]["gnome"], 1)

    def test_drafts_are_ignored(self):
        rd = snap.release_downloads(self.RELEASES, "2026-10")
        self.assertNotIn("kde", rd["cumulative_by_flavor"])


class GhFailure(unittest.TestCase):
    def test_a_failed_gh_call_raises(self):
        failed = subprocess.CompletedProcess(["gh"], 1, stdout="", stderr="HTTP 502")
        with unittest.mock.patch.object(snap.subprocess, "run", return_value=failed):
            with self.assertRaises(RuntimeError):
                snap.gh_api("repos/tuna-os/tunaos")

    def test_snapshot_reports_live_figures(self):
        def fake(path, paginate=False):
            if paginate:
                return ReleaseDownloads.RELEASES
            return {"stargazers_count": 61, "forks_count": 7}

        counts = snap.parse_adopters(adopters_md(evaluation=SELF_ROWS))
        with unittest.mock.patch.object(snap, "gh_api", side_effect=fake):
            out = snap.build_snapshot(counts, "tuna-os/tunaos", "2026-10", offline=False)
        self.assertEqual(out["github"]["stars"], 61)
        self.assertEqual(out["adopters"]["self_use_excluded"], 2)
        md = snap.render_markdown(out)
        self.assertIn("| GitHub stars / forks | 61 / 7 |", md)
        self.assertIn("**not met**", md)


class Cli(unittest.TestCase):
    def test_check_mature_exit_code_follows_the_floor(self):
        with tempfile.TemporaryDirectory() as d:
            empty = Path(d) / "empty.md"
            empty.write_text(adopters_md(evaluation=SELF_ROWS))
            self.assertEqual(snap.main(["--adopters", str(empty), "--check-mature"]), 1)
            met = Path(d) / "met.md"
            met.write_text(adopters_md(
                production="| [Example Lab](https://example.org) | fleet | Yellowfin | 2026-10 |\n"
            ))
            self.assertEqual(snap.main(["--adopters", str(met), "--check-mature"]), 0)


if __name__ == "__main__":
    unittest.main()
