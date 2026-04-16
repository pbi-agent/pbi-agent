from __future__ import annotations

from typing import Annotated, Any, cast

from fastapi import Depends, Header, Path as FastAPIPath, Query, Request
from pydantic import BaseModel, StringConstraints

from pbi_agent.web.session_manager import WebSessionManager

NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
LimitQuery = Annotated[int, Query(ge=1, le=200)]
MentionQuery = Annotated[str, Query(max_length=200)]
MentionLimitQuery = Annotated[int, Query(ge=1, le=50)]
LiveSessionIdPath = Annotated[
    str,
    FastAPIPath(min_length=1, description="The live session identifier."),
]
TaskIdPath = Annotated[
    str,
    FastAPIPath(min_length=1, description="The task identifier."),
]
StreamIdPath = Annotated[
    str,
    FastAPIPath(min_length=1, description="The event stream identifier."),
]
SessionIdPath = Annotated[
    str,
    FastAPIPath(min_length=1, description="The saved session identifier."),
]
RunSessionIdPath = Annotated[
    str,
    FastAPIPath(min_length=1, description="The observability run session identifier."),
]
UploadIdPath = Annotated[
    str,
    FastAPIPath(min_length=1, description="The uploaded image identifier."),
]
ConfigRevisionHeader = Annotated[str, Header(alias="If-Match", min_length=1)]


def get_session_manager(request: Request) -> WebSessionManager:
    return cast(WebSessionManager, request.app.state.manager)


SessionManagerDep = Annotated[WebSessionManager, Depends(get_session_manager)]


def model_from_payload[T: BaseModel](model_type: type[T], payload: Any) -> T:
    return model_type.model_validate(payload)
