"""Point-in-time features. All matches on a date see only earlier dates."""
from collections import defaultdict
import numpy as np
import pandas as pd

NUMERIC = ["is_home", "own_gf", "own_ga", "opp_gf", "opp_ga", "own_points", "opp_points", "own_games", "opp_games", "own_rest", "opp_rest"]
CATEGORICAL = ["team", "opponent", "league"]
FEATURES = CATEGORICAL + NUMERIC

def summary(history, date):
    recent = history[-5:]
    if not recent:
        return {"gf": 1.3, "ga": 1.3, "points": 1.3, "games": 0, "rest": 14.0}
    return {"gf": np.mean([x[1] for x in recent]), "ga": np.mean([x[2] for x in recent]), "points": np.mean([x[3] for x in recent]), "games": min(len(history), 30), "rest": min((date - history[-1][0]).days, 30)}

def match_rows(home, away, league, date, state):
    a = summary(state.get((league, home), []), date)
    b = summary(state.get((league, away), []), date)
    rows = []
    for team, opp, own, other, is_home in [(home, away, a, b, 1), (away, home, b, a, 0)]:
        row = {"team": team, "opponent": opp, "league": league, "is_home": is_home}
        row.update({f"own_{k}": v for k, v in own.items()})
        row.update({f"opp_{k}": v for k, v in other.items()})
        rows.append(row)
    return rows

def build_features(matches):
    state = defaultdict(list)
    rows = []
    # Batch by day: a later result on the same day must not inform an earlier game.
    for date, batch in matches.sort_values("date").groupby("date", sort=True):
        updates = []
        for idx, m in batch.iterrows():
            pair = match_rows(m.home, m.away, m.league, date, state)
            for side, row in enumerate(pair):
                row.update({"match_id": int(idx), "date": date, "season": m.season, "goals": float(m.hg if side == 0 else m.ag), "corners": float(m.hc if side == 0 else m.ac), "shots": float(m.hs if side == 0 else m["as"])})
                rows.append(row)
            hp, ap = (3, 0) if m.hg > m.ag else ((0, 3) if m.hg < m.ag else (1, 1))
            updates.extend([((m.league, m.home), (date, m.hg, m.ag, hp)), ((m.league, m.away), (date, m.ag, m.hg, ap))])
        for key, value in updates:
            state[key].append(value)
    return pd.DataFrame(rows), dict(state)
