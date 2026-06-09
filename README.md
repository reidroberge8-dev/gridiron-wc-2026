# Gridiron World Cup Challenge 2026

Live fantasy scoring site for the Gridiron Fantasy Football draft order challenge.

🌐 **Live site:** https://reidroberge8-dev.github.io/gridiron-wc-2026/

## How It Works

- 9 players each draft 3 World Cup teams
- Points accumulate as teams win matches throughout the tournament
- Final standings = draft order for picks 1–9 in The Gridiron 2026 season
- Picks 10, 11, 12 are pre-assigned (Baker, Pel, Walter)

## Point Values

| Round | Win | Draw |
|-------|-----|------|
| Group Stage | +3 | +1 |
| Round of 32 | +4 | — |
| Round of 16 | +5 | — |
| Quarterfinal | +6 | — |
| Semifinal | +7 | — |
| Final | +8 | — |

*3rd place game omitted.*

## Setup

### 1. Get a free API key
Register at [football-data.org](https://www.football-data.org/client/register) (free, instant).

### 2. Add the API key as a GitHub Secret
`Settings → Secrets and variables → Actions → New repository secret`
- Name: `FOOTBALL_DATA_API_KEY`
- Value: your key

### 3. Enable GitHub Pages
`Settings → Pages → Source: Deploy from branch → main → / (root)`

### 4. Update team assignments
Edit `config/players.json` with each player's 3 teams. Team names must match
the official FIFA names used by football-data.org (e.g. `"United States"`, not `"USA"`).

### 5. Manual score update (optional)
GitHub Actions → "Update World Cup Scores" → "Run workflow"

## Files

```
├── index.html              — the live scoring site
├── config/players.json     — player → team assignments (edit this!)
├── data/scores.json        — auto-updated by GitHub Actions
├── scripts/fetch_scores.py — score fetcher script
└── .github/workflows/
    └── update-scores.yml   — runs every 30 min during tournament
```
