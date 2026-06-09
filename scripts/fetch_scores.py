#!/usr/bin/env python3
"""
Fetches 2026 FIFA World Cup match results from football-data.org
and writes data/scores.json for the live scoring site.
"""

import json
import os
import sys
from datetime import datetime, timezone
import urllib.request
import urllib.error

API_KEY   = os.environ.get("FOOTBALL_DATA_API_KEY", "")
BASE_URL  = "https://api.football-data.org/v4"
COMP_CODE = "WC"

# Points awarded per round for a WIN
WIN_POINTS = {
    "GROUP_STAGE":    3,
    "LAST_32":        4,   # Round of 32  (new in 2026)
    "LAST_16":        5,   # Round of 16
    "QUARTER_FINALS": 6,
    "SEMI_FINALS":    7,
    "FINAL":          8,
}
# Tie points (group stage only; knockout draws go to extra time/pens)
TIE_POINTS = {"GROUP_STAGE": 1}

# 3rd-place game — omit from scoring
OMIT_STAGES = {"THIRD_PLACE"}


def api_get(path):
    url = f"{BASE_URL}{path}"
    req = urllib.request.Request(url, headers={"X-Auth-Token": API_KEY})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code} fetching {url}", file=sys.stderr)
        raise


def get_winner_team(match):
    """Return the winning team name, 'DRAW', or None (not finished)."""
    status = match.get("status")
    if status != "FINISHED":
        return None

    stage   = match.get("stage", "")
    score   = match.get("score", {})
    winner  = score.get("winner")          # HOME_TEAM | AWAY_TEAM | DRAW
    home    = match["homeTeam"]["name"]
    away    = match["awayTeam"]["name"]

    if winner == "HOME_TEAM":
        return home
    elif winner == "AWAY_TEAM":
        return away
    elif winner == "DRAW":
        return "DRAW"
    return None


def build_team_points(matches):
    """
    Returns dict: { "Brazil": {"wins": [...], "ties": [...], "total": 12}, ... }
    Each win/tie entry: {"stage": "GROUP_STAGE", "opponent": "...", "pts": 3}
    """
    team_data = {}

    def ensure(name):
        if name not in team_data:
            team_data[name] = {"wins": [], "ties": [], "total": 0}

    for m in matches:
        stage  = m.get("stage", "")
        status = m.get("status")
        if stage in OMIT_STAGES or status != "FINISHED":
            continue

        home   = m["homeTeam"]["name"]
        away   = m["awayTeam"]["name"]
        ensure(home); ensure(away)

        result = get_winner_team(m)
        if result is None:
            continue

        if result == "DRAW":
            pts = TIE_POINTS.get(stage, 0)
            if pts:
                for team, opp in [(home, away), (away, home)]:
                    team_data[team]["ties"].append({"stage": stage, "opponent": opp, "pts": pts})
                    team_data[team]["total"] += pts
        else:
            winner = result
            loser  = away if result == home else home
            pts    = WIN_POINTS.get(stage, 0)
            team_data[winner]["wins"].append({"stage": stage, "opponent": loser, "pts": pts})
            team_data[winner]["total"] += pts

    return team_data


def build_player_standings(players, team_points):
    standings = []
    for p in players:
        total = 0
        team_details = []
        for team_name in p["teams"]:
            tp = team_points.get(team_name, {"wins": [], "ties": [], "total": 0})
            total += tp["total"]
            team_details.append({"team": team_name, **tp})
        standings.append({"name": p["name"], "teams": team_details, "total": total})

    # Sort descending by total; stable so ties keep original order
    standings.sort(key=lambda x: x["total"], reverse=True)
    for i, s in enumerate(standings):
        s["draft_pick"] = i + 1  # 1st place = pick 1
    return standings


def main():
    script_dir  = os.path.dirname(os.path.abspath(__file__))
    repo_root   = os.path.dirname(script_dir)
    config_path = os.path.join(repo_root, "config", "players.json")
    out_path    = os.path.join(repo_root, "data", "scores.json")

    with open(config_path) as f:
        config = json.load(f)

    print("Fetching match data from football-data.org...")
    data    = api_get(f"/v4/competitions/{COMP_CODE}/matches")
    matches = data.get("matches", [])
    print(f"  {len(matches)} matches returned")

    team_points = build_team_points(matches)
    standings   = build_player_standings(config["players"], team_points)

    output = {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "standings": standings,
        "team_points": team_points,
        "locked_picks": config["locked_picks"],
    }

    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)

    print(f"Wrote {out_path}")
    for s in standings:
        print(f"  Pick {s['draft_pick']:2d}: {s['name']:10s} — {s['total']} pts")


if __name__ == "__main__":
    main()
