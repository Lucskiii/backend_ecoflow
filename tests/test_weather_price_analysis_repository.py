from datetime import date, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
from app.models.tables import CoreBiddingZone, CoreMarket, CoreMarketProduct, CoreTsMarketPrice
from app.repositories.weather_price_analysis_repository import WeatherPriceAnalysisRepository
from app.schemas.weather_price_analysis import WeatherPriceAnalysisRequest


def _setup_test_db() -> sessionmaker[Session]:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    testing_session_local = sessionmaker(bind=engine, autocommit=False, autoflush=False, class_=Session)
    Base.metadata.create_all(bind=engine)
    return testing_session_local


def test_weather_price_request_requires_bidding_zone_id() -> None:
    with pytest.raises(ValidationError):
        WeatherPriceAnalysisRequest(
            start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 2),
            cities=[{"analysis_city_id": 1, "weight": Decimal("1.0")}],
        )


def test_get_prices_filters_by_bidding_zone() -> None:
    testing_session_local = _setup_test_db()
    db = testing_session_local()
    repository = WeatherPriceAnalysisRepository(db)

    market = CoreMarket(id=1, code="m-1", name="Market 1")
    db.add(market)
    db.flush()

    product = CoreMarketProduct(id=1, market_id=market.id, product_code="spot", granularity_minutes=60)
    db.add(product)
    db.flush()

    zone_a = CoreBiddingZone(id=1, code="ZONE-A", name="Zone A")
    zone_b = CoreBiddingZone(id=2, code="ZONE-B", name="Zone B")
    db.add_all([zone_a, zone_b])
    db.flush()

    ts = datetime(2026, 3, 1, 0, 0)
    db.add_all(
        [
            CoreTsMarketPrice(
                market_product_id=product.id,
                bidding_zone_id=zone_a.id,
                ts=ts,
                price=Decimal("50.0"),
            ),
            CoreTsMarketPrice(
                market_product_id=product.id,
                bidding_zone_id=zone_b.id,
                ts=ts,
                price=Decimal("70.0"),
            ),
        ]
    )
    db.commit()

    prices_a = repository.get_prices(ts, ts, product_id=product.id, bidding_zone_id=zone_a.id)
    prices_b = repository.get_prices(ts, ts, product_id=product.id, bidding_zone_id=zone_b.id)

    assert prices_a == {ts: Decimal("50.000000")}
    assert prices_b == {ts: Decimal("70.000000")}

    db.close()
