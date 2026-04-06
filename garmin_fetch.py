#!/usr/bin/env python3
"""
Garmin Zone 2 Fetcher — runs via GitHub Actions.
Writes data.json to be served by GitHub Pages.

Requirements: pip install garminconnect
Env vars:     GARMIN_TOKEN  (see README for how to generate)
"""

import os
import sys
import json
import datetime
import time

try:
    from garminconnect import Garmin, GarminConnectAuthenticationError
except ImportError:
    print("Missing dependency: pip install garminconnect")
    sys.exit(1)

# ── Config ────────────────────────────────────────────────────────────────────

ACTIVITY_TYPES = ["cycling", "running"]
MAX_ACTIVITIES = 200          # per type; covers a full year comfortably
ZONE_2_NUMBER  = 2            # Garmin's zone numbering
OUTPUT_FILE    = "data.json"

# ── Auth ──────────────────────────────────────────────────────────────────────

def login() -> Garmin:
    token = os.environ.get("GARMIN_TOKEN")
    if not token:
        print("Error: GARMIN_TOKEN must be set. See README for instructions.")
        sys.exit(1)
    print("Logging in via cached session token...")
    client = Garmin()
    client.garth.loads(token)
    client.display_name = client.garth.profile.get("displayName", "")
    print("Login successful.")
    return client

# ── Helpers ───────────────────────────────────────────────────────────────────

def fetch_zone2_seconds(client: Garmin, activity_id: int) -> int:
    try:
        zones = client.get_activity_hr_in_timezones(activity_id)
        for z in (zones or []):
            if z.get("zoneNumber") == ZONE_2_NUMBER:
                return int(z.get("secsInZone", 0))
    except Exception as e:
        print(f"    Warning: could not fetch zones for {activity_id}: {e}")
    return 0

def fmt_hm(seconds: int) -> str:
    h = seconds // 3600
    m = (seconds % 3600) // 60
    return f"{h}h {m:02d}m"

def week_of_year(date_str: str) -> int:
    return datetime.date.fromisoformat(date_str).isocalendar()[1]

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    client = login()

    this_year = datetime.date.today().year
    last_year = this_year - 1

    years = {
        this_year: {"date_from": f"{this_year}-01-01", "date_to": f"{this_year}-12-31"},
        last_year: {"date_from": f"{last_year}-01-01", "date_to": f"{last_year}-12-31"},
    }

    # Accumulate Zone 2 data per year and per week
    results = {}
    for year, cfg in years.items():
        results[year] = {
            "total_seconds": 0,
            "by_week": {},       # week_number -> seconds
            "by_activity": [],   # list of {date, name, type, zone2_seconds}
        }

    for activity_type in ACTIVITY_TYPES:
        for year, cfg in years.items():
            print(f"\nFetching {activity_type} for {year}...")
            try:
                activities = client.get_activities_by_date(
                    startdate=cfg["date_from"],
                    enddate=cfg["date_to"],
                    activitytype=activity_type,
                )
            except Exception as e:
                print(f"  Failed: {e}")
                continue

            activities = activities[:MAX_ACTIVITIES]
            print(f"  {len(activities)} activities found.")

            for act in activities:
                activity_id = act.get("activityId")
                name        = act.get("activityName", "")
                start_local = act.get("startTimeLocal", "")
                date_str    = start_local[:10] if start_local else ""

                z2_secs = fetch_zone2_seconds(client, activity_id)
                print(f"    {date_str}  {name[:35]:<35}  Zone 2: {fmt_hm(z2_secs)}")

                week = week_of_year(date_str) if date_str else 0

                results[year]["total_seconds"] += z2_secs
                results[year]["by_week"][str(week)] = (
                    results[year]["by_week"].get(str(week), 0) + z2_secs
                )
                results[year]["by_activity"].append({
                    "date":          date_str,
                    "name":          name,
                    "type":          activity_type,
                    "zone2_seconds": z2_secs,
                    "zone2_fmt":     fmt_hm(z2_secs),
                })

                time.sleep(0.4)

    # Build output
    today = datetime.date.today()
    current_week = today.isocalendar()[1]

    output = {
        "updated_at":   today.isoformat(),
        "current_week": current_week,
        "this_year":    this_year,
        "last_year":    last_year,
        "years": {
            str(this_year): {
                "total_seconds": results[this_year]["total_seconds"],
                "total_fmt":     fmt_hm(results[this_year]["total_seconds"]),
                "by_week":       results[this_year]["by_week"],
                "by_activity":   sorted(
                    results[this_year]["by_activity"],
                    key=lambda x: x["date"], reverse=True
                ),
            },
            str(last_year): {
                "total_seconds": results[last_year]["total_seconds"],
                "total_fmt":     fmt_hm(results[last_year]["total_seconds"]),
                "by_week":       results[last_year]["by_week"],
                "by_activity":   sorted(
                    results[last_year]["by_activity"],
                    key=lambda x: x["date"], reverse=True
                ),
            },
        }
    }

    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\n✓ Wrote {OUTPUT_FILE}")
    print(f"  {this_year} Zone 2: {fmt_hm(results[this_year]['total_seconds'])}")
    print(f"  {last_year} Zone 2: {fmt_hm(results[last_year]['total_seconds'])}")

if __name__ == "__main__":
    main()
