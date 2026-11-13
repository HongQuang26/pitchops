"""Optional empirical-Bayes scorer projections from imported player match logs.

No invented player ratings or inferred 'official' man of the match labels.
Player IDs must be provider IDs, not names used as a global join key.
"""
import numpy as np
import pandas as pd

def scorer_projection(logs, as_of, expected_minutes, prior_goals90=0.15, prior_minutes=900):
    """expected_minutes: {player_id: prospective minutes}, chosen before kickoff.

    Missing future minutes cause an error, never use target-match actual minutes.
    Output is conditional on these minutes; appearance probability is not learned.
    """
    required = {"player_id", "player", "team", "date", "minutes", "goals"}
    if not required.issubset(logs):
        raise ValueError(f"Missing {required - set(logs)}")
    df = logs.copy()
    df["date"] = pd.to_datetime(df.date)
    df = df[df.date < pd.Timestamp(as_of)]
    if df.empty:
        return []
    if ((df.minutes < 0) | (df.minutes > 130) | (df.goals < 0) | (df.goals % 1 != 0)).any():
        raise ValueError("Invalid player minutes/goals")
    rows = []
    for pid, hist in df.groupby("player_id"):
        if pid not in expected_minutes:
            continue
        mins = float(expected_minutes[pid])
        if not 0 <= mins <= 120:
            raise ValueError("Prospective minutes must be in [0, 120]")
        hist = hist.sort_values("date").tail(20)
        latest = hist.iloc[-1]
        rate = (hist.goals.sum() + prior_goals90 * prior_minutes / 90) / (hist.minutes.sum() + prior_minutes)
        mu = float(rate * mins)
        rows.append({"player_id": str(pid), "player": str(latest.player), "team": str(latest.team), "expected_minutes": mins, "expected_goals": mu, "p_score": float(1-np.exp(-mu)), "p_2plus": float(1-np.exp(-mu)*(1+mu)), "method": "Empirical Bayes Poisson; conditional on supplied minutes; not opponent-adjusted"})
    return sorted(rows, key=lambda x: -x["p_score"])

def select_form_xi(logs, as_of, period="week"):
    """Historical form XI, NOT a forecast of an official award.

    Requires imported provider ratings and GK/DF/MF/FW position mapping.
    Rank by minutes-weighted observed rating within the specified past period.
    """
    required = {"player_id", "player", "team", "date", "minutes", "rating", "position"}
    if not required.issubset(logs):
        raise ValueError("Historical XI requires provider ratings and normalized positions")
    days = {"week": 7, "month": 30, "year": 365}[period]
    df = logs.copy()
    df["date"] = pd.to_datetime(df.date)
    cutoff = pd.Timestamp(as_of)
    df = df[(df.date < cutoff) & (df.date >= cutoff-pd.Timedelta(days=days)) & (df.minutes > 0)].dropna(subset=["rating"])
    aggregated = []
    for pid, rows in df.groupby("player_id"):
        last = rows.sort_values("date").iloc[-1]
        if rows.minutes.sum() < 45:
            continue
        aggregated.append({"player_id": str(pid), "player": last.player, "team": last.team, "position": last.position, "rating": float(np.average(rows.rating, weights=rows.minutes)), "minutes": float(rows.minutes.sum())})
    xi = []
    for position, count in {"GK": 1, "DF": 4, "MF": 3, "FW": 3}.items():
        candidates = sorted([x for x in aggregated if x["position"] == position], key=lambda x: -x["rating"])
        if len(candidates) < count:
            raise ValueError(f"Not enough {position} players for a valid 4-3-3")
        xi.extend(candidates[:count])
    return xi
