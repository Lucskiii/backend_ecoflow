from pydantic import BaseModel, ConfigDict


class SiteBase(BaseModel):
    customer_id: int
    name: str
    location: str | None = None


class SiteRead(SiteBase):
    id: int

    model_config = ConfigDict(from_attributes=True)
