from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

from app.schemas.common import MongoBaseModel, PyObjectId

class LessonBase(BaseModel):
    lesson_title: str = Field(..., min_length=1)
    lesson_content: Optional[str] = ""

class LessonCreate(LessonBase):
    pass

class LessonUpdate(BaseModel):
    lesson_title: Optional[str] = None
    lesson_content: Optional[str] = None

class LessonResponse(MongoBaseModel, LessonBase):
    lesson_video: Optional[str] = None
    lesson_documents: List[str] = []
    lesson_serie: str
    createdAt: Optional[datetime] = None
    updatedAt: Optional[datetime] = None

    class Config:
        from_attributes = True