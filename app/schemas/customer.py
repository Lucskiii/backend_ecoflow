from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr


class CustomerBase(BaseModel):
    name: str
    email: EmailStr


class CustomerCreate(CustomerBase):
    pass


class CustomerUpdate(BaseModel):
    name: str | None = None
    email: EmailStr | None = None


class CustomerRead(CustomerBase):
    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
