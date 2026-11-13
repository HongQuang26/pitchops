"""Poisson count models, chronological evaluation and an explicit baseline gate."""
import numpy as np
import pandas as pd
from scipy.stats import poisson
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.linear_model import PoissonRegressor
from sklearn.metrics import mean_absolute_error
from .features import NUMERIC, CATEGORICAL, FEATURES

def score_distribution(home_mean, away_mean, cap=15):
    hm, am = max(float(home_mean), 0.01), max(float(away_mean), 0.01)
    grid = np.outer(poisson.pmf(np.arange(cap + 1), hm), poisson.pmf(np.arange(cap + 1), am))
    retained_mass = float(grid.sum())
    grid /= retained_mass
    return {"home_win": float(np.tril(grid, -1).sum()), "draw": float(np.trace(grid)), "away_win": float(np.triu(grid, 1).sum()), "over25": float(sum(grid[i, j] for i in range(cap + 1) for j in range(cap + 1) if i + j >= 3)), "btts": float(grid[1:, 1:].sum()), "score_grid": grid[:7, :7].round(6).tolist(), "tail_mass": 1 - retained_mass}

def fit_counts(frame, target):
    usable = frame.dropna(subset=[target])
    if len(usable) < 100:
        return None
    prep = ColumnTransformer([("numeric", StandardScaler(), NUMERIC), ("identity", OneHotEncoder(handle_unknown="ignore", sparse_output=False), CATEGORICAL)])
    model = make_pipeline(prep, PoissonRegressor(alpha=0.25, max_iter=400, tol=1e-6))
    return model.fit(usable[FEATURES], usable[target])

def baseline_fit(frame, target="goals"):
    valid = frame.dropna(subset=[target])
    return {"global": float(valid[target].mean()), "rates": {f"{league}|{int(side)}": float(part[target].mean()) for (league, side), part in valid.groupby(["league", "is_home"])}}

def baseline_predict(frame, baseline):
    return np.array([baseline["rates"].get(f"{r.league}|{int(r.is_home)}", baseline["global"]) for r in frame.itertuples()])

def evaluate(frame, means):
    temp = frame[["match_id", "is_home", "goals"]].copy()
    temp["mu"] = means
    probabilities, truths = [], []
    for _, pair in temp.groupby("match_id", sort=False):
        home = pair[pair.is_home == 1].iloc[0]
        away = pair[pair.is_home == 0].iloc[0]
        dist = score_distribution(home.mu, away.mu)
        probabilities.append([dist["home_win"], dist["draw"], dist["away_win"]])
        truths.append(0 if home.goals > away.goals else (2 if home.goals < away.goals else 1))
    probs, truth = np.array(probabilities), np.array(truths)
    bins = []
    confidence = probs.max(axis=1)
    correct = probs.argmax(axis=1) == truth
    for low in np.arange(0.3, 1, 0.1):
        mask = (confidence >= low) & (confidence < low + .1)
        if mask.any():
            bins.append({"predicted": float(confidence[mask].mean()), "observed": float(correct[mask].mean()), "n": int(mask.sum())})
    return {"matches": len(truth), "log_loss": float(-np.log(probs[np.arange(len(truth)), truth].clip(1e-12)).mean()), "brier": float(((probs - np.eye(3)[truth]) ** 2).sum(axis=1).mean()), "goals_mae": float(mean_absolute_error(frame.goals, means)), "accuracy": float(correct.mean()), "reliability": bins}

def train_and_evaluate(features):
    dates = np.sort(features.date.unique())
    if len(dates) < 45:
        raise ValueError("Need at least 45 distinct match dates for temporal validation")
    # 60% development, 20% model selection, 20% untouched temporal test.
    vdate, tdate = dates[int(.6 * len(dates))], dates[int(.8 * len(dates))]
    dev, val, test = features[features.date < vdate], features[(features.date >= vdate) & (features.date < tdate)], features[features.date >= tdate]
    candidate = fit_counts(dev, "goals")
    base = baseline_fit(dev)
    cv = evaluate(val, candidate.predict(val[FEATURES]))
    bv = evaluate(val, baseline_predict(val, base))
    selected = "poisson" if cv["log_loss"] < bv["log_loss"] else "baseline"
    pretest = features[features.date < tdate]
    test_model, test_base = fit_counts(pretest, "goals"), baseline_fit(pretest)
    test_mu = test_model.predict(test[FEATURES]) if selected == "poisson" else baseline_predict(test, test_base)
    report = {"selected": selected, "validation_candidate": cv, "validation_baseline": bv, "test": evaluate(test, test_mu), "test_baseline": evaluate(test, baseline_predict(test, test_base)), "validation_from": str(pd.Timestamp(vdate).date()), "test_from": str(pd.Timestamp(tdate).date()), "evaluation_protocol": "Date-based chronological split; rolling features updated only from earlier observed dates. No random split. Selection uses validation only."}
    models = {target: fit_counts(features, target) for target in ["goals", "corners", "shots"]}
    models["baseline"] = baseline_fit(features)
    models["selected"] = selected
    # Supporting counts are exploratory: MAE on held-out dates, no winner gate.
    report["supporting"] = {}
    for target in ["corners", "shots"]:
        model = fit_counts(pretest, target)
        valid = test.dropna(subset=[target])
        report["supporting"][target] = {"n": len(valid), "mae": float(mean_absolute_error(valid[target], model.predict(valid[FEATURES]))) if model is not None and len(valid) else None, "status": "exploratory"}
    return models, report

def predict_rows(models, frame):
    result = {}
    for target in ["goals", "corners", "shots"]:
        model = models[target]
        values = baseline_predict(frame, models["baseline"]) if target == "goals" and models["selected"] == "baseline" else (model.predict(frame[FEATURES]) if model is not None else None)
        result[target] = np.maximum(values, 0.01).tolist() if values is not None else None
    return result
