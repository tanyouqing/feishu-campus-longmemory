from __future__ import annotations

import secrets

from fastapi import Request
from starlette import status

from feishu_campus_longmemory.config import Settings
from feishu_campus_longmemory.errors import AppError


def _extract_bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token


def require_ingest_token(request: Request) -> None:
    settings: Settings = request.app.state.settings
    expected_token = settings.ingest_token
    if not expected_token:
        raise AppError(
            code="ingest_token_not_configured",
            message="LONGMEMORY_INGEST_TOKEN must be configured before using event ingestion or evidence query APIs",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    provided_token = (
        _extract_bearer_token(request.headers.get("authorization"))
        or request.headers.get("x-longmemory-ingest-token")
    )
    if not provided_token or not secrets.compare_digest(provided_token, expected_token):
        raise AppError(
            code="unauthorized",
            message="A valid ingest token is required",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

