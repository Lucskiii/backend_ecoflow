from __future__ import annotations

import logging
from datetime import datetime, time, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.tables import CoreBiddingZone
from app.repositories.analysis_city_repository import AnalysisCityRepository
from app.repositories.weather_price_analysis_repository import WeatherPriceAnalysisRepository
from app.schemas.weather_price_analysis import WeatherPriceAnalysisRequest, WeatherPriceAnalysisResponse
from app.services.analysis_city_weather_service import AnalysisCityWeatherService, WeatherUpstreamError
from app.services.weather_aggregation_service import WeatherAggregationService

logger = logging.getLogger(__name__)


class AnalysisValidationError(ValueError):
    pass


class AnalysisNotFoundError(LookupError):
    pass


class NoPriceDataError(LookupError):
    pass


class WeatherPriceAnalysisService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.city_repository = AnalysisCityRepository(db)
        self.weather_service = AnalysisCityWeatherService(db)
        self.aggregation_service = WeatherAggregationService(db)
        self.repository = WeatherPriceAnalysisRepository(db)

    def execute(self, payload: WeatherPriceAnalysisRequest) -> WeatherPriceAnalysisResponse:
        self._validate_request(payload)
        normalized_weights = self._normalized_weights(payload)
        city_ids = [item.analysis_city_id for item in payload.cities]

        run = self.repository.create_run(payload.start_date, payload.end_date, run_name=payload.run_name or "frontend-analysis")
        self.repository.add_run_cities(run.id, normalized_weights)
        self.repository.set_run_status(run.id, "running")

        start_ts = datetime.combine(payload.start_date, time.min)
        end_ts = datetime.combine(payload.end_date, time.min) + timedelta(hours=23)

        try:
            rows_inserted_weather = self.weather_service.ensure_weather_data_for_selected_cities(
                city_ids, payload.start_date, payload.end_date
            )
            rows_inserted_aggregate, aggregate_rows = self.aggregation_service.aggregate_and_store(
                run.id, normalized_weights, start_ts, end_ts
            )

            product_id = payload.product_id or self.repository.get_default_product_id_for_zone_and_range(
                payload.bidding_zone_id,
                start_ts,
                end_ts,
            )
            if product_id is None:
                product_id = self.repository.get_default_product_id()
            if product_id is None:
                raise NoPriceDataError("No market product found for price join")

            prices = self.repository.get_prices(
                start_ts,
                end_ts,
                product_id=product_id,
                bidding_zone_id=payload.bidding_zone_id,
            )
            if not prices:
                raise NoPriceDataError("No price data available for requested range")

            analysis_rows = []
            for row in aggregate_rows:
                ts_utc = row["ts_utc"]
                price = prices.get(ts_utc)
                if price is None:
                    continue
                analysis_rows.append(
                    {
                        "analysis_run_id": run.id,
                        "ts_utc": ts_utc,
                        "temp_c_weighted": row["temp_c_weighted"],
                        "wind_ms_weighted": row["wind_ms_weighted"],
                        "ghi_wm2_weighted": row["ghi_wm2_weighted"],
                        "cloud_pct_weighted": row["cloud_pct_weighted"],
                        "price_eur_mwh": price,
                        "product_id": product_id,
                        "price_type": payload.price_type or "spot",
                        "source_system": "analysis-pipeline",
                    }
                )

            rows_inserted_analysis = self.repository.bulk_upsert_analysis_rows(analysis_rows)
            self.repository.set_run_status(run.id, "completed")
            self.db.commit()
        except (AnalysisValidationError, NoPriceDataError, WeatherUpstreamError):
            self.db.rollback()
            raise
        except Exception:
            self.db.rollback()
            logger.exception("Weather price analysis failed")
            raise

        response_rows = self.repository.get_analysis_rows(run.id)
        return WeatherPriceAnalysisResponse(
            analysis_run_id=run.id,
            run_name=run.run_name,
            normalized_weights=[
                {"analysis_city_id": city_id, "weight": weight}
                for city_id, weight in normalized_weights.items()
            ],
            rows_inserted_weather=rows_inserted_weather,
            rows_inserted_aggregate=rows_inserted_aggregate,
            rows_inserted_analysis=rows_inserted_analysis,
            data=[
                {
                    "ts_utc": row.ts_utc,
                    "temp_c_weighted": row.temp_c_weighted,
                    "wind_ms_weighted": row.wind_ms_weighted,
                    "ghi_wm2_weighted": row.ghi_wm2_weighted,
                    "cloud_pct_weighted": row.cloud_pct_weighted,
                    "price_eur_mwh": row.price_eur_mwh,
                    "product_id": row.product_id,
                    "price_type": row.price_type,
                }
                for row in response_rows
            ],
        )

    def get_run_data(self, analysis_run_id: int) -> WeatherPriceAnalysisResponse:
        run = self.repository.get_run(analysis_run_id)
        if run is None:
            raise AnalysisNotFoundError(f"Analysis run {analysis_run_id} not found")
        rows = self.repository.get_analysis_rows(analysis_run_id)
        run_weights = self.repository.get_run_city_weights(analysis_run_id)
        return WeatherPriceAnalysisResponse(
            analysis_run_id=analysis_run_id,
            run_name=run.run_name,
            normalized_weights=[
                {"analysis_city_id": city_id, "weight": weight}
                for city_id, weight in run_weights.items()
            ],
            rows_inserted_weather=0,
            rows_inserted_aggregate=0,
            rows_inserted_analysis=len(rows),
            data=[
                {
                    "ts_utc": row.ts_utc,
                    "temp_c_weighted": row.temp_c_weighted,
                    "wind_ms_weighted": row.wind_ms_weighted,
                    "ghi_wm2_weighted": row.ghi_wm2_weighted,
                    "cloud_pct_weighted": row.cloud_pct_weighted,
                    "price_eur_mwh": row.price_eur_mwh,
                    "product_id": row.product_id,
                    "price_type": row.price_type,
                }
                for row in rows
            ],
        )

    def rename_run(self, analysis_run_id: int, run_name: str) -> dict:
        run = self.repository.set_run_name(analysis_run_id, run_name)
        if run is None:
            raise AnalysisNotFoundError(f"Analysis run {analysis_run_id} not found")
        self.db.commit()
        return {"analysis_run_id": run.id, "run_name": run.run_name}

    def get_status(self, analysis_run_id: int) -> dict:
        payload = self.repository.get_status_payload(analysis_run_id)
        if payload is None:
            raise AnalysisNotFoundError(f"Analysis run {analysis_run_id} not found")
        return payload

    def _validate_request(self, payload: WeatherPriceAnalysisRequest) -> None:
        if payload.start_date > payload.end_date:
            raise AnalysisValidationError("start_date must be before or equal to end_date")

        city_ids = [city.analysis_city_id for city in payload.cities]
        if len(city_ids) != len(set(city_ids)):
            raise AnalysisValidationError("duplicate city ids are not allowed")

        if self.db.get(CoreBiddingZone, payload.bidding_zone_id) is None:
            raise AnalysisNotFoundError(f"Bidding zone {payload.bidding_zone_id} does not exist")

        for city_id in city_ids:
            if self.city_repository.get_analysis_city_by_id(city_id) is None:
                raise AnalysisNotFoundError(f"Analysis city {city_id} does not exist")

    @staticmethod
    def _normalized_weights(payload: WeatherPriceAnalysisRequest) -> dict[int, Decimal]:
        total = sum(Decimal(str(city.weight)) for city in payload.cities)
        if total <= 0:
            raise AnalysisValidationError("weights must be positive")
        return {
            city.analysis_city_id: (Decimal(str(city.weight)) / total).quantize(Decimal("0.0001"))
            for city in payload.cities
        }
