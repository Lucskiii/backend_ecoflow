-- ============================================================
-- EcoFlow Energy (VPP/BI) – Datenmodell
-- MySQL 8 Version
-- Layering über Tabellenpräfixe: raw_, core_, bi_
-- ============================================================

CREATE DATABASE IF NOT EXISTS energy_db;
USE energy_db;

-- ============================================================
-- RAW / STAGING
-- ============================================================

CREATE TABLE IF NOT EXISTS raw_ingestion_batch (
  ingestion_batch_id BIGINT AUTO_INCREMENT PRIMARY KEY,
  source_system      VARCHAR(100) NOT NULL,
  fetched_at_utc     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  payload_format     VARCHAR(20) NOT NULL,
  source_uri         TEXT NULL,
  checksum           VARCHAR(255) NULL,
  notes              TEXT NULL
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS raw_raw_payload (
  raw_payload_id      BIGINT AUTO_INCREMENT PRIMARY KEY,
  ingestion_batch_id  BIGINT NOT NULL,
  entity_hint         VARCHAR(100) NULL,
  received_at_utc     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  payload             LONGBLOB NOT NULL,
  CONSTRAINT fk_raw_payload_batch
    FOREIGN KEY (ingestion_batch_id)
    REFERENCES raw_ingestion_batch(ingestion_batch_id)
    ON DELETE CASCADE
) ENGINE=InnoDB;

-- ============================================================
-- CORE / REFERENCE
-- ============================================================

CREATE TABLE IF NOT EXISTS core_bidding_zone (
  bidding_zone_id BIGINT AUTO_INCREMENT PRIMARY KEY,
  code            VARCHAR(50) NOT NULL,
  country         VARCHAR(100) NOT NULL,
  CONSTRAINT uq_core_bidding_zone_code UNIQUE (code)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS core_grid_zone (
  grid_zone_id BIGINT AUTO_INCREMENT PRIMARY KEY,
  tso_name     VARCHAR(255) NOT NULL,
  country      VARCHAR(100) NOT NULL
) ENGINE=InnoDB;

-- ============================================================
-- CORE / MASTER DATA
-- ============================================================

CREATE TABLE IF NOT EXISTS core_customer (
  customer_id   BIGINT AUTO_INCREMENT PRIMARY KEY,
  customer_type VARCHAR(20) NOT NULL,
  created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT chk_core_customer_type
    CHECK (customer_type IN ('household','sme','industrial'))
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS core_site (
  site_id          BIGINT AUTO_INCREMENT PRIMARY KEY,
  customer_id      BIGINT NOT NULL,
  address_hash     VARCHAR(255) NULL,
  country          VARCHAR(100) NOT NULL,
  zip              VARCHAR(20) NULL,
  lat              DECIMAL(9,6) NULL,
  lon              DECIMAL(9,6) NULL,
  bidding_zone_id  BIGINT NULL,
  grid_zone_id     BIGINT NULL,
  CONSTRAINT fk_core_site_customer
    FOREIGN KEY (customer_id)
    REFERENCES core_customer(customer_id)
    ON DELETE RESTRICT,
  CONSTRAINT fk_core_site_bidding_zone
    FOREIGN KEY (bidding_zone_id)
    REFERENCES core_bidding_zone(bidding_zone_id)
    ON DELETE SET NULL,
  CONSTRAINT fk_core_site_grid_zone
    FOREIGN KEY (grid_zone_id)
    REFERENCES core_grid_zone(grid_zone_id)
    ON DELETE SET NULL
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS core_asset (
  asset_id         BIGINT AUTO_INCREMENT PRIMARY KEY,
  site_id          BIGINT NOT NULL,
  asset_type       VARCHAR(20) NOT NULL,
  manufacturer     VARCHAR(255) NULL,
  model            VARCHAR(255) NULL,
  commissioned_at  DATE NULL,
  status           VARCHAR(20) NOT NULL DEFAULT 'active',
  CONSTRAINT fk_core_asset_site
    FOREIGN KEY (site_id)
    REFERENCES core_site(site_id)
    ON DELETE CASCADE,
  CONSTRAINT chk_core_asset_type
    CHECK (asset_type IN ('PV','BATTERY','EV','HEATPUMP','WIND','OTHER')),
  CONSTRAINT chk_core_asset_status
    CHECK (status IN ('active','inactive'))
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS core_asset_capability (
  asset_id               BIGINT PRIMARY KEY,
  p_max_kw               DECIMAL(12,3) NULL,
  p_min_kw               DECIMAL(12,3) NULL,
  energy_capacity_kwh    DECIMAL(12,3) NULL,
  ramp_rate_kw_per_min   DECIMAL(12,3) NULL,
  response_time_s        INT NULL,
  efficiency_roundtrip   DECIMAL(6,4) NULL,
  flex_window_min        INT NULL,
  CONSTRAINT fk_core_asset_capability_asset
    FOREIGN KEY (asset_id)
    REFERENCES core_asset(asset_id)
    ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS core_meter (
  meter_id          BIGINT AUTO_INCREMENT PRIMARY KEY,
  site_id           BIGINT NOT NULL,
  meter_type        VARCHAR(30) NOT NULL,
  interval_minutes  INT NOT NULL,
  timezone          VARCHAR(100) NOT NULL DEFAULT 'UTC',
  CONSTRAINT fk_core_meter_site
    FOREIGN KEY (site_id)
    REFERENCES core_site(site_id)
    ON DELETE CASCADE,
  CONSTRAINT chk_core_meter_type
    CHECK (meter_type IN ('grid_import','grid_export','pv_generation','load','battery_power','battery_energy','other')),
  CONSTRAINT chk_core_meter_interval
    CHECK (interval_minutes IN (1,5,10,15,30,60))
) ENGINE=InnoDB;

-- ============================================================
-- CORE / QUALITY FLAGS
-- ============================================================

CREATE TABLE IF NOT EXISTS core_quality_flag (
  quality_flag VARCHAR(20) PRIMARY KEY,
  description  VARCHAR(255) NULL
) ENGINE=InnoDB;

INSERT INTO core_quality_flag (quality_flag, description)
VALUES
  ('measured','Measured by device/meter'),
  ('estimated','Estimated or modeled value'),
  ('missing','Missing value / gap'),
  ('invalid','Invalid/outlier value')
ON DUPLICATE KEY UPDATE description = VALUES(description);

-- ============================================================
-- CORE / TIME SERIES
-- ============================================================

CREATE TABLE IF NOT EXISTS core_ts_meter_reading (
  meter_id             BIGINT NOT NULL,
  ts_utc               DATETIME NOT NULL,
  value                DECIMAL(18,6) NOT NULL,
  unit                 VARCHAR(20) NOT NULL,
  quality_flag         VARCHAR(20) NOT NULL,
  ingestion_batch_id   BIGINT NULL,
  PRIMARY KEY (meter_id, ts_utc),
  CONSTRAINT fk_core_ts_meter_reading_meter
    FOREIGN KEY (meter_id)
    REFERENCES core_meter(meter_id)
    ON DELETE CASCADE,
  CONSTRAINT fk_core_ts_meter_reading_quality
    FOREIGN KEY (quality_flag)
    REFERENCES core_quality_flag(quality_flag),
  CONSTRAINT fk_core_ts_meter_reading_batch
    FOREIGN KEY (ingestion_batch_id)
    REFERENCES raw_ingestion_batch(ingestion_batch_id)
    ON DELETE SET NULL
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS core_ts_asset_telemetry (
  asset_id             BIGINT NOT NULL,
  ts_utc               DATETIME NOT NULL,
  soc_pct              DECIMAL(6,3) NULL,
  power_kw             DECIMAL(12,3) NULL,
  state                VARCHAR(20) NULL,
  temperature_c        DECIMAL(8,3) NULL,
  quality_flag         VARCHAR(20) NOT NULL,
  ingestion_batch_id   BIGINT NULL,
  PRIMARY KEY (asset_id, ts_utc),
  CONSTRAINT fk_core_ts_asset_telemetry_asset
    FOREIGN KEY (asset_id)
    REFERENCES core_asset(asset_id)
    ON DELETE CASCADE,
  CONSTRAINT fk_core_ts_asset_telemetry_quality
    FOREIGN KEY (quality_flag)
    REFERENCES core_quality_flag(quality_flag),
  CONSTRAINT fk_core_ts_asset_telemetry_batch
    FOREIGN KEY (ingestion_batch_id)
    REFERENCES raw_ingestion_batch(ingestion_batch_id)
    ON DELETE SET NULL,
  CONSTRAINT chk_core_ts_asset_telemetry_state
    CHECK (state IN ('charging','discharging','idle','unknown') OR state IS NULL)
) ENGINE=InnoDB;

-- ============================================================
-- CORE / WEATHER & FORECAST
-- ============================================================

CREATE TABLE IF NOT EXISTS core_weather_location (
  weather_loc_id BIGINT AUTO_INCREMENT PRIMARY KEY,
  lat            DECIMAL(9,6) NOT NULL,
  lon            DECIMAL(9,6) NOT NULL,
  provider       VARCHAR(100) NOT NULL,
  model_name     VARCHAR(100) NULL,
  created_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS core_ts_weather_observation (
  weather_loc_id       BIGINT NOT NULL,
  ts_utc               DATETIME NOT NULL,
  temp_c               DECIMAL(8,3) NULL,
  wind_ms              DECIMAL(8,3) NULL,
  ghi_wm2              DECIMAL(10,3) NULL,
  cloud_pct            DECIMAL(6,3) NULL,
  quality_flag         VARCHAR(20) NOT NULL,
  ingestion_batch_id   BIGINT NULL,
  PRIMARY KEY (weather_loc_id, ts_utc),
  CONSTRAINT fk_core_ts_weather_observation_loc
    FOREIGN KEY (weather_loc_id)
    REFERENCES core_weather_location(weather_loc_id)
    ON DELETE CASCADE,
  CONSTRAINT fk_core_ts_weather_observation_quality
    FOREIGN KEY (quality_flag)
    REFERENCES core_quality_flag(quality_flag),
  CONSTRAINT fk_core_ts_weather_observation_batch
    FOREIGN KEY (ingestion_batch_id)
    REFERENCES raw_ingestion_batch(ingestion_batch_id)
    ON DELETE SET NULL
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS core_ts_forecast (
  forecast_id          BIGINT AUTO_INCREMENT PRIMARY KEY,
  site_id              BIGINT NULL,
  bidding_zone_id      BIGINT NULL,
  forecast_type        VARCHAR(20) NOT NULL,
  run_ts_utc           DATETIME NOT NULL,
  target_ts_utc        DATETIME NOT NULL,
  horizon_min          INT NOT NULL,
  value                DECIMAL(18,6) NOT NULL,
  unit                 VARCHAR(20) NOT NULL,
  model_version        VARCHAR(100) NULL,
  quality_flag         VARCHAR(20) NOT NULL,
  ingestion_batch_id   BIGINT NULL,

  site_scope_id BIGINT GENERATED ALWAYS AS (IFNULL(site_id, -1)) STORED,
  bidding_zone_scope_id BIGINT GENERATED ALWAYS AS (IFNULL(bidding_zone_id, -1)) STORED,
  model_version_scope VARCHAR(100) GENERATED ALWAYS AS (IFNULL(model_version, '__NULL__')) STORED,

  CONSTRAINT fk_core_ts_forecast_site
    FOREIGN KEY (site_id)
    REFERENCES core_site(site_id)
    ON DELETE CASCADE,
  CONSTRAINT fk_core_ts_forecast_bidding_zone
    FOREIGN KEY (bidding_zone_id)
    REFERENCES core_bidding_zone(bidding_zone_id)
    ON DELETE CASCADE,
  CONSTRAINT fk_core_ts_forecast_quality
    FOREIGN KEY (quality_flag)
    REFERENCES core_quality_flag(quality_flag),
  CONSTRAINT fk_core_ts_forecast_batch
    FOREIGN KEY (ingestion_batch_id)
    REFERENCES raw_ingestion_batch(ingestion_batch_id)
    ON DELETE SET NULL,
  CONSTRAINT chk_core_ts_forecast_type
    CHECK (forecast_type IN ('load','pv','wind','price','co2')),
  CONSTRAINT chk_core_ts_forecast_horizon
    CHECK (horizon_min >= 0),
  CONSTRAINT chk_core_ts_forecast_scope
    CHECK (site_id IS NOT NULL OR bidding_zone_id IS NOT NULL),
  CONSTRAINT uq_core_ts_forecast_dedup
    UNIQUE (
      site_scope_id,
      bidding_zone_scope_id,
      forecast_type,
      run_ts_utc,
      target_ts_utc,
      horizon_min,
      model_version_scope
    )
) ENGINE=InnoDB;

-- ============================================================
-- CORE / MARKET DATA
-- ============================================================

CREATE TABLE IF NOT EXISTS core_market (
  market_id    BIGINT AUTO_INCREMENT PRIMARY KEY,
  market_name  VARCHAR(100) NOT NULL,
  market_type  VARCHAR(20) NOT NULL,
  currency     VARCHAR(10) NOT NULL DEFAULT 'EUR',
  CONSTRAINT chk_core_market_type
    CHECK (market_type IN ('DAY_AHEAD','INTRADAY','BALANCING'))
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS core_market_product (
  product_id                 BIGINT AUTO_INCREMENT PRIMARY KEY,
  market_id                  BIGINT NOT NULL,
  product_code               VARCHAR(100) NOT NULL,
  delivery_granularity_min   INT NOT NULL,
  bidding_zone_id            BIGINT NULL,

  bidding_zone_scope_id BIGINT GENERATED ALWAYS AS (IFNULL(bidding_zone_id, -1)) STORED,

  CONSTRAINT fk_core_market_product_market
    FOREIGN KEY (market_id)
    REFERENCES core_market(market_id)
    ON DELETE CASCADE,
  CONSTRAINT fk_core_market_product_bidding_zone
    FOREIGN KEY (bidding_zone_id)
    REFERENCES core_bidding_zone(bidding_zone_id)
    ON DELETE SET NULL,
  CONSTRAINT chk_core_market_product_granularity
    CHECK (delivery_granularity_min IN (15,30,60)),
  CONSTRAINT uq_core_market_product
    UNIQUE (market_id, product_code, bidding_zone_scope_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS core_ts_market_price (
  product_id            BIGINT NOT NULL,
  ts_utc                DATETIME NOT NULL,
  price_eur_mwh         DECIMAL(18,6) NOT NULL,
  price_type            VARCHAR(20) NOT NULL,
  source                VARCHAR(100) NOT NULL,
  quality_flag          VARCHAR(20) NOT NULL,
  ingestion_batch_id    BIGINT NULL,
  PRIMARY KEY (product_id, ts_utc, price_type),
  CONSTRAINT fk_core_ts_market_price_product
    FOREIGN KEY (product_id)
    REFERENCES core_market_product(product_id)
    ON DELETE CASCADE,
  CONSTRAINT fk_core_ts_market_price_quality
    FOREIGN KEY (quality_flag)
    REFERENCES core_quality_flag(quality_flag),
  CONSTRAINT fk_core_ts_market_price_batch
    FOREIGN KEY (ingestion_batch_id)
    REFERENCES raw_ingestion_batch(ingestion_batch_id)
    ON DELETE SET NULL,
  CONSTRAINT chk_core_ts_market_price_type
    CHECK (price_type IN ('settlement','last','index'))
) ENGINE=InnoDB;

-- ============================================================
-- CORE / GRID EVENTS
-- ============================================================

CREATE TABLE IF NOT EXISTS core_grid_event (
  grid_event_id      BIGINT AUTO_INCREMENT PRIMARY KEY,
  grid_zone_id       BIGINT NULL,
  bidding_zone_id    BIGINT NULL,
  ts_start_utc       DATETIME NOT NULL,
  ts_end_utc         DATETIME NOT NULL,
  event_type         VARCHAR(30) NOT NULL,
  severity           INT NULL,
  metadata_json      JSON NULL,
  CONSTRAINT fk_core_grid_event_grid_zone
    FOREIGN KEY (grid_zone_id)
    REFERENCES core_grid_zone(grid_zone_id)
    ON DELETE SET NULL,
  CONSTRAINT fk_core_grid_event_bidding_zone
    FOREIGN KEY (bidding_zone_id)
    REFERENCES core_bidding_zone(bidding_zone_id)
    ON DELETE SET NULL,
  CONSTRAINT chk_core_grid_event_scope
    CHECK (grid_zone_id IS NOT NULL OR bidding_zone_id IS NOT NULL),
  CONSTRAINT chk_core_grid_event_time
    CHECK (ts_end_utc > ts_start_utc),
  CONSTRAINT chk_core_grid_event_type
    CHECK (event_type IN ('congestion','redispatch','frequency_event','outage'))
) ENGINE=InnoDB;

-- ============================================================
-- CORE / DISPATCH
-- ============================================================

CREATE TABLE IF NOT EXISTS core_dispatch_plan (
  dispatch_id       BIGINT AUTO_INCREMENT PRIMARY KEY,
  site_id           BIGINT NULL,
  asset_id          BIGINT NULL,
  created_ts_utc    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  strategy          VARCHAR(30) NOT NULL,
  status            VARCHAR(20) NOT NULL,
  CONSTRAINT fk_core_dispatch_plan_site
    FOREIGN KEY (site_id)
    REFERENCES core_site(site_id)
    ON DELETE CASCADE,
  CONSTRAINT fk_core_dispatch_plan_asset
    FOREIGN KEY (asset_id)
    REFERENCES core_asset(asset_id)
    ON DELETE CASCADE,
  CONSTRAINT chk_core_dispatch_plan_scope
    CHECK (site_id IS NOT NULL OR asset_id IS NOT NULL),
  CONSTRAINT chk_core_dispatch_plan_strategy
    CHECK (strategy IN ('price_arbitrage','grid_support','co2_opt','other')),
  CONSTRAINT chk_core_dispatch_plan_status
    CHECK (status IN ('planned','executed','cancelled'))
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS core_dispatch_step (
  dispatch_id         BIGINT NOT NULL,
  ts_utc              DATETIME NOT NULL,
  setpoint_kw         DECIMAL(12,3) NOT NULL,
  constraint_reason   VARCHAR(255) NULL,
  PRIMARY KEY (dispatch_id, ts_utc),
  CONSTRAINT fk_core_dispatch_step_plan
    FOREIGN KEY (dispatch_id)
    REFERENCES core_dispatch_plan(dispatch_id)
    ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS core_dispatch_execution (
  dispatch_id    BIGINT NOT NULL,
  ts_utc         DATETIME NOT NULL,
  actual_kw      DECIMAL(12,3) NULL,
  deviation_kw   DECIMAL(12,3) NULL,
  PRIMARY KEY (dispatch_id, ts_utc),
  CONSTRAINT fk_core_dispatch_execution_plan
    FOREIGN KEY (dispatch_id)
    REFERENCES core_dispatch_plan(dispatch_id)
    ON DELETE CASCADE
) ENGINE=InnoDB;

-- ============================================================
-- CORE / CONTRACTS & SETTLEMENT
-- ============================================================

CREATE TABLE IF NOT EXISTS core_contract (
  contract_id         BIGINT AUTO_INCREMENT PRIMARY KEY,
  customer_id         BIGINT NOT NULL,
  tariff_type         VARCHAR(20) NOT NULL,
  revenue_share_pct   DECIMAL(6,3) NULL,
  valid_from          DATE NOT NULL,
  valid_to            DATE NULL,
  CONSTRAINT fk_core_contract_customer
    FOREIGN KEY (customer_id)
    REFERENCES core_customer(customer_id)
    ON DELETE CASCADE,
  CONSTRAINT chk_core_contract_tariff_type
    CHECK (tariff_type IN ('fixed','dynamic','revenue_share')),
  CONSTRAINT chk_core_contract_rev_share
    CHECK (
      tariff_type <> 'revenue_share'
      OR (revenue_share_pct IS NOT NULL AND revenue_share_pct BETWEEN 0 AND 100)
    ),
  CONSTRAINT chk_core_contract_dates
    CHECK (valid_to IS NULL OR valid_to >= valid_from)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS core_settlement_statement (
  settlement_id      BIGINT AUTO_INCREMENT PRIMARY KEY,
  customer_id        BIGINT NOT NULL,
  period_start_utc   DATETIME NOT NULL,
  period_end_utc     DATETIME NOT NULL,
  revenue_eur        DECIMAL(18,6) NOT NULL DEFAULT 0,
  cost_eur           DECIMAL(18,6) NOT NULL DEFAULT 0,
  net_eur            DECIMAL(18,6) NOT NULL DEFAULT 0,
  details_json       JSON NULL,
  created_at         TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_core_settlement_statement_customer
    FOREIGN KEY (customer_id)
    REFERENCES core_customer(customer_id)
    ON DELETE CASCADE,
  CONSTRAINT chk_core_settlement_statement_period
    CHECK (period_end_utc > period_start_utc)
) ENGINE=InnoDB;

-- ============================================================
-- BI / DIMENSIONS
-- ============================================================

CREATE TABLE IF NOT EXISTS bi_dim_time (
  time_id       BIGINT PRIMARY KEY,
  ts_utc        DATETIME NOT NULL,
  date_utc      DATE NOT NULL,
  hour_utc      SMALLINT NOT NULL,
  minute_utc    SMALLINT NOT NULL,
  week_utc      SMALLINT NULL,
  month_utc     SMALLINT NULL,
  year_utc      SMALLINT NULL,
  is_weekend    BOOLEAN NOT NULL DEFAULT FALSE,
  is_holiday    BOOLEAN NOT NULL DEFAULT FALSE,
  CONSTRAINT chk_bi_dim_time_hour
    CHECK (hour_utc BETWEEN 0 AND 23),
  CONSTRAINT chk_bi_dim_time_minute
    CHECK (minute_utc IN (0,1,2,3,4,5,10,15,20,30,45)),
  CONSTRAINT chk_bi_dim_time_month
    CHECK (month_utc BETWEEN 1 AND 12 OR month_utc IS NULL)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS bi_dim_customer (
  customer_id    BIGINT PRIMARY KEY,
  customer_type  VARCHAR(20) NOT NULL,
  segment        VARCHAR(50) NULL
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS bi_dim_site (
  site_id          BIGINT PRIMARY KEY,
  customer_id      BIGINT NOT NULL,
  bidding_zone_id  BIGINT NULL,
  grid_zone_id     BIGINT NULL,
  zip              VARCHAR(20) NULL,
  country          VARCHAR(100) NOT NULL
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS bi_dim_asset (
  asset_id        BIGINT PRIMARY KEY,
  site_id         BIGINT NOT NULL,
  asset_type      VARCHAR(20) NOT NULL,
  manufacturer    VARCHAR(255) NULL,
  model           VARCHAR(255) NULL,
  capacity_kwh    DECIMAL(12,3) NULL,
  p_max_kw        DECIMAL(12,3) NULL
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS bi_dim_market_product (
  product_id                 BIGINT PRIMARY KEY,
  market_type               VARCHAR(20) NOT NULL,
  product_code              VARCHAR(100) NOT NULL,
  delivery_granularity_min  INT NOT NULL
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS bi_dim_quality (
  quality_id    SMALLINT AUTO_INCREMENT PRIMARY KEY,
  quality_flag  VARCHAR(20) NOT NULL,
  CONSTRAINT uq_bi_dim_quality_flag UNIQUE (quality_flag)
) ENGINE=InnoDB;

-- ============================================================
-- BI / FACTS
-- ============================================================

CREATE TABLE IF NOT EXISTS bi_fact_energy_interval (
  time_id                 BIGINT NOT NULL,
  site_id                 BIGINT NOT NULL,
  quality_id              SMALLINT NULL,
  grid_import_kwh         DECIMAL(18,6) NOT NULL DEFAULT 0,
  grid_export_kwh         DECIMAL(18,6) NOT NULL DEFAULT 0,
  load_kwh                DECIMAL(18,6) NOT NULL DEFAULT 0,
  pv_gen_kwh              DECIMAL(18,6) NOT NULL DEFAULT 0,
  battery_charge_kwh      DECIMAL(18,6) NOT NULL DEFAULT 0,
  battery_discharge_kwh   DECIMAL(18,6) NOT NULL DEFAULT 0,
  soc_avg_pct             DECIMAL(6,3) NULL,
  PRIMARY KEY (time_id, site_id),
  CONSTRAINT fk_bi_fact_energy_interval_time
    FOREIGN KEY (time_id)
    REFERENCES bi_dim_time(time_id)
    ON DELETE RESTRICT,
  CONSTRAINT fk_bi_fact_energy_interval_site
    FOREIGN KEY (site_id)
    REFERENCES bi_dim_site(site_id)
    ON DELETE CASCADE,
  CONSTRAINT fk_bi_fact_energy_interval_quality
    FOREIGN KEY (quality_id)
    REFERENCES bi_dim_quality(quality_id)
    ON DELETE SET NULL
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS bi_fact_market_price (
  time_id        BIGINT NOT NULL,
  product_id     BIGINT NOT NULL,
  price_eur_mwh  DECIMAL(18,6) NOT NULL,
  PRIMARY KEY (time_id, product_id),
  CONSTRAINT fk_bi_fact_market_price_time
    FOREIGN KEY (time_id)
    REFERENCES bi_dim_time(time_id)
    ON DELETE RESTRICT,
  CONSTRAINT fk_bi_fact_market_price_product
    FOREIGN KEY (product_id)
    REFERENCES bi_dim_market_product(product_id)
    ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS bi_fact_dispatch (
  time_id          BIGINT NOT NULL,
  asset_id         BIGINT NOT NULL,
  setpoint_kw      DECIMAL(12,3) NULL,
  actual_kw        DECIMAL(12,3) NULL,
  deviation_kw     DECIMAL(12,3) NULL,
  curtailment_kw   DECIMAL(12,3) NULL,
  strategy         VARCHAR(30) NULL,
  dispatch_status  VARCHAR(20) NULL,
  PRIMARY KEY (time_id, asset_id),
  CONSTRAINT fk_bi_fact_dispatch_time
    FOREIGN KEY (time_id)
    REFERENCES bi_dim_time(time_id)
    ON DELETE RESTRICT,
  CONSTRAINT fk_bi_fact_dispatch_asset
    FOREIGN KEY (asset_id)
    REFERENCES bi_dim_asset(asset_id)
    ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS bi_fact_forecast_accuracy (
  time_id         BIGINT NOT NULL,
  site_id         BIGINT NOT NULL,
  forecast_type   VARCHAR(20) NOT NULL,
  horizon_min     INT NOT NULL,
  forecast_value  DECIMAL(18,6) NOT NULL,
  actual_value    DECIMAL(18,6) NOT NULL,
  abs_error       DECIMAL(18,6) NOT NULL,
  mape            DECIMAL(18,6) NULL,
  PRIMARY KEY (time_id, site_id, forecast_type, horizon_min),
  CONSTRAINT fk_bi_fact_forecast_accuracy_time
    FOREIGN KEY (time_id)
    REFERENCES bi_dim_time(time_id)
    ON DELETE RESTRICT,
  CONSTRAINT fk_bi_fact_forecast_accuracy_site
    FOREIGN KEY (site_id)
    REFERENCES bi_dim_site(site_id)
    ON DELETE CASCADE,
  CONSTRAINT chk_bi_fact_forecast_accuracy_type
    CHECK (forecast_type IN ('load','pv','wind','price','co2')),
  CONSTRAINT chk_bi_fact_forecast_accuracy_horizon
    CHECK (horizon_min >= 0)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS bi_fact_settlement (
  period_start_time_id  BIGINT NOT NULL,
  customer_id           BIGINT NOT NULL,
  revenue_eur           DECIMAL(18,6) NOT NULL DEFAULT 0,
  cost_eur              DECIMAL(18,6) NOT NULL DEFAULT 0,
  net_eur               DECIMAL(18,6) NOT NULL DEFAULT 0,
  PRIMARY KEY (period_start_time_id, customer_id),
  CONSTRAINT fk_bi_fact_settlement_time
    FOREIGN KEY (period_start_time_id)
    REFERENCES bi_dim_time(time_id)
    ON DELETE RESTRICT,
  CONSTRAINT fk_bi_fact_settlement_customer
    FOREIGN KEY (customer_id)
    REFERENCES bi_dim_customer(customer_id)
    ON DELETE CASCADE
) ENGINE=InnoDB;

-- ============================================================
-- INDEXES
-- ============================================================

CREATE INDEX ix_core_ts_meter_reading_ts
  ON core_ts_meter_reading (ts_utc);

CREATE INDEX ix_core_ts_asset_telemetry_ts
  ON core_ts_asset_telemetry (ts_utc);

CREATE INDEX ix_core_ts_market_price_ts
  ON core_ts_market_price (ts_utc);

CREATE INDEX ix_core_ts_weather_observation_ts
  ON core_ts_weather_observation (ts_utc);

CREATE INDEX ix_core_grid_event_time
  ON core_grid_event (ts_start_utc, ts_end_utc);

CREATE INDEX ix_bi_fact_energy_interval_site
  ON bi_fact_energy_interval (site_id);

CREATE INDEX ix_bi_fact_market_price_product
  ON bi_fact_market_price (product_id);

-- ============================================================
-- VIEW
-- ============================================================

CREATE OR REPLACE VIEW core_v_site_customer AS
SELECT
  s.site_id,
  s.country,
  s.zip,
  s.lat,
  s.lon,
  s.bidding_zone_id,
  s.grid_zone_id,
  c.customer_id,
  c.customer_type,
  c.created_at AS customer_created_at
FROM core_site s
JOIN core_customer c
  ON c.customer_id = s.customer_id;