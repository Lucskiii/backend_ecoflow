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
- `POST /api/geocode/site/{site_id}`
- `POST /api/geocode/all-sites`


## Database foundation

- The database is managed via Alembic migrations only (no `Base.metadata.create_all()` in app startup).
- Logical layers are represented as MySQL table prefixes: `raw_`, `core_`, and `bi_`.
- Run `python -m alembic upgrade head` to create all tables, constraints, and indexes in MySQL 8.
- After pulling new backend changes, run `python -m alembic upgrade head` before startup so new columns (e.g. customer address/geocoordinates) exist.
- Configure your connection in `.env` using `DATABASE_URL` (example provided in `.env.example`).



## Geocoding

- Address-to-coordinate resolution now uses the OpenCage Geocoding API (`https://api.opencagedata.com/geocode/v1/json`).
- Weather ingestion remains on Open-Meteo APIs; only address geocoding changed.
- Geocoding tries multiple address variants and stops at the first successful match:
  1. `address_line1, postal_code, city, country`
  2. `address_line1, city, country`
  3. `postal_code, city, country`
  4. `city, country`
- Existing site coordinates are not geocoded again unless the `force=true` query parameter is used.
- Relevant settings:
  - `OPENCAGE_API_KEY`
  - `OPENCAGE_GEOCODING_URL`
  - `OPENCAGE_TIMEOUT_SECONDS`

### Manual geocoding operations

- `POST /api/geocode/site/{site_id}` geocodes one site and stores coordinates in `core_site`.
- `POST /api/geocode/all-sites` geocodes all sites without coordinates (or all sites with `force=true`).

## Weather ingestion

- The backend ingests hourly weather history from Open-Meteo using site coordinates stored in `core_site`.
- Historical backfills use the Open-Meteo archive API, while recent catch-up syncs can use the forecast API with `past_days` to cover the newest hours when archive data lags.
- Data is stored in `core_weather_location`, `core_ts_weather_observation`, `raw_ingestion_batch`, and optionally `raw_raw_payload`.
- Weather observations are written idempotently by `weather_loc_id + ts_utc`, so reruns only fill missing rows or refresh the latest modeled values.

### Weather scheduler

- The weather scheduler runs in a background thread on API startup and checks each coordinate-bearing site for missing hourly data.
- On startup, customer addresses are geocoded and used to backfill missing `core_site.latitude/longitude` values for existing sites.
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

## One-time market price historical backfill

- Purpose: fill **missing older** rows in `core_ts_market_price` from the earliest stored timestamp backwards to a target date.
- This is a **manual one-time operation** and is **not** attached to startup or any scheduler.
- Idempotency: existing rows are preserved; only missing historical rows are inserted.

### Trigger endpoint

- `POST /api/market/backfill/historical`
- Query parameters:
  - `manual_run=true` (required guard)
  - `target_start_date=YYYY-MM-DD` (optional, defaults to `MARKET_PRICE_BACKFILL_DEFAULT_START_DATE`, default value `2025-03-26`)

Example:

```bash
curl -X POST "http://localhost:8000/api/market/backfill/historical?manual_run=true&target_start_date=2025-03-26"
```

The response includes processed/skipped/failed product counts, inserted row count, and effective backfill range metadata.

## Analysis cities (manual weather locations)

- Frontend users can create analysis cities via `POST /api/analysis-cities` by sending `city_name` and optional `country_code`.
- The backend resolves coordinates via the **Open-Meteo Geocoding API** (`/v1/search`) and stores the resolved city in a dedicated `core_analysis_city` table.
- If a city cannot be resolved, the API returns a user-friendly client error (no generic 500).

## Weighted weather-price analysis workflow

- Frontend sends `POST /analysis/weather-price` with `start_date`, `end_date`, optional `product_id` / `price_type`, and selected analysis cities including weights.
- Backend validates city ids, rejects duplicates, normalizes weights to sum `1.0`, and stores one analysis run (`core_weather_price_analysis_run`) with run-city mapping (`bi_weather_price_analysis_run_city`).
- Backend ensures hourly weather exists in `core_analysis_city_weather_observation` for each selected city:
  - Existing data is reused.
  - Only missing hourly timestamps are fetched from Open-Meteo.
  - Inserts are idempotent via unique key `(analysis_city_id, ts_utc)`.
- Backend performs weighted aggregation per timestamp into `core_weighted_weather_aggregate`.
  - Strategy: if a metric is missing for some cities at a timestamp, available city weights are re-normalized for that metric+timestamp.
- Backend joins weighted weather with `core_ts_market_price` on `ts_utc` and writes final BI rows into `bi_weather_price_analysis`.
- API response returns:
  - `analysis_run_id`
  - normalized weights actually used
  - inserted row counters
  - final joined dataset for direct frontend rendering.

Additional endpoints:
- `GET /api/analysis/weather-price/{analysis_run_id}` returns persisted result rows from `bi_weather_price_analysis` for frontend display.
- `GET /api/analysis/weather-price/{analysis_run_id}/status` returns run metadata and row counts.
- `PATCH /api/analysis/weather-price/{analysis_run_id}/name` renames an existing analysis run for frontend labeling.
