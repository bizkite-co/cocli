import datetime
from pathlib import Path
from pydantic import BaseModel

class Meeting(BaseModel):
    datetime_local: datetime.datetime
    file_path: Path
    title: str