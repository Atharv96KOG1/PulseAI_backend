from functools import lru_cache

from fastapi import HTTPException, Path

from loom.config import Settings
from loom.db import get_analysis


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def get_analysis_record(analysis_id: str = Path(...)) -> dict:
    record = get_analysis(analysis_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return record
