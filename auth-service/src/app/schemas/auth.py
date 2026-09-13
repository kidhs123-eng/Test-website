from pydantic import BaseModel, EmailStr, Field


class RegisterSchema(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6)


class LoginSchema(BaseModel):
    email: EmailStr
    password: str


class TokenSchema(BaseModel):
    access_token: str
    token_type: str = "bearer"


class SetPasswordSchema(BaseModel):
    new_password: str = Field(..., min_length=6)