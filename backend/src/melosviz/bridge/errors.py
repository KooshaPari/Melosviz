"""RFC 7807-ish problem+json helpers for the MelosViz bridge."""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse


def problem(
    *,
    status: int,
    title: str,
    detail: str,
    type_: str = "about:blank",
    instance: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "type": type_,
        "title": title,
        "status": status,
        "detail": detail,
    }
    if instance:
        body["instance"] = instance
    if extra:
        body.update(extra)
    return body


async def http_exception_problem(request: Request, exc: Exception) -> JSONResponse:
    """Render FastAPI HTTPException as application/problem+json."""
    from fastapi import HTTPException

    if not isinstance(exc, HTTPException):
        raise exc
    detail = exc.detail
    if isinstance(detail, dict):
        payload = detail
        status = int(payload.get("status", exc.status_code))
    else:
        title = {
            400: "Bad Request",
            401: "Unauthorized",
            403: "Forbidden",
            404: "Not Found",
            413: "Payload Too Large",
            429: "Too Many Requests",
            503: "Service Unavailable",
        }.get(exc.status_code, "Error")
        payload = problem(
            status=exc.status_code,
            title=title,
            detail=str(detail),
            type_=f"https://melosviz.dev/problems/{exc.status_code}",
            instance=str(request.url.path),
        )
        status = exc.status_code
    headers = dict(exc.headers) if exc.headers else None
    return JSONResponse(
        status_code=status,
        content=payload,
        media_type="application/problem+json",
        headers=headers,
    )
