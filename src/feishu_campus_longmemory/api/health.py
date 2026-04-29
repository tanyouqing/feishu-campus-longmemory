from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel
from starlette import status

from feishu_campus_longmemory.db import check_database
from feishu_campus_longmemory.errors import AppError

router = APIRouter(tags=["system"])


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    database: str


@router.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    try:
        check_database(request.app.state.db_engine)
    except Exception as exc:
        raise AppError(
            code="database_unavailable",
            message="Database is not available",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        ) from exc

    settings = request.app.state.settings
    return HealthResponse(
        status="ok",
        service=settings.service_name,
        version=settings.version,
        database="ok",
    )

