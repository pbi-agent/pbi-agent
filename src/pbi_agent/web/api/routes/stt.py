from __future__ import annotations

from dataclasses import dataclass
from email import policy
from email.parser import BytesParser
from typing import cast

from fastapi import APIRouter, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from pbi_agent.stt import SttError, SttInputError, local, transcribe_wav_bytes
from pbi_agent.web.api.schemas.stt import (
    LocalSttStatusResponse,
    SttTranscriptionResponse,
)

router = APIRouter(prefix="/api/stt", tags=["stt"])


@dataclass(frozen=True, slots=True)
class _UploadedFile:
    filename: str
    content_type: str
    content: bytes


@router.post("/transcribe", response_model=SttTranscriptionResponse)
async def transcribe_stt(request: Request) -> SttTranscriptionResponse:
    try:
        upload = await _read_single_file_upload(request)
        text = await run_in_threadpool(transcribe_wav_bytes, upload.content)
    except SttError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return SttTranscriptionResponse(text=text)


@router.get("/local", response_model=LocalSttStatusResponse)
def get_local_stt_status() -> LocalSttStatusResponse:
    return _local_status_response()


@router.post("/local/download", response_model=LocalSttStatusResponse)
def download_local_stt() -> LocalSttStatusResponse:
    local.start_download()
    return _local_status_response()


def _local_status_response() -> LocalSttStatusResponse:
    current = local.status()
    return LocalSttStatusResponse(
        state=current.state,
        downloaded_bytes=current.downloaded_bytes,
        total_bytes=current.total_bytes,
        error=current.error,
    )


async def _read_single_file_upload(request: Request) -> _UploadedFile:
    content_type = request.headers.get("content-type", "")
    if "multipart/form-data" not in content_type.lower():
        raise SttInputError("Expected multipart/form-data with one 'file' field.")
    body = await request.body()
    if not body:
        raise SttInputError("Multipart upload body is empty.")

    message_bytes = (
        f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode() + body
    )
    try:
        message = BytesParser(policy=policy.default).parsebytes(message_bytes)
    except Exception as exc:
        raise SttInputError("Could not parse multipart upload.") from exc
    if not message.is_multipart():
        raise SttInputError("Expected multipart/form-data with one 'file' field.")

    parts = [part for part in message.iter_parts() if not part.is_multipart()]
    if len(parts) != 1:
        raise SttInputError("Expected exactly one multipart field named 'file'.")

    part = parts[0]
    field_name = part.get_param("name", header="content-disposition")
    filename = part.get_filename()
    if field_name != "file" or not filename:
        raise SttInputError("Expected exactly one multipart field named 'file'.")
    payload = cast(bytes | None, part.get_payload(decode=True))
    if payload is None:
        raise SttInputError("Uploaded file is empty.")
    return _UploadedFile(
        filename=filename,
        content_type=part.get_content_type(),
        content=payload,
    )
