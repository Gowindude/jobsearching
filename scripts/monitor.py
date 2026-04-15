"""
monitor.py — Internship tracker updater for aerospace/simulation/GNC roles.

Fetches README files from multiple GitHub internship tracker repos, filters
for aerospace/mechanical/simulation/GNC/CFD/FEA/propulsion roles, and appends
new entries to tracker.csv.

Usage:
    python scripts/monitor.py

Requirements:
    pip install requests
"""

import csv
import re
import sys
from datetime import date
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

TRACKER_CSV = Path(__file__).parent.parent / "tracker.csv"

# GitHub raw README URLs to scrape
SOURCES = [
    {
        "name": "jobright-ai/2026-Engineer-Internship",
        "url": "https://raw.githubusercontent.com/jobright-ai/2026-Engineer-Internship/main/README.md",
    },
    {
        "name": "SimplifyJobs/Fall2026-Internships",
        "url": "https://raw.githubusercontent.com/SimplifyJobs/Fall2026-Internships/dev/README.md",
    },
    {
        "name": "SimplifyJobs/Summer2026-Internships",
        "url": "https://raw.githubusercontent.com/SimplifyJobs/Summer2026-Internships/dev/README.md",
    },
    {
        "name": "vanshb03/Summer2026-Internships",
        "url": "https://raw.githubusercontent.com/vanshb03/Summer2026-Internships/main/README.md",
    },
]

# Keywords that indicate an aerospace/sim/GNC/propulsion relevant role.
# Checked case-insensitively against the full row text.
ROLE_KEYWORDS = [
    "gnc",
    "guidance navigation",
    "trajectory",
    "flight dynamics",
    "flight simulation",
    "flight simulator",
    "6dof",
    "6-dof",
    "orbital mechanics",
    "orbital analysis",
    "proximity operations",
    "rendezvous",
    "reentry",
    "astrodynamics",
    "hypersonic",
    "propulsion",
    "feed system",
    "combustion",
    "turbopump",
    "turbomachinery",
    "rocket engine",
    "rocket motor",
    "thruster",
    "nozzle",
    "cfd",
    "computational fluid",
    "aerodynamics",
    "openfoam",
    "ansys fluent",
    "fluent",
    "finite volume",
    "aeroelastic",
    "fea",
    "finite element",
    "structural analysis",
    "ansys mechanical",
    "nastran",
    "aerostructures",
    "thermal analysis",
    "thermal protection",
    "thermal management",
    "controls engineer",
    "control systems",
    "flight control",
    "attitude control",
    "thrust vector",
    "autonomy",
    "flight software",
    "digital twin",
    "simulation engineer",
    "hardware-in-the-loop",
    "model-based",
    "systems engineering",
    "vehicle integration",
    "mission analysis",
    "mission design",
    "aerospace engineer",
    "mechanical engineer",
]

# Company names to always capture regardless of role title.
# Catches cases where a role title is generic (e.g., "Engineering Intern") but
# the company is a high-priority target.
WATCHLIST_COMPANIES = [
    "spacex",
    "rocket lab",
    "hermeus",
    "impulse space",
    "true anomaly",
    "apex space",
    "stoke space",
    "orbital operations",
    "blue origin",
    "anduril",
    "shield ai",
    "joby aviation",
    "wisk",
    "archer aviation",
    "relativity space",
    "firefly aerospace",
    "sierra space",
    "vast space",
    "k2 space",
    "starfish space",
    "ursa major",
    "vaya space",
    "firehawk",
    "muon space",
    "cesiumastro",
]

