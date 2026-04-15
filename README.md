# jobsearching

Fall 2026 internship tracker for aerospace, simulation, GNC, propulsion, CFD/FEA, and controls roles.

## Files

| File | Purpose |
|------|---------|
| `tracker.csv` | Main watchlist — paste into Google Sheets or Excel |
| `sources.md` | Best GitHub repos, aggregators, and company portals to monitor |
| `keywords.md` | Keyword filter lists by discipline for manual searching |
| `scripts/monitor.py` | Scrapes tracker repos and appends new matching roles to `tracker.csv` |
| `.github/workflows/update_tracker.yml` | GitHub Action that runs the monitor daily at 08:00 UTC |

## Setup

```bash
pip install -r scripts/requirements.txt
```

## Run the monitor manually

```bash
python scripts/monitor.py
```

Fetches `jobright-ai/2026-Engineer-Internship`, `SimplifyJobs/Fall2026-Internships`, `SimplifyJobs/Summer2026-Internships`, and `vanshb03/Summer2026-Internships`. Filters for aerospace/GNC/propulsion/simulation keywords, deduplicates against existing rows, and appends new roles to `tracker.csv`.

## Verify it's working

```bash
# Run twice — second run should report 0 new roles (dedup check)
python scripts/monitor.py
python scripts/monitor.py

# Check row count and status of appended rows
grep ",New," tracker.csv | wc -l
```

## GitHub Actions

The workflow at `.github/workflows/update_tracker.yml` runs automatically every day at 08:00 UTC. If new roles are found, it commits updated `tracker.csv` back to the repo.

To trigger it manually: **Actions tab → Update Tracker → Run workflow**.

Requires the repo's default `GITHUB_TOKEN` — no extra secrets needed.

## Tracker columns

```
Company | Role Title | Location | Internship Season | Posting Date | Link
Source Tracker | Keywords | Priority Score | Notes for Coffee Chat / Outreach | Status
```

Priority scores: `5` = apply day one, `4` = apply within 48h, `3` = apply within a week, `2` = broader net.
