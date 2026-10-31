from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.auth.models import Role


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(max_length=128)


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    role: Role


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    role: Role
