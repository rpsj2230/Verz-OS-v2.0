"""The company logo: an upload behind the setup code, and the image served to the console.

`POST /setup/logo` is the wizard's upload (M42.5.5). It is asked for in the order every setup
route asks: the store and the code first, one refusal for a wrong code, a finished install and an
install with no code (`brain.setup_staff_routes.assert_setup_open`), and only then is the body
looked at. It writes one file and nothing else. `GET /brand/logo` serves it, with no sign-in,
because the console's sign-in page draws it too.

**What is served cannot be run.** `X-Content-Type-Options: nosniff`, a content security policy that
allows nothing, and the media type read from the bytes by `brain.branding.read` every time, so a
file placed by hand is held to the upload's rule. See `brain.branding` for why an SVG is refused.

Task ids: M42.5.5
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Final

import structlog
from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from brain.api import COMMON_RESPONSES, NoEchoRoute
from brain.branding import LOGO_PATH, MAX_LOGO_BYTES, LogoRefusedError, from_base64, keep, read
from brain.core.errors import Absent
from brain.setup_routes import draft_file_of
from brain.setup_staff_routes import assert_setup_open
from brain.setup_wizard import MAX_ANSWER_CHARS

log = structlog.get_logger()

#: Where the upload is made.
UPLOAD_PATH: Final = "/setup/logo"

#: The most base64 characters a body may carry, which is `MAX_LOGO_BYTES` and a third again.
MAX_BASE64_CHARS: Final = (MAX_LOGO_BYTES * 4) // 3 + 8


class LogoAsked(BaseModel):
    """The setup code and the image, as base64 text."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    setup_code: str = Field(max_length=MAX_ANSWER_CHARS)
    image: str = Field(max_length=MAX_BASE64_CHARS)


class LogoKeptView(BaseModel):
    """What was kept: its kind and size, and where the console will draw it from."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    media_type: str
    bytes_kept: int
    path: str


class LogoRefusedView(BaseModel):
    """Why the file could not be kept, in a sentence."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    problem: str


router = APIRouter(tags=["setup"], route_class=NoEchoRoute)

_TOLD: Final[dict[int | str, dict[str, object]]] = {
    **COMMON_RESPONSES,
    422: {"model": LogoRefusedView, "description": "Why the file cannot be used."},
}


def logo_directory_of(request: Request) -> Path:
    """The directory the logo is kept in: beside the wizard's draft."""
    return draft_file_of(request).parent


@router.post(UPLOAD_PATH, response_model=LogoKeptView, responses=_TOLD)
async def upload_logo(request: Request, body: LogoAsked) -> JSONResponse:
    """Keep the logo the setup code's holder chose, or say why it cannot be used."""
    await assert_setup_open(request, body.setup_code, datetime.now(UTC))
    try:
        logo = from_base64(body.image)
        keep(logo_directory_of(request), logo)
    except LogoRefusedError as why:
        told = LogoRefusedView(problem=str(why))
        return JSONResponse(status_code=422, content=told.model_dump())
    log.info("logo kept", media_type=logo.media_type, size=len(logo.data))
    kept = LogoKeptView(media_type=logo.media_type, bytes_kept=len(logo.data), path=LOGO_PATH)
    return JSONResponse(status_code=200, content=kept.model_dump())


@router.get(LOGO_PATH, responses={200: {"content": {"image/*": {}}}, **COMMON_RESPONSES})
async def served_logo(request: Request) -> Response:
    """The uploaded logo, or the one refusal when there is none."""
    logo = read(logo_directory_of(request))
    if logo is None:
        raise Absent("no logo has been uploaded")
    return Response(
        content=logo.data,
        media_type=logo.media_type,
        headers={
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; sandbox",
            "Cache-Control": "public, max-age=300",
        },
    )
