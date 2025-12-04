from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

from common import MongoBaseModel, PyObjectId

class SerieBase(BaseModel):
    serie_title: str = Field(..., min_length=1)
    serie_description: Optional[str] = ""
    isPublish: bool = False

class SerieCreate(SerieBase):
    pass

class SerieUpdate(BaseModel):
    serie_title: Optional[str] = None
    serie_description: Optional[str] = None
    isPublish: Optional[bool] = None


class SerieResponse(MongoBaseModel, SerieBase):
    serie_thumbnail: Optional[str] = None
    serie_lessons: List[PyObjectId] = []
    serie_subscribe_num: int = 0
    serie_user: str
    createdAt: Optional[datetime] = None
    updatedAt: Optional[datetime] = None

    class Config:
        from_attributes = True