from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from fastapi.testclient import TestClient

from app.main import app
from app.models.tables import CoreDailyConsumption
from app.services.consumption_simulation_service import ConsumptionSimulationService


class _StubCustomerRepository:
    def __init__(self, customer_exists: bool = True):
        self.customer_exists = customer_exists

    def get(self, customer_id: int):
        if not self.customer_exists:
            return None
        return type("Customer", (), {"id": customer_id})()


class _InMemoryConsumptionRepository:
    def __init__(self):
        self.rows: dict[tuple[int, date], CoreDailyConsumption] = {}

    def get_latest_consumption_date(self, customer_id: int) -> date | None:
        dates = [d for (cid, d) in self.rows if cid == customer_id]
        return max(dates) if dates else None

    def exists_for_date(self, customer_id: int, consumption_date: date) -> bool:
        return (customer_id, consumption_date) in self.rows

    def bulk_insert(self, rows: list[CoreDailyConsumption]) -> int:
        for row in rows:
            self.rows[(row.customer_id, row.consumption_date)] = row
        return len(rows)

    def list_by_customer_and_range(self, customer_id: int, start_date: date, end_date: date):
        return [
            row
            for (cid, day), row in sorted(self.rows.items(), key=lambda item: item[0][1])
            if cid == customer_id and start_date <= day <= end_date
        ]


def _service_with_stubs() -> ConsumptionSimulationService:
    service = ConsumptionSimulationService(db=None)  # type: ignore[arg-type]
    service.customer_repository = _StubCustomerRepository()
    service.consumption_repository = _InMemoryConsumptionRepository()
    return service


def test_first_generation_for_new_customer() -> None:
    service = _service_with_stubs()
    created = service.ensure_customer_consumption_data(1)
    assert created == 91


def test_repeated_generation_does_not_create_duplicates() -> None:
    service = _service_with_stubs()
    first = service.ensure_customer_consumption_data(1)
    second = service.ensure_customer_consumption_data(1)

    assert first == 91
    assert second == 0


def test_generation_fills_only_missing_days() -> None:
    service = _service_with_stubs()
    today = date.today()
    existing_day = today - timedelta(days=3)
    service.consumption_repository.rows[(1, existing_day)] = CoreDailyConsumption(
        customer_id=1,
        consumption_date=existing_day,
        consumption_kwh=Decimal("10.000"),
        source_type="simulated",
    )

    created = service.ensure_customer_consumption_data(1)
    assert created == 3


def test_get_daily_endpoint_returns_generated_data() -> None:
    client = TestClient(app)

    def _fake_ensure(self, customer_id: int) -> int:
        return 2

    def _fake_list(self, customer_id: int, start_date: date, end_date: date):
        return [
            CoreDailyConsumption(
                consumption_id=1,
                customer_id=customer_id,
                consumption_date=end_date - timedelta(days=1),
                consumption_kwh=Decimal("8.125"),
                source_type="simulated",
                created_at=datetime.now(timezone.utc)
            ),
            CoreDailyConsumption(
                consumption_id=2,
                customer_id=customer_id,
                consumption_date=end_date,
                consumption_kwh=Decimal("9.200"),
                source_type="simulated",
                created_at=datetime.now(timezone.utc)
            ),
        ]

    original_ensure = ConsumptionSimulationService.ensure_customer_consumption_data
    original_list = ConsumptionSimulationService.list_consumption
    try:
        ConsumptionSimulationService.ensure_customer_consumption_data = _fake_ensure  # type: ignore[assignment]
        ConsumptionSimulationService.list_consumption = _fake_list  # type: ignore[assignment]

        response = client.get("/api/customers/1/consumption/daily")
        assert response.status_code == 200
        payload = response.json()
        assert len(payload) == 2
        assert payload[-1]["consumption_kwh"] == "9.200"
    finally:
        ConsumptionSimulationService.ensure_customer_consumption_data = original_ensure
        ConsumptionSimulationService.list_consumption = original_list
