from __future__ import annotations

from dataclasses import dataclass

import requests

from app.config import get_settings


@dataclass(slots=True)
class OpenCageClientError(Exception):
    message: str

    def __str__(self) -> str:
        return self.message


class OpenCageClient:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._session = requests.Session()

    def geocode_address(self, address: str) -> tuple[float, float]:
        params = {
            "q": address,
            "key": self.settings.opencage_api_key,
            "limit": 1,
            "no_annotations": 1,
        }

        try:
            response = self._session.get(
                self.settings.opencage_geocoding_url,
                params=params,
                timeout=self.settings.opencage_timeout_seconds,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise OpenCageClientError(f"OpenCage geocoding request failed: {exc}") from exc

        payload = response.json()
        status = payload.get("status") or {}
        code = int(status.get("code", 0)) if str(status.get("code", "")).isdigit() else 0
        if code == 402:
            raise OpenCageClientError("OpenCage geocoding quota exceeded")
        if code and code >= 400:
            raise OpenCageClientError(f"OpenCage geocoding error: {status.get('message', 'unknown error')}")

        results = payload.get("results") or []
        if not results:
            raise OpenCageClientError(f"No geocoding result for address: {address}")

        geometry = results[0].get("geometry") or {}
        lat = geometry.get("lat")
        lon = geometry.get("lng")
        if lat is None or lon is None:
            raise OpenCageClientError(f"Incomplete geocoding result for address: {address}")

        return float(lat), float(lon)
