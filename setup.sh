#!/usr/bin/env bash

set -e  # stoppt bei Fehlern

python3 -m venv .venv
source .venv/bin/activate

pip install --upgrade pip
pip install -r requirements.txt

cp .env.example .env

python3 -m alembic upgrade head

python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000