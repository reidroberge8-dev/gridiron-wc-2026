#!/usr/bin/env python3
"""
Fetches 2026 FIFA World Cup results from ESPN's public API (no auth needed).
Writes data/scores.json for the live scoring site.
"""

import json, os, sys, time
from datetime import datetime, timezone
import urllib.request, urllib.error

ESPN_URL = (
    "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard"
    "?dates=20260611-20260719&limit=200"
)

WIN_POINTS = {
    "group-stage":   3,
    "round-of-32":   4,
    "round-of-16":   5,
    "quarterfinals": 6,
    "semifinals":    7,
    "final":         8,
}
TIE_POINTS   = {"group-stage": 1}
OMIT_SLUGS   = {"3rd-place-match"}
KNOCKOUT_SLUGS = {"round-of-32","round-of-16","quarterfinals","semifinals","final"}


def fetch_events(retries=3):
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(ESPN_URL, headers={"User-Agent": "gridiron-wc-2026/1.0"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                return json.loads(resp.read().decode())["events"]
        except Exception as e:
            print(f"Attempt {attempt} failed: {e}", file=sys.stderr)
            if attempt < retries:
                time.sleep(5)
    sys.exit(1)


def build_team_data(events):
    """
    Returns dict keyed by team name with:
      wins, ties, total, last_result, next_game, eliminated
    """
    teams = {}

    def ensure(name):
        if name not in teams:
            teams[name] = {
                "wins": [], "ties": [], "losses": [], "total": 0,
                "last_result": None, "next_game": None,
                "eliminated": False,
                "_completed_dates": [],
                "_scheduled_dates": [],
            }

    for event in events:
        slug = event.get("season", {}).get("slug", "")
        if slug in OMIT_SLUGS:
            continue

        comp        = event["competitions"][0]
        status_type = comp["status"]["type"]
        completed   = status_type.get("completed", False)
        scheduled   = status_type.get("name") == "STATUS_SCHEDULED"
        date_str    = event.get("date", "")  # ISO UTC

        competitors = comp["competitors"]
        home = next(c for c in competitors if c["homeAway"] == "home")
        away = next(c for c in competitors if c["homeAway"] == "away")
        home_name = home["team"]["displayName"]
        away_name = away["team"]["displayName"]

        ensure(home_name); ensure(away_name)

        if scheduled:
            # Record next game for each team
            for team, opp in [(home_name, away_name), (away_name, home_name)]:
                existing = teams[team]["next_game"]
                if existing is None or date_str < existing["date"]:
                    teams[team]["next_game"] = {"opponent": opp, "date": date_str, "stage": slug}

        if not completed:
            continue

        # --- parse result ---
        home_score = int(home.get("score", 0))
        away_score = int(away.get("score", 0))
        home_won   = home.get("winner", False)
        away_won   = away.get("winner", False)

        if home_won:
            winner, loser, draw = home_name, away_name, False
        elif away_won:
            winner, loser, draw = away_name, home_name, False
        else:
            winner, loser, draw = None, None, True

        # --- points ---
        if draw:
            pts = TIE_POINTS.get(slug, 0)
            if pts:
                for team, opp in [(home_name, away_name), (away_name, home_name)]:
                    teams[team]["ties"].append({"stage": slug, "opponent": opp, "pts": pts})
                    teams[team]["total"] += pts
        else:
            win_pts = WIN_POINTS.get(slug, 0)
            teams[winner]["wins"].append({"stage": slug, "opponent": loser, "pts": win_pts})
            teams[winner]["total"] += win_pts
            teams[loser]["losses"].append({"stage": slug, "opponent": winner})
            # Knockout loss = eliminated
            if slug in KNOCKOUT_SLUGS:
                teams[loser]["eliminated"] = True

        # --- last result for each team ---
        for team in [home_name, away_name]:
            if team == winner:
                result = "W"
            elif draw:
                result = "D"
            else:
                result = "L"
            score_str = f"{home_score}-{away_score}" if team == home_name else f"{away_score}-{home_score}"
            opp = away_name if team == home_name else home_name
            existing = teams[team]["last_result"]
            if existing is None or date_str > existing["date"]:
                teams[team]["last_result"] = {
                    "result": result,
                    "score": score_str,
                    "opponent": opp,
                    "stage": slug,
                    "date": date_str,
                }

    # Clean up internal keys
    for t in teams.values():
        del t["_completed_dates"]
        del t["_scheduled_dates"]
        # Add computed record string
        w = len(t["wins"]); d = len(t["ties"]); l = len(t["losses"])
        t["record"] = f"{w}W-{d}D-{l}L"

    # Detect group-stage elimination:
    # If a team has no next_game AND group stage is well underway, they didn't advance
    now = datetime.now(timezone.utc).isoformat()
    group_matches_done = sum(
        1 for e in events
        if e.get("season", {}).get("slug") == "group-stage"
        and e["competitions"][0]["status"]["type"].get("completed", False)
    )
    if group_matches_done >= 72:  # all group games done
        for name, t in teams.items():
            if t["next_game"] is None and not t["eliminated"]:
                t["eliminated"] = True

    return teams


def build_standings(players, team_data):
    standings = []
    for p in players:
        total        = 0
        team_details = []
        for team_name in p["teams"]:
            td = team_data.get(team_name, {
                "wins": [], "ties": [], "total": 0,
                "last_result": None, "next_game": None, "eliminated": False
            })
            total += td["total"]
            team_details.append({"team": team_name, **td})
        standings.append({"name": p["name"], "teams": team_details, "total": total})

    TIEBREAKER = {
        "Luke": 1, "Nolan": 2, "Devin": 3, "Joe Ricc": 4,
        "Joe Kasz": 5, "Joe Klim": 6, "Matt": 7, "Spark": 8, "Reid": 9,
    }
    standings.sort(key=lambda x: (-x["total"], TIEBREAKER.get(x["name"], 99)))
    for i, s in enumerate(standings):
        s["draft_pick"]  = i + 1
        s["tiebreaker"]  = TIEBREAKER.get(s["name"], 99)
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
    print(f"  {len(events)} total matches")

    finished = sum(1 for e in events if e["competitions"][0]["status"]["type"].get("completed"))
    print(f"  {finished} completed")

    team_data  = build_team_data(events)
    standings  = build_standings(config["players"], team_data)

    output = {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "standings":    standings,
        "team_data":    team_data,
        "locked_picks": config["locked_picks"],
    }

    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nWrote {out_path}")
    for s in standings:
        print(f"  Pick {s['draft_pick']:2d}: {s['name']:10s} — {s['total']} pts")


if __name__ == "__main__":
    main()
