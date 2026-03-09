from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class CustomerBase(BaseModel):
    name: str = Field(min_length=1)
    email: EmailStr


class CustomerCreate(CustomerBase):
    pass


class CustomerRegister(CustomerBase):
    password: str = Field(min_length=8)


class CustomerLogin(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class CustomerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    email: EmailStr | None = None


class CustomerRead(CustomerBase):
    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class AuthenticatedCustomer(BaseModel):
    customer: CustomerRead
    access_token: str
    token_type: str = "bearer"
