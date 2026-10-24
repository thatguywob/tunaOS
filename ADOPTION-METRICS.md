# TunaOS Adoption Metrics Plan

**Last updated**: 2026-08-14 | **Owner**: strategist (snapshot), ci-maintainer (R2/Releases data), guide (publishing)
**Tracking**: [tunaos#1174](https://github.com/tuna-os/tunaos/issues/1174)

---

## Why

tunaOS ships 179+ downloadable ISOs across 9+ variants × 5 desktops, yet has
**zero usage telemetry**. Roadmap themes (Q3 "Expand", Q4 "Mature") are executed
without evidence of what users download, install, or keep. Enterprise
credibility (Redfin/RHEL #1123, FOSDEM 2027 CFP #1135) rests on demonstrable
adoption — today the only public signal is a star count that moved 55→56 in a
month.

This document defines *what* to measure, *where* the data comes from, *when* to
publish, and *how* the snapshot feeds roadmap decisions.

---

## Metric tiers (funnel)

| Tier | Metric | Source | Current baseline (08-10) | Target (Q4 2026, "Mature") |
|------|--------|--------|--------------------------|------------------------------|
| Discovery | GitHub stars / forks | GitHub API | 56 / 3 | ≥100 stars |
| Discovery | Docs site visits, top variant pages | Cloudflare analytics on tunaos.org | not measured | ≥1k visits/mo, variant-page ranking |
| Discovery | DistroWatch referral traffic | Cloudflare analytics referrer field, tunaos.org | not submitted yet — draft ready ([docs/DISTROWATCH-SUBMISSION.md](./docs/DISTROWATCH-SUBMISSION.md), tunaos#1333) | Submission live; referral share visible in the monthly snapshot |
| Download | ISO downloads by variant+desktop | R2 access logs (tunaos.org/download) | **not measured** | ≥1k ISO downloads/mo; variant ranking |
| Download | GitHub Release asset downloads | Releases API (resumed 08-09, #1106) | 0 (assets were empty shells) | assets present on all flavors; downloads counted |
| Install | Installs / successful boots | opt-in telemetry or boot-report gating | **not measured** | Q4 design decision (#577 GUI gate, #763) |
| Community | Merged PRs from external human contributors | GitHub API | **3 merged contributions from 3 verified humans** (docs#234, docs#239 on 08-14; one bootc-migrate contribution on 08-05) | ≥5 merged PRs from ≥3 humans, including one repeat contributor |
| Community | Discussion posts, `good first issue` pickups | GitHub API | 0 starter issues (dead label, #1308) | ≥5 starter issues picked up |
| Community | **External** public adopters (production or evaluation), [ADOPTERS.md](./ADOPTERS.md) — excludes the maintainer and TunaOS's own infrastructure | Manual — PR from the adopting org, or outreach asking permission to list | 0 external entries (#1348) | ≥2–3 external evaluator/production entries |
| Community | Adoption-call conversion | GitHub Discussion + follow-up PRs | **not measured** | Record responses, consent-confirmed named entries, anonymous reports, and ADOPTERS.md PRs |

**Instrumentation order** (cheapest first):

1. **GitHub Releases download counts** — free API counter; needs non-gnome
   flavors to publish assets too (#1254 parity gap — scheduled matrix now
   covers gnome/kde/xfce/cosmic/niri, PR pending; watch the next few
   scheduled runs to confirm kde/xfce/cosmic/niri publish before
   counting this instrumentation step done).
2. **R2/Cloudflare access-log analytics** on tunaos.org/download — R2 already
   serves the ISOs; enable access logs + a dashboard (owner: ci-maintainer).
3. **Docs analytics** — Cloudflare Web Analytics on the Docusaurus site
   (one script tag; owner: guide).
4. **Install telemetry** — deferred to Q4 design decision; do not block 1–3.

---

## Cadence & publication

- **Monthly snapshot**, published in the ROADMAP **Community** section (first:
  **2026-11-01**, covering October — aligns with Q4 "Mature" opening).
- Snapshot format: downloads by variant × desktop (top 10), stars/forks,
  external-contributor PRs, release-asset presence per flavor,
  [ADOPTERS.md](./ADOPTERS.md) EXTERNAL production/evaluation entry count
  (the two self-entries — maintainer and TunaOS CI — are excluded; counting
  them would have met the >=2 target on the day it was written, #1348),
  adoption-call responses/conversion, and a one-line "variant ranking" that
  flags under-/over-performing editions.
- Ownership: **strategist** compiles; **ci-maintainer** supplies R2/Releases
  exports; **guide** publishes on tunaos.org/blog.

### Deriving the snapshot (#3305)

The derivable part of the snapshot is generated, not transcribed (AGENTS.md
rule 3):

```bash
just adoption-snapshot --month 2026-10        # Markdown block for the ROADMAP
just adoption-snapshot --month 2026-10 --json # same data, machine-readable
just adoption-snapshot --check-mature         # Q4 adoption floor; exits 1 until met
```

`scripts/adoption-snapshot.py` reads the external production/evaluation count
from [ADOPTERS.md](./ADOPTERS.md) (self-use rows linked to `github.com/hanthor`,
`github.com/tuna-os` or `*.tunaos.org` are reported separately and never counted),
stars/forks from the GitHub API, and Release asset downloads per flavor from
the Releases API. GitHub's `download_count` is cumulative per asset, so the
monthly column counts downloads, as of the snapshot date, of assets on
releases published in that month. It is not a count of downloads that
happened during the month. A failed API call stops the script; it never
reports zero instead. The script does not measure R2 ISO downloads, docs
analytics, install telemetry, or adoption-call conversion, and the output
lists them as not measured. The owners above supply those figures.

`--check-mature` is the falsifiable form of the adoption line in
[Q4-MATURE-DEFINITION.md](./Q4-MATURE-DEFINITION.md). It passes only when
ADOPTERS.md has at least one external **production** row with a link. An
evaluation row, a self-use row, or a row without a link does not count.

## Outreach evidence

The current outreach record is kept in
[docs/ADOPTION-OUTREACH-STATUS.md](docs/ADOPTION-OUTREACH-STATUS.md). A draft,
an intended recipient, or an ecosystem relationship is not an outreach result;
the monthly snapshot must record a sent date, public URL, response, or an
explicitly unattempted status.

### Contribution evidence is not adoption evidence

The 2026-08-14 docs merges establish a real external-contribution channel and
are useful leading evidence for the Hacktoberfest funnel. They do not establish
that the authors use TunaOS. Keep the contribution count separate from
production/evaluation entries in `ADOPTERS.md`; only a consent-confirmed report
belongs in the adopter funnel.

## Decision linkage

Each snapshot must answer two questions for the roadmap:

1. Which variants/desktops justify the 40-cell nightly build fanout (#1106)?
2. Which variant pages need content investment (docs parity, #1294)?

A variant with <2% of downloads for two consecutive snapshots is a candidate
for **downgrade or retirement** in the next quarterly roadmap — unless there is
a documented strategic reason to keep it (e.g., enterprise channel #1123).

## Anti-goals

- No user-tracking cookies or invasive telemetry in the OS image.
- Download counts are a *proxy* for installs, not proof of use — do not
  over-claim adoption in external materials (FOSDEM CFP, enterprise outreach)
  beyond what snapshots show.

---

## Roadmap integration

Q4 2026 goal: **"Adoption metrics / usage telemetry"** (owner: strategist,
tunaos#1174) — first monthly snapshot published 2026-11-01 and Q4 target
metrics above met or explicitly re-baselined in the ROADMAP.

---
*Filed by strategist agent (ACMM L6 — full mode) — planning artifact for tunaos#1174.*
