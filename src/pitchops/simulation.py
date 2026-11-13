"""Domestic double round-robin simulation with points, goal difference and GF.

Not a UEFA/FIFA knockout engine. Club strengths are frozen during a simulation.
"""
import numpy as np
import pandas as pd
from .features import match_rows
from .models import predict_rows

EXPECTED_TEAMS = {"E0": 20, "SP1": 20, "D1": 18, "I1": 20, "F1": 18}

def simulate_league(matches, league, season, models, state, simulations=5000, seed=42, as_of=None):
    played = matches[(matches.league == league) & (matches.season == season)]
    teams = sorted(set(played.home) | set(played.away))
    if len(teams) != EXPECTED_TEAMS[league]:
        return {"status": "unavailable", "reason": "Incomplete season membership; import a verified fixture list before simulating."}
    ix = {team: i for i, team in enumerate(teams)}
    n = len(teams)
    points, gd, gf = np.zeros(n), np.zeros(n), np.zeros(n)
    for m in played.itertuples():
        h, a = ix[m.home], ix[m.away]
        points[h] += 3 if m.hg > m.ag else (1 if m.hg == m.ag else 0)
        points[a] += 3 if m.ag > m.hg else (1 if m.hg == m.ag else 0)
        gd[h] += m.hg - m.ag
        gd[a] += m.ag - m.hg
        gf[h] += m.hg
        gf[a] += m.ag
    seen = set(zip(played.home, played.away))
    remaining = [(h, a) for h in teams for a in teams if h != a and (h, a) not in seen]
    date = pd.Timestamp(as_of) if as_of is not None else played.date.max() + pd.Timedelta(days=1)
    features = [row for h, a in remaining for row in match_rows(h, a, league, date, state)]
    means = predict_rows(models, pd.DataFrame(features))["goals"] if features else []
    rng = np.random.default_rng(seed)
    pts = np.tile(points, (simulations, 1))
    diff = np.tile(gd, (simulations, 1))
    goals = np.tile(gf, (simulations, 1))
    for j, (home, away) in enumerate(remaining):
        h, a = ix[home], ix[away]
        hg, ag = rng.poisson(means[2*j], simulations), rng.poisson(means[2*j+1], simulations)
        pts[:, h] += 3 * (hg > ag) + (hg == ag)
        pts[:, a] += 3 * (ag > hg) + (hg == ag)
        diff[:, h] += hg - ag
        diff[:, a] += ag - hg
        goals[:, h] += hg
        goals[:, a] += ag
    # Lexicographic tie-break, randomized only if points/GD/GF all equal.
    ranks = np.empty((simulations, n), dtype=int)
    for s in range(simulations):
        order = np.lexsort((rng.random(n), -goals[s], -diff[s], -pts[s]))
        ranks[s, order] = np.arange(1, n + 1)
    rows = []
    for team, i in ix.items():
        probability = float((ranks[:, i] == 1).mean())
        rows.append({"team": team, "played": int(((played.home == team) | (played.away == team)).sum()), "points": int(points[i]), "title": probability, "title_mc_se": float(np.sqrt(probability * (1-probability) / simulations)), "top4": float((ranks[:, i] <= 4).mean()), "bottom3": float((ranks[:, i] > n-3).mean()), "expected_points": float(pts[:, i].mean()), "points_p10": float(np.quantile(pts[:, i], .1)), "points_p90": float(np.quantile(pts[:, i], .9))})
    return {"status": "scenario" if remaining else "completed", "simulations": simulations, "remaining_matches": len(remaining), "assumptions": "Domestic double round-robin; all remaining home-away pairs inferred, not official dates; frozen strengths; points/GD/GF then random ties. Head-to-head/playoff rules not modeled. Top4/bottom3 are rank bands, not guaranteed qualification/relegation. Monte Carlo error is not model uncertainty.", "table": sorted(rows, key=lambda r: (-r["title"], -r["expected_points"]))}
