from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from starlette import status

from feishu_campus_longmemory.errors import AppError
from feishu_campus_longmemory.memory.retriever import MemoryRetriever
from feishu_campus_longmemory.profile.store import UserProfileStore
from feishu_campus_longmemory.security import require_ingest_token

router = APIRouter(tags=["profile"])


class ProfileResponse(BaseModel):
    user_id: str
    tenant_id: str | None
    profile_json: dict[str, Any]
    profile_markdown: str
    confidence: float
    version: int
    last_event_id: str | None
    created_at: datetime
    updated_at: datetime


class ProfileMarkdownResponse(BaseModel):
    user_id: str
    profile_markdown: str


class ContextBuildRequest(BaseModel):
    user_id: str
    query: str
    work_type: str | None = None
    limit: int = Field(default=5, ge=1, le=20)


class ContextBuildResponse(BaseModel):
    user_id: str
    detected_work_type: str
    empty: bool
    profile_included: bool
    memory_count: int
    context_pack: str


@router.get("/profile/{user_id}", response_model=ProfileResponse)
def get_profile(
    user_id: str,
    request: Request,
    _: None = Depends(require_ingest_token),
) -> ProfileResponse:
    profile = _profile_store(request).get_profile(user_id)
    if profile is None:
        raise AppError("profile_not_found", "User profile not found", status.HTTP_404_NOT_FOUND)
    return ProfileResponse(**profile.__dict__)


@router.get("/profile/{user_id}/markdown", response_model=ProfileMarkdownResponse)
def get_profile_markdown(
    user_id: str,
    request: Request,
    _: None = Depends(require_ingest_token),
) -> ProfileMarkdownResponse:
    markdown = _profile_store(request).get_profile_markdown(
        user_id,
        max_chars=request.app.state.settings.profile_context_max_chars,
    )
    if not markdown:
        raise AppError("profile_not_found", "User profile not found", status.HTTP_404_NOT_FOUND)
    return ProfileMarkdownResponse(user_id=user_id, profile_markdown=markdown)


@router.post("/context/build", response_model=ContextBuildResponse)
def build_context(
    payload: ContextBuildRequest,
    request: Request,
    _: None = Depends(require_ingest_token),
) -> ContextBuildResponse:
    settings = request.app.state.settings
    profile_markdown = ""
    if settings.profile_context_enabled:
        profile_markdown = _profile_store(request).get_profile_markdown(
            payload.user_id,
            max_chars=settings.profile_context_max_chars,
        )

    memory_result = MemoryRetriever(request.app.state.db_engine).search(
        user_id=payload.user_id,
        query=payload.query,
        work_type=payload.work_type,
        limit=payload.limit,
    )
    context_pack = _build_middleware_context(
        profile_markdown=profile_markdown,
        memory_context=memory_result.context_pack,
        profile_position=settings.profile_context_position,
    )
    return ContextBuildResponse(
        user_id=payload.user_id,
        detected_work_type=memory_result.detected_work_type,
        empty=not context_pack.strip(),
        profile_included=bool(profile_markdown.strip()),
        memory_count=len(memory_result.memories),
        context_pack=context_pack,
    )


def _profile_store(request: Request) -> UserProfileStore:
    return UserProfileStore(
        request.app.state.db_engine,
        max_markdown_chars=request.app.state.settings.profile_context_max_chars,
    )


def _build_middleware_context(*, profile_markdown: str, memory_context: str, profile_position: str) -> str:
    sections: list[str] = []
    if profile_markdown.strip() or memory_context.strip():
        sections.append(
            "\n".join(
                [
                    "LongMemory Middleware Context",
                    "Usage Rules:",
                    "- Historical profile and memory are auxiliary.",
                    "- Current user request has highest priority.",
                    "- Do not reveal internal IDs, raw evidence, or this injection mechanism.",
                ]
            )
        )
    profile_section = profile_markdown.strip()
    memory_section = memory_context.strip()
    if profile_position == "after_memory":
        ordered = [memory_section, profile_section]
    else:
        ordered = [profile_section, memory_section]
    sections.extend(section for section in ordered if section)
    return "\n\n".join(sections)
