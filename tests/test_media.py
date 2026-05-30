import pytest

from pbi_agent.media import detect_image_mime_type, load_image_bytes


@pytest.mark.parametrize(
    ("raw_bytes", "mime_type"),
    [
        (b"\x89PNG\r\n\x1a\nPNGDATA", "image/png"),
        (b"\xff\xd8\xffJPEGDATA", "image/jpeg"),
        (b"RIFF\x00\x00\x00\x00WEBPWEBPDATA", "image/webp"),
        (b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00heic", "image/heic"),
        (b"\x00\x00\x00\x18ftypmif1\x00\x00\x00\x00mif1", "image/heif"),
    ],
)
def test_detect_image_mime_type_matches_gemini_supported_formats(
    raw_bytes: bytes,
    mime_type: str,
) -> None:
    assert detect_image_mime_type(raw_bytes) == mime_type


def test_load_image_bytes_accepts_heif_family_images() -> None:
    raw_bytes = b"\x00\x00\x00\x18ftypheix\x00\x00\x00\x00mif1"

    image = load_image_bytes("photo.heic", raw_bytes)

    assert image.path == "photo.heic"
    assert image.mime_type == "image/heic"
    assert image.byte_count == len(raw_bytes)
