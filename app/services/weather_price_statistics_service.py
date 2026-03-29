from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from app.repositories.weather_price_analysis_repository import WeatherPriceAnalysisRepository
from app.schemas.weather_price_analysis import WeatherPriceAnalysisRequest
from app.schemas.weather_price_statistics import WeatherPriceStatisticsRequest, WeatherPriceStatisticsResponse
from app.services.weather_price_analysis_service import (
    AnalysisNotFoundError,
    AnalysisValidationError,
    WeatherPriceAnalysisService,
)


class StatisticsInputError(ValueError):
    pass


class StatisticsNotEnoughDataError(ValueError):
    pass


class StatisticsDataNotFoundError(LookupError):
    pass


@dataclass(frozen=True)
class _MetricPair:
    key: str
    metric_col: str


class WeatherPriceStatisticsService:
    MIN_REQUIRED_ROWS = 10

    METRICS = [
        "temp_c_weighted",
        "wind_ms_weighted",
        "ghi_wm2_weighted",
        "cloud_pct_weighted",
        "price_eur_mwh",
    ]

    WEATHER_METRICS = [
        "temp_c_weighted",
        "wind_ms_weighted",
        "ghi_wm2_weighted",
        "cloud_pct_weighted",
    ]

    CORRELATION_PAIRS = [
        _MetricPair("temp_vs_price", "temp_c_weighted"),
        _MetricPair("wind_vs_price", "wind_ms_weighted"),
        _MetricPair("ghi_vs_price", "ghi_wm2_weighted"),
        _MetricPair("cloud_vs_price", "cloud_pct_weighted"),
    ]

    LAG_PAIRS = [
        _MetricPair("temp_vs_price", "temp_c_weighted"),
        _MetricPair("wind_vs_price", "wind_ms_weighted"),
        _MetricPair("ghi_vs_price", "ghi_wm2_weighted"),
    ]

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = WeatherPriceAnalysisRepository(db)
        self.analysis_service = WeatherPriceAnalysisService(db)

    def analyze(self, payload: WeatherPriceStatisticsRequest) -> WeatherPriceStatisticsResponse:
        if payload.analysis_run_id is not None:
            run = self.repository.get_run(payload.analysis_run_id)
            if run is None:
                raise AnalysisNotFoundError(f"Analysis run {payload.analysis_run_id} not found")
            rows = self.repository.get_analysis_rows(payload.analysis_run_id)
            analysis_run_id = payload.analysis_run_id
            run_name = run.run_name
        else:
            analysis_payload = WeatherPriceAnalysisRequest(
                run_name="statistics-analysis",
                start_date=payload.start_date,
                end_date=payload.end_date,
                bidding_zone_id=payload.bidding_zone_id,
                product_id=payload.product_id,
                price_type=payload.price_type,
                cities=payload.cities or [],
            )
            try:
                analysis_response = self.analysis_service.execute(analysis_payload)
            except AnalysisValidationError as exc:
                raise StatisticsInputError(str(exc)) from exc
            rows = analysis_response.data
            analysis_run_id = analysis_response.analysis_run_id
            run_name = analysis_response.run_name

        if not rows:
            raise StatisticsDataNotFoundError("No linked weather-price rows found for this selection")

        df = pd.DataFrame(
            [
                {
                    "ts_utc": row.ts_utc,
                    "temp_c_weighted": row.temp_c_weighted,
                    "wind_ms_weighted": row.wind_ms_weighted,
                    "ghi_wm2_weighted": row.ghi_wm2_weighted,
                    "cloud_pct_weighted": row.cloud_pct_weighted,
                    "price_eur_mwh": row.price_eur_mwh,
                }
                for row in rows
            ]
        )
        df["ts_utc"] = pd.to_datetime(df["ts_utc"], utc=True)
        for column in self.METRICS:
            df[column] = pd.to_numeric(df[column], errors="coerce")

        # Price-null rows are excluded globally for all analyses.
        df = df[df["price_eur_mwh"].notna()].copy()

        if len(df) < self.MIN_REQUIRED_ROWS:
            raise StatisticsNotEnoughDataError(
                f"At least {self.MIN_REQUIRED_ROWS} non-null price rows are required; found {len(df)}"
            )

        df = df.sort_values("ts_utc").reset_index(drop=True)

        descriptive = self._descriptive_statistics(df)
        correlations = self._correlations(df)
        correlation_matrix = self._correlation_matrix(df)
        bucket_analysis = self._bucket_analysis(df)
        scatter_data = self._scatter_data(df)
        lag_analysis = self._lag_analysis(df)
        outliers = self._outliers(df)
        trend_lines = self._trend_lines(df)
        interpretation_hints = self._interpretation_hints(correlations, lag_analysis)

        return WeatherPriceStatisticsResponse(
            meta={
                "analysis_run_id": analysis_run_id,
                "run_name": run_name,
                "row_count": int(len(df)),
                "time_range": {
                    "start": df["ts_utc"].min().to_pydatetime() if not df.empty else None,
                    "end": df["ts_utc"].max().to_pydatetime() if not df.empty else None,
                },
            },
            descriptive_statistics=descriptive,
            correlations=correlations,
            correlation_matrix=correlation_matrix,
            bucket_analysis=bucket_analysis,
            scatter_data=scatter_data,
            lag_analysis=lag_analysis,
            interpretation_hints=interpretation_hints,
            outliers=outliers,
            trend_lines=trend_lines,
        )

    def _descriptive_statistics(self, df: pd.DataFrame) -> dict:
        result: dict[str, dict] = {}
        for col in self.METRICS:
            series = df[col].dropna()
            result[col] = {
                "count": int(series.count()),
                "min": _to_float(series.min()),
                "max": _to_float(series.max()),
                "mean": _to_float(series.mean()),
                "median": _to_float(series.median()),
                "std": _to_float(series.std(ddof=1)),
            }
        return result

    def _correlations(self, df: pd.DataFrame) -> dict[str, float | None]:
        result: dict[str, float | None] = {}
        for pair in self.CORRELATION_PAIRS:
            subset = df[[pair.metric_col, "price_eur_mwh"]].dropna()
            result[pair.key] = _to_float(subset[pair.metric_col].corr(subset["price_eur_mwh"], method="pearson"))
        return result

    def _correlation_matrix(self, df: pd.DataFrame) -> dict:
        columns = [*self.WEATHER_METRICS, "price_eur_mwh"]
        corr = df[columns].corr(method="pearson")
        values = [[_to_float(corr.loc[row, col]) for col in columns] for row in columns]
        return {"columns": columns, "values": values}

    def _bucket_analysis(self, df: pd.DataFrame) -> dict[str, list[dict]]:
        return {
            "temperature": self._single_bucket(df, "temp_c_weighted", "price_eur_mwh", bin_size=5),
            "wind": self._single_bucket(df, "wind_ms_weighted", "price_eur_mwh", bin_size=2),
            "ghi": self._ghi_buckets(df),
        }

    def _single_bucket(self, df: pd.DataFrame, metric_col: str, price_col: str, bin_size: int) -> list[dict]:
        subset = df[[metric_col, price_col]].dropna()
        if subset.empty:
            return []
        min_val = np.floor(subset[metric_col].min() / bin_size) * bin_size
        max_val = np.ceil(subset[metric_col].max() / bin_size) * bin_size + bin_size
        bins = np.arange(min_val, max_val + bin_size, bin_size)

        subset = subset.assign(
            bucket=pd.cut(subset[metric_col], bins=bins, right=False, include_lowest=True)
        )
        grouped = subset.groupby("bucket", observed=False)[price_col]
        output = []
        for interval, group in grouped:
            if len(group) == 0:
                continue
            output.append(
                {
                    "bucket": f"{float(interval.left):g} to {float(interval.right):g}",
                    "count": int(group.count()),
                    "avg_price": _to_float(group.mean()),
                    "min_price": _to_float(group.min()),
                    "max_price": _to_float(group.max()),
                }
            )
        return output

    def _ghi_buckets(self, df: pd.DataFrame) -> list[dict]:
        subset = df[["ghi_wm2_weighted", "price_eur_mwh"]].dropna()
        if subset.empty:
            return []

        bins = [-0.001, 50, 150, 300, 500, 800, np.inf]
        labels = ["0 to 50", "50 to 150", "150 to 300", "300 to 500", "500 to 800", "800+"]
        subset = subset.assign(
            bucket=pd.cut(subset["ghi_wm2_weighted"], bins=bins, labels=labels, include_lowest=True)
        )
        grouped = subset.groupby("bucket", observed=False)["price_eur_mwh"]
        output = []
        for label, group in grouped:
            if len(group) == 0:
                continue
            output.append(
                {
                    "bucket": str(label),
                    "count": int(group.count()),
                    "avg_price": _to_float(group.mean()),
                    "min_price": _to_float(group.min()),
                    "max_price": _to_float(group.max()),
                }
            )
        return output

    def _scatter_data(self, df: pd.DataFrame) -> dict[str, list[dict]]:
        result: dict[str, list[dict]] = {}
        for pair in self.CORRELATION_PAIRS:
            subset = df[["ts_utc", pair.metric_col, "price_eur_mwh"]].dropna()
            result[pair.key] = [
                {"x": float(row[pair.metric_col]), "y": float(row["price_eur_mwh"]), "ts_utc": row["ts_utc"]}
                for _, row in subset.iterrows()
            ]
        return result

    def _lag_analysis(self, df: pd.DataFrame) -> dict[str, list[dict]]:
        result: dict[str, list[dict]] = {}
        for pair in self.LAG_PAIRS:
            lag_points = []
            for lag in range(4):
                shifted = df["price_eur_mwh"].shift(-lag)
                subset = pd.DataFrame({pair.metric_col: df[pair.metric_col], "price_shifted": shifted}).dropna()
                lag_points.append(
                    {
                        "lag_hours": lag,
                        "correlation": _to_float(subset[pair.metric_col].corr(subset["price_shifted"])),
                    }
                )
            result[pair.key] = lag_points
        return result

    def _outliers(self, df: pd.DataFrame) -> list[dict]:
        series = df["price_eur_mwh"].dropna()
        std = series.std(ddof=1)
        if pd.isna(std) or std == 0:
            return []
        z = (series - series.mean()) / std
        outlier_idx = z.abs().sort_values(ascending=False).head(5).index
        output = []
        for idx in outlier_idx:
            if abs(z.loc[idx]) < 2.5:
                continue
            output.append(
                {
                    "ts_utc": df.loc[idx, "ts_utc"],
                    "price_eur_mwh": float(df.loc[idx, "price_eur_mwh"]),
                    "z_score": float(z.loc[idx]),
                }
            )
        return output

    def _trend_lines(self, df: pd.DataFrame) -> dict[str, dict]:
        output: dict[str, dict] = {}
        for pair in self.CORRELATION_PAIRS[:3]:
            subset = df[[pair.metric_col, "price_eur_mwh"]].dropna()
            if len(subset) < 2:
                output[pair.key] = {"slope": None, "intercept": None}
                continue
            slope, intercept = np.polyfit(subset[pair.metric_col].to_numpy(), subset["price_eur_mwh"].to_numpy(), 1)
            output[pair.key] = {"slope": float(slope), "intercept": float(intercept)}
        return output

    def _interpretation_hints(self, correlations: dict[str, float | None], lag_analysis: dict[str, list[dict]]) -> list[str]:
        hints = [
            "Correlations summarize linear co-movement and should be interpreted carefully.",
            "Correlation does not imply causation; market fundamentals and seasonality may drive both weather and price.",
        ]

        strongest_key = None
        strongest_value = 0.0
        for key, value in correlations.items():
            if value is None:
                continue
            if abs(value) > abs(strongest_value):
                strongest_key = key
                strongest_value = value

        if strongest_key is not None and abs(strongest_value) >= 0.2:
            direction = "negative" if strongest_value < 0 else "positive"
            hints.append(
                f"{strongest_key.replace('_', ' ')} shows a {direction} correlation and may indicate useful operational patterns."
            )

        for key, values in lag_analysis.items():
            valid = [item for item in values if item["correlation"] is not None]
            if not valid:
                continue
            best = max(valid, key=lambda item: abs(item["correlation"]))
            if best["lag_hours"] > 0:
                hints.append(
                    f"For {key.replace('_', ' ')}, the strongest observed correlation appears at +{best['lag_hours']}h lag."
                )
                break

        hints.append("Bucket averages may indicate non-linear patterns that a single correlation value can miss.")
        return hints[:5]


def _to_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, (float, int)):
        if np.isnan(value):
            return None
        return float(value)
    try:
        as_float = float(value)
        if np.isnan(as_float):
            return None
        return as_float
    except (TypeError, ValueError):
        return None
