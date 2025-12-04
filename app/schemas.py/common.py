from typing import Annotated, Any
from pydantic import BaseModel, BeforeValidator, Field

# Function: Convert ObjectID to String
def str_object_id(v: Any) -> str:
    if v is None:
        return None
    return str(v)

# PyObjectId datatype for validate MongoDB ID
PyObjectId = Annotated[str, BeforeValidator(str_object_id)]

class MongoBaseModel(BaseModel):
    id: PyObjectId | None = Field(default=None, alias="_id")

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_schema_extra = {
            "example": {
                "id": "64f1a0b2c3d4e5f6a7b8c9d0"
            }
        }