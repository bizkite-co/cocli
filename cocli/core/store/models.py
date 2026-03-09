from pydantic import BaseModel, Field
from pathlib import Path
from ..text_utils import slugify

class OmapPathModel(BaseModel):
    """
    Base model for representing a physical path in the OMAP structure.
    """
    root: Path = Field(..., description="The base directory for this path component.")
    
    def to_path(self) -> Path:
        """Returns the full validated filesystem path."""
        raise NotImplementedError

class TilePath(OmapPathModel):
    """
    Represents a coordinate-sharded path (lat/lon/phrase).
    Used by ScrapedTiles, GM List Results, and Raw Witnesses.
    """
    latitude: float
    longitude: float
    phrase: str
    extension: str = ".usv"

    def to_path(self) -> Path:
        from ..sharding import get_grid_tile_id, get_geo_shard
        tile_id = get_grid_tile_id(self.latitude, self.longitude)
        geo_shard = get_geo_shard(self.latitude)
        lat_tile, lon_tile = tile_id.split("_")
        phrase_slug = slugify(self.phrase)
        return self.root / geo_shard / lat_tile / lon_tile / f"{phrase_slug}{self.extension}"

class ShardPath(OmapPathModel):
    """
    Represents a character-sharded path (shard_char/identity).
    Used by Prospects WAL and individual company files.
    """
    shard_char: str = Field(..., min_length=1, max_length=2)
    identity: str
    extension: str = ".usv"

    def to_path(self) -> Path:
        return self.root / self.shard_char / f"{self.identity}{self.extension}"

class ShardIDPath(OmapPathModel):
    """
    Represents a 2-character hex sharded path (00-ff/identity).
    Used by Email Index Inbox.
    """
    shard_id: str = Field(..., min_length=2, max_length=2)
    identity: str
    extension: str = ".usv"

    def to_path(self) -> Path:
        return self.root / self.shard_id / f"{self.identity}{self.extension}"
