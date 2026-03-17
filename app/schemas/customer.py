from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CustomerBase(BaseModel):
    customer_type: str = Field(pattern="^(household|sme|industrial)$")


class CustomerCreate(CustomerBase):
    pass


class CustomerRegister(BaseModel):
    customer_type: str = Field(pattern="^(household|sme|industrial)$")


class CustomerLogin(BaseModel):
    customer_id: int
    password: str = Field(min_length=1)


class CustomerUpdate(BaseModel):
    customer_type: str | None = Field(default=None, pattern="^(household|sme|industrial)$")


class CustomerSelfUpdate(BaseModel):
    customer_type: str | None = Field(default=None, pattern="^(household|sme|industrial)$")


class CustomerRead(CustomerBase):
    customer_id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class AuthenticatedCustomer(BaseModel):
    customer: CustomerRead
    access_token: str
    token_type: str = "bearer"
