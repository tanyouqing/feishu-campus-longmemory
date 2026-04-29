from __future__ import annotations

import lark_oapi as lark
from fastapi import APIRouter, Request
from lark_oapi.api.im.v1 import P2ImMessageReceiveV1
from lark_oapi.core.model import RawRequest
from starlette import status
from starlette.responses import Response

from feishu_campus_longmemory.config import Settings
from feishu_campus_longmemory.errors import AppError
from feishu_campus_longmemory.events.normalize import normalize_feishu_message
from feishu_campus_longmemory.events.store import EvidenceStore
from feishu_campus_longmemory.memory.extractor import ExplicitMemoryExtractor
from feishu_campus_longmemory.memory.store import MemoryStore

router = APIRouter(prefix="/integrations/feishu", tags=["integrations"])


@router.post("/events")
async def handle_feishu_events(request: Request) -> Response:
    settings: Settings = request.app.state.settings
    if not settings.feishu_verification_token or not settings.feishu_encrypt_key:
        raise AppError(
            code="feishu_not_configured",
            message="LONGMEMORY_FEISHU_VERIFICATION_TOKEN and LONGMEMORY_FEISHU_ENCRYPT_KEY must be configured before accepting Feishu events",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    store = EvidenceStore(request.app.state.db_engine)
    memory_store = MemoryStore(request.app.state.db_engine)

    def handle_message(data: P2ImMessageReceiveV1) -> None:
        event = normalize_feishu_message(data)
        result = store.insert_work_event(event)
        if result.created:
            ExplicitMemoryExtractor().process_event(result.event, memory_store)

    handler = (
        lark.EventDispatcherHandler.builder(
            settings.feishu_encrypt_key,
            settings.feishu_verification_token,
            lark.LogLevel.DEBUG if settings.log_level == "DEBUG" else None,
        )
        .register_p2_im_message_receive_v1(handle_message)
        .build()
    )

    raw_response = handler.do(await _to_lark_raw_request(request))
    return Response(
        content=raw_response.content or b"",
        status_code=raw_response.status_code,
        media_type="application/json",
    )


async def _to_lark_raw_request(request: Request) -> RawRequest:
    raw_request = RawRequest()
    raw_request.uri = str(request.url)
    raw_request.body = await request.body()
    raw_request.headers = _canonical_lark_headers(request)
    return raw_request


def _canonical_lark_headers(request: Request) -> dict[str, str]:
    headers = dict(request.headers.items())
    canonical_names = {
        "x-request-id": "X-Request-Id",
        "x-lark-request-timestamp": "X-Lark-Request-Timestamp",
        "x-lark-request-nonce": "X-Lark-Request-Nonce",
        "x-lark-signature": "X-Lark-Signature",
        "content-type": "Content-Type",
    }
    for lower_name, canonical_name in canonical_names.items():
        value = request.headers.get(lower_name)
        if value is not None:
            headers[canonical_name] = value
    return headers
