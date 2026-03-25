from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.tables import Customer, Site
from app.services.customer_site_coordinate_service import CustomerSiteCoordinateService
from app.services.geocoding_service import GeocodeResult


class StubGeocodingService:
    def geocode_site(self, site_id: int, force: bool = False) -> GeocodeResult:
        assert site_id == 1
        return GeocodeResult(latitude=Decimal("48.208200"), longitude=Decimal("16.373800"))


def _setup_test_db() -> sessionmaker[Session]:
    engine = create_engine("sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    testing_session_local = sessionmaker(bind=engine, autocommit=False, autoflush=False, class_=Session)
    Base.metadata.create_all(bind=engine)
    return testing_session_local


def test_backfill_missing_site_coordinates_from_customer_address() -> None:
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
            site_code="geo-site",
            name="Geo Site",
            timezone="UTC",
            latitude=None,
            longitude=None,
        )
        db.add(site)
        db.commit()

        result = CustomerSiteCoordinateService(db, geocoding_service=StubGeocodingService()).backfill_missing_site_coordinates()

        db.refresh(customer)
        db.refresh(site)
        assert result == {"customers_geocoded": 1, "sites_updated": 1}
        assert site.latitude == Decimal("48.208200")
        assert site.longitude == Decimal("16.373800")
    finally:
        db.close()
