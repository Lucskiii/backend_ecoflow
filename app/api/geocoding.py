from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.repositories.site_repository import SiteRepository
from app.services.geocoding_service import GeocodingService

router = APIRouter(prefix="/api/geocode", tags=["geocoding"])


@router.post("/site/{site_id}")
def geocode_site(site_id: int, force: bool = Query(default=False), db: Session = Depends(get_db)) -> dict:
    service = GeocodingService(db)
    try:
        result = service.geocode_site(site_id, force=force)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "site_id": site_id,
        "latitude": str(result.latitude),
        "longitude": str(result.longitude),
        "force": force,
    }


@router.post("/all-sites")
def geocode_all_sites(force: bool = Query(default=False), db: Session = Depends(get_db)) -> dict:
    repo = SiteRepository(db)
    service = GeocodingService(db)
    sites = repo.list_all_sites() if force else repo.list_sites_without_coordinates()

    geocoded = 0
    failures: list[dict[str, str | int]] = []
    for site in sites:
        try:
            service.geocode_site(site.id, force=force)
            geocoded += 1
        except Exception as exc:
            failures.append({"site_id": site.id, "error": str(exc)})

    return {"total": len(sites), "geocoded": geocoded, "failed": len(failures), "failures": failures}
