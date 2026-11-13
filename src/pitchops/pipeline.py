"""A single restartable Colab pipeline; no hidden background compute."""
import argparse
import hashlib
import json
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
import sklearn
from .data import LEAGUES, atomic_json, load_seasons
from .features import build_features, match_rows
from .models import train_and_evaluate, predict_rows, score_distribution
from .simulation import simulate_league

def run(root, seasons=("2526", "2627"), leagues=None, as_of=None, simulations=5000, local_files=None):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    print("1/6 Collecting cached academic snapshots", flush=True)
    matches, manifests = load_seasons(root / "data", seasons, leagues, local_files)
    if as_of:
        matches = matches[matches.date < pd.Timestamp(as_of)].reset_index(drop=True)
    if matches.empty:
        raise ValueError("No completed matches before cutoff")
    canonical = matches.to_csv(index=False).encode()
    data_hash = hashlib.sha256(canonical).hexdigest()
    print(f"2/6 Building point-in-time features for {len(matches):,} matches", flush=True)
    features, state = build_features(matches)
    print("3/6 Training + chronological validation + untouched test", flush=True)
    models, report = train_and_evaluate(features)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = timestamp + "-" + data_hash[:10]
    run_dir = root / "artifacts" / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump({"models": models, "state": state, "as_of": as_of, "data_hash": data_hash}, run_dir / "model.joblib")
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        commit = "uncommitted"
    metadata = {"run_id": run_id, "created_at": datetime.now(timezone.utc).isoformat(), "data_sha256": data_hash, "code_commit": commit, "python": platform.python_version(), "sklearn": sklearn.__version__, "numpy": np.__version__, "pandas": pd.__version__, "training_from": str(matches.date.min().date()), "training_through": str(matches.date.max().date()), "forecast_date": str((matches.date.max() + pd.Timedelta(days=1)).date()), "seed": 42, "source": "football-data.co.uk", "source_manifests": manifests, "matches": len(matches), "features": len(features), "calibration": "Reliability measured on test; no post-hoc calibration fitted; Poisson independence assumption", "status": "research"}
    payload = {"meta": metadata, "metrics": report, "leagues": {}}
    print("4/6 Forecasting all within-league home-away combinations", flush=True)
    for league in sorted(matches.league.unique()):
        season = sorted(matches[matches.league == league].season.unique())[-1]
        current = matches[(matches.league == league) & (matches.season == season)]
        teams = sorted(set(current.home) | set(current.away))
        date = matches.date.max() + pd.Timedelta(days=1)
        pairs = [(h, a) for h in teams for a in teams if h != a]
        frame = pd.DataFrame([r for h, a in pairs for r in match_rows(h, a, league, date, state)])
        forecasts = predict_rows(models, frame)
        lookup = {}
        for i, (home, away) in enumerate(pairs):
            hg, ag = forecasts["goals"][2*i:2*i+2]
            dist = score_distribution(hg, ag)
            dist["goals"] = [hg, ag]
            dist["corners"] = forecasts["corners"][2*i:2*i+2] if forecasts["corners"] else None
            dist["shots"] = forecasts["shots"][2*i:2*i+2] if forecasts["shots"] else None
            lookup[home + "|" + away] = dist
        race = simulate_league(matches, league, season, models, state, simulations)
        payload["leagues"][league] = {"name": LEAGUES[league], "season": season, "teams": teams, "forecasts": lookup, "race": race, "matches": len(current), "last_result": str(current.date.max().date()), "sparse_teams": [t for t in teams if len(state.get((league,t),[])) < 5]}
    print("5/6 Recording artifacts + data-quality and drift summaries", flush=True)
    numeric = ["own_gf", "own_ga", "own_points", "own_rest"]
    dates = sorted(features.date.unique())
    split = dates[int(len(dates)*.8)]
    reference, recent = features[features.date < split], features[features.date >= split]
    payload["drift"] = [{"feature": col, "standardized_mean_shift": float((recent[col].mean()-reference[col].mean()) / max(reference[col].std(), 1e-6))} for col in numeric]
    payload["quality"] = {"duplicate_matches": 0, "missing_goal_labels": 0, "optional_corner_coverage": float(matches[["hc", "ac"]].notna().all(axis=1).mean()), "optional_shot_coverage": float(matches[["hs", "as"]].notna().all(axis=1).mean()), "snapshot_age_days": int((pd.Timestamp.now().normalize()-matches.date.max()).days)}
    atomic_json(run_dir / "snapshot.json", payload)
    atomic_json(run_dir / "metrics.json", report)
    atomic_json(run_dir / "model_card.json", metadata)
    atomic_json(root / "artifacts" / "latest.json", {"run_id": run_id, "snapshot": str(run_dir / "snapshot.json")})
    # Environment lock is run-specific; do not silently claim untested exact pins.
    freeze = subprocess.run(["python", "-m", "pip", "freeze"], capture_output=True, text=True, check=True)
    (run_dir / "requirements-lock.txt").write_text(freeze.stdout)
    print("6/6 Rendering interactive offline dashboard", flush=True)
    from .dashboard import render_dashboard
    render_dashboard(payload, run_dir / "dashboard.html")
    print(json.dumps({"run_id": run_id, "selected": report["selected"], "test_log_loss": report["test"]["log_loss"], "test_baseline_log_loss": report["test_baseline"]["log_loss"], "dashboard": str(run_dir / "dashboard.html")}, indent=2), flush=True)
    return payload, run_dir

def track_mlflow(payload, run_dir):
    """Optional: pip install -e '.[tracking]'. Local tracking, no account needed."""
    import mlflow
    mlflow.set_tracking_uri((Path(run_dir).parents[2] / "mlruns").resolve().as_uri())
    mlflow.set_experiment("pitchops")
    with mlflow.start_run(run_name=payload["meta"]["run_id"]):
        mlflow.log_params({"model": payload["metrics"]["selected"], "seed": 42, "data_sha256": payload["meta"]["data_sha256"], "code_commit": payload["meta"]["code_commit"]})
        mlflow.log_metrics({k: v for k, v in payload["metrics"]["test"].items() if isinstance(v, (int,float))})
        mlflow.log_artifacts(str(run_dir))

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="/content/pitchops_workspace")
    parser.add_argument("--as-of")
    parser.add_argument("--simulations", type=int, default=5000)
    args = parser.parse_args()
    run(args.root, as_of=args.as_of, simulations=args.simulations)
