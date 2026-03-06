# EcoFlow Backend Foundation

Clean backend starter for an energy analytics / virtual power plant platform.

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
