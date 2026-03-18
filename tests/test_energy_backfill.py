from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.customer import Customer
from app.models.tables import CoreMeter, CoreQualityFlag, CoreTsMeterReading, Site
from app.services.energy_service import EnergyService, INTERVAL_SECONDS, METER_TYPES


def _setup_test_db() -> sessionmaker[Session]:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session_local = sessionmaker(bind=engine, autocommit=False, autoflush=False, class_=Session)
    Base.metadata.create_all(bind=engine)
    return testing_session_local


def _next_id(db: Session, model) -> int:
    return (db.scalar(select(func.coalesce(func.max(model.id), 0))) or 0) + 1


def _create_customer(db: Session, email: str = "user@example.com") -> Customer:
    customer = Customer(id=_next_id(db, Customer), name="User", email=email, password_hash="hash")
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer


def _create_site(db: Session, customer_id: int, code: str) -> Site:
    site = Site(id=_next_id(db, Site), customer_id=customer_id, site_code=code, name=code, timezone="UTC")
    db.add(site)
    db.commit()
    db.refresh(site)
    return site




def _ensure_quality_flag(db: Session) -> int:
    quality = db.scalar(select(CoreQualityFlag).where(CoreQualityFlag.code == "estimated"))
    if quality is None:
        quality = CoreQualityFlag(
            id=_next_id(db, CoreQualityFlag),
            code="estimated",
            description="Simulated/estimated value",
            severity=0,
        )
        db.add(quality)
        db.commit()
        db.refresh(quality)
    return quality.id


def _create_meter(db: Session, site_id: int, role: str) -> CoreMeter:
    meter = CoreMeter(
        id=_next_id(db, CoreMeter),
        site_id=site_id,
        meter_code=f"site-{site_id}-{role}",
        meter_role=role,
        unit="kWh",
    )
    db.add(meter)
    db.commit()
    db.refresh(meter)
    return meter


def test_backfill_skips_partial_role_sites_without_overwriting_existing_data() -> None:
    testing_session_local = _setup_test_db()
    db = testing_session_local()
    try:
        service = EnergyService(db)
        customer = _create_customer(db, email="partial@example.com")
        site = _create_site(db, customer.id, "partial-site")
        load_meter = _create_meter(db, site.id, "load")

        existing_ts = service._round_to_interval(datetime.now(timezone.utc) - timedelta(hours=1))
        db.add(
            CoreTsMeterReading(
                meter_id=load_meter.id,
                ts=existing_ts,
                interval_seconds=INTERVAL_SECONDS,
                value=1,
            )
        )
        db.commit()

        _ensure_quality_flag(db)
        result = service.backfill_customer_data_to_now(customer)
        assert result is None

        readings = db.scalars(select(CoreTsMeterReading).where(CoreTsMeterReading.meter_id == load_meter.id)).all()
        assert len(readings) == 1
        assert readings[0].ts == existing_ts.replace(tzinfo=None)
        assert readings[0].value == 1
    finally:
        db.close()


def test_backfill_uses_site_scoped_completeness_for_multi_site_customers() -> None:
    testing_session_local = _setup_test_db()
    db = testing_session_local()
    try:
        service = EnergyService(db)
        customer = _create_customer(db, email="multi@example.com")
        current_end = service._round_to_interval(datetime.now(timezone.utc))
        stale_end = current_end - timedelta(hours=1)
        start_ts = current_end - timedelta(days=1)

        site_a = _create_site(db, customer.id, "site-a")
        site_b = _create_site(db, customer.id, "site-b")
        meters_a = {role: _create_meter(db, site_a.id, role) for role in METER_TYPES}
        meters_b = {role: _create_meter(db, site_b.id, role) for role in METER_TYPES}
        quality_flag_id = _ensure_quality_flag(db)

        db.execute(CoreTsMeterReading.__table__.insert(), service._build_readings(customer.id, site_a.id, meters_a, quality_flag_id, start_ts, current_end))
        db.execute(CoreTsMeterReading.__table__.insert(), service._build_readings(customer.id, site_b.id, meters_b, quality_flag_id, start_ts, stale_end))
        db.commit()

        before_site_b_max = db.scalar(
            select(func.max(CoreTsMeterReading.ts)).where(CoreTsMeterReading.meter_id == meters_b["load"].id)
        )
        assert before_site_b_max == (stale_end - timedelta(seconds=INTERVAL_SECONDS)).replace(tzinfo=None)

        result = service.backfill_customer_data_to_now(customer)
        assert result is not None
        assert result.sites_processed == 1

        after_site_b_max = db.scalar(
            select(func.max(CoreTsMeterReading.ts)).where(CoreTsMeterReading.meter_id == meters_b["load"].id)
        )
        assert after_site_b_max == (current_end - timedelta(seconds=INTERVAL_SECONDS)).replace(tzinfo=None)
    finally:
        db.close()


def test_backfill_is_idempotent_when_called_twice_for_same_customer() -> None:
    testing_session_local = _setup_test_db()
    db = testing_session_local()
    try:
        service = EnergyService(db)
        customer = _create_customer(db, email="idempotent@example.com")
        site = _create_site(db, customer.id, "idempotent-site")
        meters = {role: _create_meter(db, site.id, role) for role in METER_TYPES}

        end_ts = service._round_to_interval(datetime.now(timezone.utc))
        start_ts = end_ts - timedelta(hours=2)
        quality_flag_id = _ensure_quality_flag(db)
        initial_readings = service._build_readings(customer.id, site.id, meters, quality_flag_id, start_ts, end_ts)
        service._insert_readings(initial_readings)
        db.commit()

        stale_cutoff = end_ts - timedelta(hours=1)
        db.query(CoreTsMeterReading).filter(
            CoreTsMeterReading.meter_id.in_([meter.id for meter in meters.values()]),
            CoreTsMeterReading.ts >= stale_cutoff,
        ).delete(synchronize_session=False)
        db.commit()

        before_count = db.query(CoreTsMeterReading).filter(CoreTsMeterReading.meter_id.in_([meter.id for meter in meters.values()])).count()

        first_result = service.backfill_customer_data_to_now(customer)
        after_first_count = db.query(CoreTsMeterReading).filter(CoreTsMeterReading.meter_id.in_([meter.id for meter in meters.values()])).count()

        second_result = service.backfill_customer_data_to_now(customer)
        after_second_count = db.query(CoreTsMeterReading).filter(CoreTsMeterReading.meter_id.in_([meter.id for meter in meters.values()])).count()

        assert first_result is not None
        assert first_result.readings_created == after_first_count - before_count
        assert second_result is None
        assert after_second_count == after_first_count
    finally:
        db.close()
