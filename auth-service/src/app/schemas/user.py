from datetime import datetime
from pydantic import BaseModel, ConfigDict, EmailStr


class UserResponseSchema(BaseModel):
    id: int
    email: EmailStr
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)