# CSV column names (must match tracker.csv header exactly)
FIELDNAMES = [
    "Company",
    "Role Title",
    "Location",
    "Internship Season",
    "Posting Date",
    "Link",
    "Source Tracker",
    "Keywords",
    "Priority Score",
    "Notes for Coffee Chat / Outreach",
    "Status",
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def fetch_readme(url: str) -> str:
    """Fetch raw README text; return empty string on failure."""
    try:
        resp = requests.get(url, timeout=20)
        resp.raise_for_status()
        return resp.text
    except requests.RequestException as exc:
        print(f"  WARNING: Could not fetch {url}: {exc}", file=sys.stderr)
        return ""


def parse_markdown_table_rows(text: str) -> list:
    """
    Extract non-header, non-separator rows from all markdown tables in text.
    Returns a list of lists (each inner list is the cell values for one row).
    """
    rows = []
    for line in text.splitlines():
        line = line.strip()
        # Must start and end with | to be a table row
        if not (line.startswith("|") and line.endswith("|")):
            continue
        # Skip separator rows (e.g. |---|---|)
        if re.match(r"^\|[-| :]+\|$", line):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        # Skip header rows that contain typical header words
        first = cells[0].lower() if cells else ""
        if first in ("company", "name", "employer", "organization"):
            continue
        # Skip empty or near-empty rows
        if all(not c or c == "🔒" for c in cells):
            continue
        rows.append(cells)
    return rows


def is_relevant(cells: list) -> tuple:
    """
    Return (True, matched_keywords) if this row is relevant to our search.
    Checks the full row text against ROLE_KEYWORDS and WATCHLIST_COMPANIES.
    """
    full_text = " ".join(cells).lower()
    matched = []

    # Check watchlist companies first (always capture)
    for company in WATCHLIST_COMPANIES:
        if company in full_text:
            matched.append(company)

    # Check role keywords
    for kw in ROLE_KEYWORDS:
        if kw in full_text:
            matched.append(kw)

    return bool(matched), list(dict.fromkeys(matched))  # deduplicate, preserve order


def load_existing_tracker() -> tuple:
    """
    Load tracker.csv. Returns (existing_keys, rows) where existing_keys is a
    set of (company_lower, role_lower) tuples for deduplication.
    """
    existing_keys = set()
    rows = []
    if not TRACKER_CSV.exists():
        return existing_keys, rows
    with open(TRACKER_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
            key = (row.get("Company", "").strip().lower(), row.get("Role Title", "").strip().lower())
            existing_keys.add(key)
    return existing_keys, rows


def extract_link(cell_text: str) -> str:
    """Extract URL from a markdown link like [text](url) or return cell as-is."""
    match = re.search(r"\(https?://[^\)]+\)", cell_text)
    if match:
        return match.group(0).strip("()")
    return ""


def clean_cell(cell_text: str) -> str:
    """Strip markdown formatting from a cell."""
    # Remove markdown links, keep text
    cell_text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", cell_text)
    # Remove bold/italic markers
    cell_text = re.sub(r"\*+", "", cell_text)
    # Remove HTML tags
    cell_text = re.sub(r"<[^>]+>", "", cell_text)
    return cell_text.strip()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    today = date.today().isoformat()
    existing_keys, current_rows = load_existing_tracker()

    new_rows = []
    source_stats = {}

    for source in SOURCES:
        print(f"Fetching {source['name']} ...", flush=True)
        readme = fetch_readme(source["url"])
        if not readme:
            source_stats[source["name"]] = 0
            continue

        table_rows = parse_markdown_table_rows(readme)
        found_count = 0

        for cells in table_rows:
            if len(cells) < 2:
                continue

            relevant, matched_kws = is_relevant(cells)
            if not relevant:
                continue

            # Best-effort column mapping: most trackers are (Company, Role, Location, [Date], [Link])
            company = clean_cell(cells[0]) if len(cells) > 0 else ""
            role = clean_cell(cells[1]) if len(cells) > 1 else ""
            location = clean_cell(cells[2]) if len(cells) > 2 else ""

            # Try to find a link anywhere in the row
            link = ""
            for cell in cells:
                link = extract_link(cell)
                if link:
                    break

            # Skip clearly bad rows
            if not company or not role:
                continue
            if len(company) > 100 or len(role) > 200:
                continue

            key = (company.lower(), role.lower())
            if key in existing_keys:
                continue

            # Determine season from source name
            season = "Fall 2026" if "fall" in source["name"].lower() else "Summer/Fall 2026"

            new_row = {
                "Company": company,
                "Role Title": role,
                "Location": location,
                "Internship Season": season,
                "Posting Date": today,
                "Link": link,
                "Source Tracker": source["name"],
                "Keywords": ", ".join(matched_kws[:5]),
                "Priority Score": "",
                "Notes for Coffee Chat / Outreach": "",
                "Status": "New",
            }
            new_rows.append(new_row)
            existing_keys.add(key)
            found_count += 1

        source_stats[source["name"]] = found_count
        print(f"  -> {found_count} new relevant roles found")

    # Append new rows to tracker.csv
    if new_rows:
        write_header = not TRACKER_CSV.exists()
        with open(TRACKER_CSV, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            if write_header:
                writer.writeheader()
            for row in new_rows:
                writer.writerow(row)
        print(f"\nAppended {len(new_rows)} new roles to {TRACKER_CSV.name}")
    else:
        print("\nNo new roles found since last run.")

    # Summary
    print("\n--- Summary ---")
    for source_name, count in source_stats.items():
        print(f"  {source_name}: {count} new roles")
    print(f"  Total new: {len(new_rows)}")
    print(f"  Tracker now has {len(current_rows) + len(new_rows)} total rows")


if __name__ == "__main__":
    main()
