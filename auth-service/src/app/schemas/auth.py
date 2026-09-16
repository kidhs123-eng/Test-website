from datetime import datetime
from pydantic import BaseModel, ConfigDict, EmailStr


class RegisterSchema(BaseModel):
    email: EmailStr
    password: str


class LoginSchema(BaseModel):
    email: EmailStr
    password: str


class TokenSchema(BaseModel):
    access_token: str
    token_type: str = "bearer"


class SetPasswordSchema(BaseModel):
    new_password: str