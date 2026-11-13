"""StatsBomb adapter: measured event-location density, not tracking heatmaps.

Open Data contains selected competitions/seasons, not global live coverage.
Read the StatsBomb licence and supply their required logo/credit before publishing
an event-derived visualization. This adapter does not publish any data by itself.
"""
import pandas as pd
from .data import CachedHTTP

BASE = "https://raw.githubusercontent.com/hudl/open-data/master/data"

class StatsBomb:
    def __init__(self, root):
        self.http = CachedHTTP(root)

    def _json(self, suffix):
        import json
        # bounded batch budget: no crawling every event file in the repository
        return json.loads(self.http.get(f"{BASE}/{suffix}.json", ttl_days=365, budget=80))

    def competitions(self):
        return pd.DataFrame(self._json("competitions"))

    def matches(self, competition_id, season_id):
        return pd.DataFrame(self._json(f"matches/{int(competition_id)}/{int(season_id)}"))

    def player_locations(self, match_id, player_id):
        events = self._json(f"events/{int(match_id)}")
        rows = [{"x": e["location"][0], "y": e["location"][1], "minute": e.get("minute"), "event": e.get("type", {}).get("name")} for e in events if e.get("player", {}).get("id") == int(player_id) and len(e.get("location", [])) == 2]
        return pd.DataFrame(rows, columns=["x", "y", "minute", "event"])
