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


## Weather ingestion

- The backend ingests hourly weather history from Open-Meteo using site coordinates stored in `core_site`.
- Historical backfills use the Open-Meteo archive API, while recent catch-up syncs can use the forecast API with `past_days` to cover the newest hours when archive data lags.
- Data is stored in `core_weather_location`, `core_ts_weather_observation`, `raw_ingestion_batch`, and optionally `raw_raw_payload`.
- Weather observations are written idempotently by `weather_loc_id + ts_utc`, so reruns only fill missing rows or refresh the latest modeled values.

### Weather scheduler

- The weather scheduler runs in a background thread on API startup and checks each coordinate-bearing site for missing hourly data.
- Configure the behavior with:
  - `WEATHER_SCHEDULER_ENABLED`
  - `WEATHER_SCHEDULER_INTERVAL_MINUTES`
  - `WEATHER_DEFAULT_BACKFILL_DAYS`
  - `WEATHER_RECENT_DAYS_WINDOW`
  - `OPEN_METEO_HISTORICAL_URL`
  - `OPEN_METEO_FORECAST_URL`
- The scheduler is non-blocking and skips duplicate thread startup when the app reloads.

### Manual weather operations

- `POST /api/weather/backfill/site/{site_id}` optionally accepts `start_date` and `end_date` query parameters in `YYYY-MM-DD` format.
- `POST /api/weather/backfill/all` backfills all sites with valid coordinates.
- `POST /api/weather/sync` fetches only missing data from the latest stored timestamp through the newest available UTC date.
- `GET /api/weather/status` reports scheduler configuration and per-site latest stored timestamps.
