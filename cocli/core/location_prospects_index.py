import os
import pandas as pd
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)

class LocationProspectsIndex:
    def __init__(self, campaign_name: str, data_home: str = "~/.local/share/cocli_data"):
        self.campaign_name = campaign_name
        self.data_home = os.path.expanduser(data_home)
        self.index_dir = os.path.join(self.data_home, "campaigns", campaign_name, "indexes")
        os.makedirs(self.index_dir, exist_ok=True)
        self.index_file = os.path.join(self.index_dir, "location-prospects.csv")
        self.index_df = self._load_index()

    def _load_index(self) -> pd.DataFrame:
        if os.path.exists(self.index_file):
            try:
                df = pd.read_csv(self.index_file)
                logger.info(f"Loaded location prospects index from {self.index_file}")
                return df
            except Exception as e:
                logger.warning(f"Could not load location prospects index from {self.index_file}: {e}. Starting with empty index.")
                return pd.DataFrame(columns=["location_name", "prospect_count", "last_updated"])
        return pd.DataFrame(columns=["location_name", "prospect_count", "last_updated"])

    def _save_index(self):
        self.index_df.to_csv(self.index_file, index=False)
        logger.info(f"Saved location prospects index to {self.index_file}")

    def update_prospect_count(self, location_name: str, count: int):
        if location_name in self.index_df["location_name"].values:
            self.index_df.loc[self.index_df["location_name"] == location_name, "prospect_count"] += count
            self.index_df.loc[self.index_df["location_name"] == location_name, "last_updated"] = pd.Timestamp.now().isoformat()
            logger.info(f"Updated prospect count for {location_name} by {count}. New total: {self.get_prospect_count(location_name)}")
        else:
            new_row = pd.DataFrame([{
                "location_name": location_name,
                "prospect_count": count,
                "last_updated": pd.Timestamp.now().isoformat()
            }])
            self.index_df = pd.concat([self.index_df, new_row], ignore_index=True)
            logger.info(f"Added new location {location_name} with {count} prospects.")
        self._save_index()

    def get_prospect_count(self, location_name: str) -> int:
        if location_name in self.index_df["location_name"].values:
            return int(self.index_df.loc[self.index_df["location_name"] == location_name, "prospect_count"].iloc[0])
        return 0

    def get_least_prospected_locations(self, n: int = 3) -> pd.DataFrame:
        return self.index_df.sort_values(by="prospect_count", ascending=True).head(n)

    def get_all_locations(self) -> pd.DataFrame:
        return self.index_df
