"""Providers, immutable snapshots and conservative persistent download budgets."""
from __future__ import annotations
import hashlib
import io
import json
import time
from pathlib import Path
import pandas as pd
import requests

LEAGUES = {"E0": "Premier League", "SP1": "La Liga", "D1": "Bundesliga", "I1": "Serie A", "F1": "Ligue 1"}
RENAME = {"HomeTeam": "home", "AwayTeam": "away", "FTHG": "hg", "FTAG": "ag", "HC": "hc", "AC": "ac", "HS": "hs", "AS": "as", "HST": "hst", "AST": "ast"}

def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    tmp.replace(path)

class CachedHTTP:
    """No login-wall bypass. 403/429 fail closed; a cache hit costs no request.

    football-data.co.uk permits at most light twice-weekly automated downloads
    for personal/academic use. Budget is global to this cache, not per URL.
    Keep the cache across Colab sessions; do not reset it to evade the limit.
    """
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def get(self, url, ttl_days=7, budget=2):
        host = requests.utils.urlparse(url).hostname
        if host not in {"www.football-data.co.uk", "football-data.co.uk", "raw.githubusercontent.com"}:
            raise ValueError("Provider host is not allowlisted")
        key = hashlib.sha256(url.encode()).hexdigest()
        path = self.root / (key + ".bin")
        ledger_path = self.root / (host + ".json")
        ledger = json.loads(ledger_path.read_text()) if ledger_path.exists() else []
        now = time.time()
        if path.exists() and now - path.stat().st_mtime < ttl_days * 86400:
            return path.read_bytes()
        recent = [r for r in ledger if now - r["time"] < 7 * 86400]
        if len(recent) >= budget:
            if path.exists():
                print("Using cached snapshot: provider budget reached; freshness is recorded.")
                return path.read_bytes()
            raise RuntimeError("Weekly provider download budget reached. Reuse the persistent cache or import a manually downloaded file.")
        # Record attempts before HTTP so retries cannot silently exceed the budget.
        ledger.append({"url": url, "time": now})
        atomic_json(ledger_path, ledger)
        response = requests.get(url, timeout=(15, 90), headers={"User-Agent": "PitchOps/0.1 academic research; cached light download"})
        response.raise_for_status()
        if len(response.content) > 40_000_000:
            raise ValueError("Unexpectedly large provider response")
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(response.content)
        tmp.replace(path)
        atomic_json(self.root / (key + ".json"), {"url": url, "retrieved_at": pd.Timestamp.now(tz="UTC").isoformat(), "sha256": hashlib.sha256(response.content).hexdigest()})
        return response.content

def validate_matches(df):
    required = {"date", "home", "away", "hg", "ag", "league", "season"}
    if not required.issubset(df):
        raise ValueError(f"Missing fields: {sorted(required - set(df))}")
    if df.empty or df[list(required)].isna().any().any():
        raise ValueError("Empty data or missing required match fields")
    if (df.home == df.away).any():
        raise ValueError("A team cannot play itself")
    for field in ["hg", "ag", "hc", "ac", "hs", "as", "hst", "ast"]:
        if field in df:
            values = df[field].dropna()
            if ((values < 0) | (values % 1 != 0)).any():
                raise ValueError(f"Invalid count in {field}")
    keys = ["league", "season", "date", "home", "away"]
    if df.duplicated(keys).any():
        raise ValueError("Duplicate match identities; resolve source conflicts first")
    if df.duplicated(["league", "season", "home", "away"]).any():
        raise ValueError("Repeated home-away pair: this MVP only accepts double round-robin leagues")
    return df.sort_values(keys).reset_index(drop=True)

def normalize(raw, league, season):
    raw = raw.rename(columns=RENAME).copy()
    raw["date"] = pd.to_datetime(raw["Date"], dayfirst=True, errors="coerce").dt.normalize()
    for field in ["hg", "ag", "hc", "ac", "hs", "as", "hst", "ast"]:
        raw[field] = pd.to_numeric(raw[field], errors="coerce") if field in raw else float("nan")
    # Scheduled/unplayed rows cannot become zero-goal training examples.
    raw = raw.dropna(subset=["date", "home", "away", "hg", "ag"])
    raw["home"] = raw.home.astype(str).str.strip()
    raw["away"] = raw.away.astype(str).str.strip()
    raw["league"], raw["season"] = league, season
    return raw[["league", "season", "date", "home", "away", "hg", "ag", "hc", "ac", "hs", "as", "hst", "ast"]]

def load_seasons(root, seasons=("2526", "2627"), leagues=None, local_files=None):
    """One published bulk workbook per season, rather than one request per team.

    local_files: mapping season -> manually downloaded .xlsx; no web request.
    Defaults are an academic starter, not permission for a commercial service.
    """
    root = Path(root)
    cache = CachedHTTP(root / "bronze")
    frames = []
    manifests = []
    for season in seasons:
        if not (len(season) == 4 and season.isdigit()):
            raise ValueError("Season format must be YYZZ, for example 2526")
        year = 2000 + int(season[:2])
        url = f"https://www.football-data.co.uk/mmz4281/{season}/all-euro-data-{year}-{year+1}.xlsx"
        local = (local_files or {}).get(season)
        blob = Path(local).read_bytes() if local else cache.get(url, ttl_days=3650 if year < 2026 else 7)
        workbook = pd.ExcelFile(io.BytesIO(blob))
        selected = leagues or list(LEAGUES)
        for league in selected:
            if league not in workbook.sheet_names:
                raise ValueError(f"{league} missing in {season}: {workbook.sheet_names}")
            frames.append(normalize(pd.read_excel(workbook, sheet_name=league), league, season))
        cache_path = cache.root / (hashlib.sha256(url.encode()).hexdigest() + ".json")
        meta = json.loads(cache_path.read_text()) if cache_path.exists() and not local else {"retrieved_at": None}
        manifests.append({"season": season, "source": str(local) if local else url, "sha256": hashlib.sha256(blob).hexdigest(), "retrieved_at": meta["retrieved_at"]})
    df = validate_matches(pd.concat(frames, ignore_index=True))
    df = df[df.date < pd.Timestamp.now().normalize()]  # conservative: no same-day results
    silver = root / "silver"
    silver.mkdir(parents=True, exist_ok=True)
    df.to_csv(silver / "matches.csv", index=False)
    atomic_json(silver / "manifest.json", manifests)
    return df, manifests
