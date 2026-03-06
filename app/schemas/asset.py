from pydantic import BaseModel, ConfigDict


class AssetBase(BaseModel):
    site_id: int
    name: str
    asset_type: str


class AssetRead(AssetBase):
    id: int

    model_config = ConfigDict(from_attributes=True)
