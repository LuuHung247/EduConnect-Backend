from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import datetime

class UserBase(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    username: Optional[str] = None


class UserCreate(UserBase):
    userId: str = Field(..., description="Cognito User ID")
    name: str
    email: EmailStr
    username: str


class UserUpdate(UserBase):
    pass


class UserResponse(UserBase):
    id: str = Field(..., alias="_id")
    userId: str
    serie_subscribe: List[str] = []
    createdAt: Optional[datetime] = None
    updatedAt: Optional[datetime] = None

    class Config:
        populate_by_name = True
        from_attributes = True