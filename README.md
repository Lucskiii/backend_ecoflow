# EcoFlow Backend Foundation

Clean backend starter for an energy analytics / virtual power plant platform with a full MySQL 8 schema managed by Alembic migrations.

## Stack

- FastAPI (REST API)
- MySQL + PyMySQL
- SQLAlchemy 2.x ORM
- Alembic migrations
- Pydantic schemas
- python-dotenv for environment variables

## Project layout

```text
app/
  main.py
  config.py
  database.py
  api/
  models/
  schemas/
  repositories/
  services/
migrations/
tests/
```

## Quick start
## Mit bash ist unter Windows PowerShell gemeint

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Set environment variables:
   ```bash
   cp .env.example .env
   ```
3. Run migrations:
   ```bash
   python -m alembic upgrade head
   ```
4. Start API:
   ```bash
   python -m uvicorn app.main:app --reload
   ```

## Endpoints

- `GET /health` - service health check
- `GET /api/customers`
- `GET /api/customers/{customer_id}`
- `POST /api/customers`
- `PUT /api/customers/{customer_id}`
- `DELETE /api/customers/{customer_id}`


## Database foundation

- The database is managed via Alembic migrations only (no `Base.metadata.create_all()` in app startup).
- Logical layers are represented as MySQL table prefixes: `raw_`, `core_`, and `bi_`.
- Run `python -m alembic upgrade head` to create all tables, constraints, and indexes in MySQL 8.
- Configure your connection in `.env` using `DATABASE_URL` (example provided in `.env.example`).

## Simulated daily consumption

The backend now maintains a customer-level daily energy summary table (`core_daily_consumption`).

- When the consumption daily endpoint is called with `auto_generate=true` (default), the backend first checks whether data exists up to today.
- Missing days are simulated and inserted only for gaps between the latest available date and today.
- Existing rows are never regenerated, and `(customer_id, consumption_date)` is unique to prevent duplicates.
- For new customers with no data, the service initializes the last 90 days plus today.
- Each daily row now includes: `consumption_kwh`, `grid_import_kwh`, `grid_export_kwh`, `pv_generation_kwh`, and `self_consumption_share_pct`.

### Consumption endpoints

- `GET /api/customers/{customer_id}/consumption/daily`
  - Query params: `start_date`, `end_date`, `auto_generate`
  - Defaults to last 90 days when no date range is provided
- `POST /api/customers/{customer_id}/consumption/simulate`
  - Manually triggers missing day simulation up to today
- `GET /api/customers/{customer_id}/consumption/status`
  - Returns latest available date and whether days are missing through today
