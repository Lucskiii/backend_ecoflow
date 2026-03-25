from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.tables import Customer, Site
from app.clients.opencage_client import OpenCageClientError
from app.services.geocoding_service import GeocodingService


class FallbackClient:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def geocode_address(self, address: str) -> tuple[float, float]:
        self.calls.append(address)
        if "Stephansplatz" in address:
            raise OpenCageClientError("not found")
        if "1010" in address:
            return (48.2082, 16.3738)
        raise OpenCageClientError("not found")


class AlwaysSuccessClient:
    def geocode_address(self, address: str) -> tuple[float, float]:
        return (48.2082, 16.3738)


def _setup_test_db() -> sessionmaker[Session]:
    engine = create_engine("sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    testing_session_local = sessionmaker(bind=engine, autocommit=False, autoflush=False, class_=Session)
    Base.metadata.create_all(bind=engine)
    return testing_session_local


def test_geocode_address_uses_fallback_queries() -> None:
    service = GeocodingService(client=FallbackClient())
    result = service.geocode_address(
        address_line1="Stephansplatz 1",
        city="Vienna",
        postal_code="1010",
        country="Austria",
    )

    assert result.latitude == Decimal("48.208200")
    assert result.longitude == Decimal("16.373800")


def test_geocode_site_updates_coordinates() -> None:
    testing_session_local = _setup_test_db()
    db = testing_session_local()
    try:
        customer = Customer(
            id=1,
            name="Geo Customer",
            email="geo@example.com",
            address_line1="Stephansplatz 1",
            city="Vienna",
            postal_code="1010",
            country="Austria",
        )
        db.add(customer)
        db.flush()
        site = Site(
            id=1,
            customer_id=customer.id,
            site_code="site-1",
            name="Site 1",
            timezone="UTC",
            latitude=None,
            longitude=None,
        )
        db.add(site)
        db.commit()

        service = GeocodingService(db=db, client=AlwaysSuccessClient())
        result = service.geocode_site(site.id)

        db.refresh(site)
        assert result.latitude == Decimal("48.208200")
        assert result.longitude == Decimal("16.373800")
        assert site.latitude == Decimal("48.208200")
        assert site.longitude == Decimal("16.373800")
    finally:
        db.close()
