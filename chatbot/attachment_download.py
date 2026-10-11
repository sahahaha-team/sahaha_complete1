"""Safe direct downloads for attachments hosted by the official Saha website."""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from urllib.parse import unquote, urljoin, urlparse

import requests

from chatbot.reference_answers import safe_official_link


MAX_ATTACHMENT_BYTES = 25 * 1024 * 1024
ALLOWED_MEDIA_TYPES = {
    ".pdf": "application/pdf",
    ".hwp": "application/x-hwp",
    ".hwpx": "application/vnd.hancom.hwpx",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".ppt": "application/vnd.ms-powerpoint",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".zip": "application/zip",
}


def _extension(url: str) -> str:
    return PurePosixPath(unquote(urlparse(url).path)).suffix.lower()


def _filename(label: str, url: str) -> str:
    extension = _extension(url)
    fallback = PurePosixPath(unquote(urlparse(url).path)).name or f"attachment{extension}"
    value = (label or fallback).strip()
    value = re.sub(r"[\\/:*?\"<>|\r\n]", "_", value).strip(" .")
    if not value:
        value = f"attachment{extension}"
    if extension and not value.lower().endswith(extension):
        value += extension
    return value[:180]


def fetch_official_attachment(url: str, label: str = "첨부파일") -> tuple[bytes, str, str]:
    """Fetch a bounded official attachment without allowing an open proxy/SSRF."""
    if not safe_official_link(url) or _extension(url) not in ALLOWED_MEDIA_TYPES:
        raise ValueError("허용되지 않은 첨부파일 주소입니다.")

    current = url
    response = None
    try:
        for _ in range(4):
            response = requests.get(
                current,
                headers={"User-Agent": "SahaAI-AttachmentDownload/1.0"},
                timeout=(5, 20),
                stream=True,
                allow_redirects=False,
            )
            if response.status_code in {301, 302, 303, 307, 308}:
                location = response.headers.get("Location", "")
                response.close()
                response = None
                current = urljoin(current, location)
                if not safe_official_link(current):
                    raise ValueError("공식 사이트 밖으로 이동하는 첨부파일입니다.")
                continue
            break
        else:
            raise ValueError("첨부파일 이동 횟수가 너무 많습니다.")

        if response is None:
            raise ValueError("첨부파일을 불러오지 못했습니다.")
        response.raise_for_status()
        extension = _extension(current)
        if extension not in ALLOWED_MEDIA_TYPES:
            raise ValueError("허용되지 않은 첨부파일 형식입니다.")
        content_type = (response.headers.get("Content-Type") or "").lower()
        if "text/html" in content_type:
            raise ValueError("파일 대신 웹페이지가 반환되었습니다.")
        length = response.headers.get("Content-Length")
        if length and int(length) > MAX_ATTACHMENT_BYTES:
            raise ValueError("첨부파일 크기가 25MB를 초과합니다.")

        chunks = []
        total = 0
        for chunk in response.iter_content(chunk_size=64 * 1024):
            if not chunk:
                continue
            total += len(chunk)
            if total > MAX_ATTACHMENT_BYTES:
                raise ValueError("첨부파일 크기가 25MB를 초과합니다.")
            chunks.append(chunk)
        if not chunks:
            raise ValueError("비어 있는 첨부파일입니다.")
        return b"".join(chunks), ALLOWED_MEDIA_TYPES[extension], _filename(label, current)
    finally:
        if response is not None:
            response.close()
