#!/usr/bin/env python3
"""
Fetches 2026 FIFA World Cup results from ESPN's public API (no auth needed).
Writes data/scores.json for the live scoring site.
"""

import json
import os
import sys
import time
from datetime import datetime, timezone
import urllib.request
import urllib.error

# ESPN public endpoint — no API key required
ESPN_URL = (
    "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard"
    "?dates=20260611-20260719&limit=200"
)

# Points per WIN by round slug
WIN_POINTS = {
    "group-stage":  3,
    "round-of-32":  4,
    "round-of-16":  5,
    "quarterfinals": 6,
    "semifinals":   7,
    "final":        8,
}
# Points per DRAW (group stage only; knockout rounds go to pens)
TIE_POINTS = {"group-stage": 1}

# Omit from scoring
OMIT_SLUGS = {"3rd-place-match"}


def fetch_events(retries=3):
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(
                ESPN_URL,
                headers={"User-Agent": "gridiron-wc-2026/1.0"}
            )
            with urllib.request.urlopen(req, timeout=20) as resp:
                return json.loads(resp.read().decode())["events"]
        except Exception as e:
            print(f"Attempt {attempt} failed: {e}", file=sys.stderr)
            if attempt < retries:
                time.sleep(5)
    print("All retries exhausted.", file=sys.stderr)
    sys.exit(1)


def parse_match(event):
    """
    Returns a dict with match info, or None if not yet finished.
    """
    slug   = event.get("season", {}).get("slug", "")
    if slug in OMIT_SLUGS:
        return None

    comp   = event["competitions"][0]
    status = comp["status"]["type"]

    if not status.get("completed", False):
        return None  # scheduled or in progress

    competitors = comp["competitors"]
    home = next(c for c in competitors if c["homeAway"] == "home")
    away = next(c for c in competitors if c["homeAway"] == "away")

    home_name  = home["team"]["displayName"]
    away_name  = away["team"]["displayName"]
    home_score = int(home.get("score", 0))
    away_score = int(away.get("score", 0))

    # winner field is reliable after full time / penalties
    home_won = home.get("winner", False)
    away_won = away.get("winner", False)

    if home_won:
        winner, loser = home_name, away_name
        draw = False
    elif away_won:
        winner, loser = away_name, home_name
        draw = False
    else:
        # Genuinely equal — treat as draw (only meaningful in group stage)
        winner, loser = None, None
        draw = True

    return {
        "slug":       slug,
        "home":       home_name,
        "away":       away_name,
        "home_score": home_score,
        "away_score": away_score,
        "winner":     winner,
        "loser":      loser,
        "draw":       draw,
    }


def build_team_points(events):
    team_data = {}

    def ensure(name):
        if name not in team_data:
            team_data[name] = {"wins": [], "ties": [], "total": 0}

    for event in events:
        m = parse_match(event)
        if m is None:
            continue

        ensure(m["home"]); ensure(m["away"])

        if m["draw"]:
            pts = TIE_POINTS.get(m["slug"], 0)
            if pts:
                for team, opp in [(m["home"], m["away"]), (m["away"], m["home"])]:
                    team_data[team]["ties"].append({"stage": m["slug"], "opponent": opp, "pts": pts})
                    team_data[team]["total"] += pts
        else:
            win_pts = WIN_POINTS.get(m["slug"], 0)
            team_data[m["winner"]]["wins"].append({
                "stage": m["slug"], "opponent": m["loser"], "pts": win_pts
            })
            team_data[m["winner"]]["total"] += win_pts

    return team_data


def build_standings(players, team_points):
    standings = []
    for p in players:
        total        = 0
        team_details = []
        for team_name in p["teams"]:
            tp = team_points.get(team_name, {"wins": [], "ties": [], "total": 0})
            total += tp["total"]
            team_details.append({"team": team_name, **tp})
        standings.append({"name": p["name"], "teams": team_details, "total": total})

    standings.sort(key=lambda x: x["total"], reverse=True)
    for i, s in enumerate(standings):
        s["draft_pick"] = i + 1
    return standings


def main():
    script_dir  = os.path.dirname(os.path.abspath(__file__))
    repo_root   = os.path.dirname(script_dir)
    config_path = os.path.join(repo_root, "config", "players.json")
    out_path    = os.path.join(repo_root, "data", "scores.json")

    with open(config_path) as f:
        config = json.load(f)

    print("Fetching 2026 World Cup data from ESPN...")
    events = fetch_events()
    print(f"  {len(events)} total matches found")

    finished = [e for e in events if e["competitions"][0]["status"]["type"].get("completed")]
    print(f"  {len(finished)} completed")

    team_points = build_team_points(events)
    standings   = build_standings(config["players"], team_points)

    output = {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "standings":    standings,
        "team_points":  team_points,
        "locked_picks": config["locked_picks"],
    }

    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nWrote {out_path}")
    for s in standings:
        print(f"  Pick {s['draft_pick']:2d}: {s['name']:10s} — {s['total']} pts")


if __name__ == "__main__":
    main()
