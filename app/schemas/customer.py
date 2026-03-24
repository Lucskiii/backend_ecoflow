from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator


class CustomerBase(BaseModel):
    name: str = Field(min_length=1)
    email: EmailStr
    address_line1: str | None = Field(default=None, min_length=3)
    city: str | None = Field(default=None, min_length=2)
    postal_code: str | None = Field(default=None, min_length=2)
    country: str | None = Field(default=None, min_length=2)


class CustomerCreate(CustomerBase):
    pass


class CustomerRegister(CustomerBase):
    password: str = Field(min_length=8)

    @model_validator(mode="after")
    def validate_address_fields(self) -> "CustomerRegister":
        required_fields = ("address_line1", "city", "postal_code", "country")
        missing = [field for field in required_fields if not getattr(self, field)]
        if missing:
            raise ValueError("Address is required for registration")
        return self


class CustomerLogin(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class CustomerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    email: EmailStr | None = None


class CustomerSelfUpdate(BaseModel):
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
