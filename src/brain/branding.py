"""A company's logo as a file it uploads in the setup wizard, checked and kept where the install
keeps its own files.

M42.5.5 says the company step takes a logo as an upload. It took an address (`INSTALL_LOGO_URL`)
and said so in a docstring, which meant a company without a place to host an image could not set
one. This is the upload, and the three decisions in it are the ones to read.

**The file is kept beside the wizard's draft and not in the database.** The wizard is reachable
while the first migration is still running and holds nothing else it needs a schema for, so a file
in the directory the installer owns (the draft's directory) has no dependency the draft does not
already have. It is not the object store, which the lite profile does not run, and it is not a
setting, because an installation value is a line a person edits and a logo is a hundred thousand
characters of base64 on a screen that lists every value. Rejected: a column. It is a migration for
one image, and a table that holds one image is a setting with extra steps.

**What is accepted is a raster image, identified by its first bytes and not by its name.** PNG,
JPEG, GIF and WebP. An SVG is refused, because an SVG is a document that can carry script and this
file is served from the install's own origin to every browser that opens the console: a scriptable
"logo" there is a stored cross-site-scripting hole with a friendly name. The kind is read from the
bytes each time the file is read as well as when it is written, so a file put in the directory by
hand is held to the same rule. A person with an SVG exports a PNG; the refusal says so.

**It is capped at 256 KiB.** A logo is drawn at about two rems high. A larger file is a photograph
or an export nobody optimised, and every console page load would carry it.

**An upload is not an installation value until an administrator exists.** The appointment is the
last write of the wizard, so the upload only puts the file down and the appointment points
`INSTALL_LOGO_URL` at `LOGO_PATH` when no address was given. An address the company chose wins, and
changing the address on the Settings screen later replaces the upload without a second place to
undo it.

Task ids: M42.5.5
"""

from __future__ import annotations

import binascii
import contextlib
import os
import tempfile
from base64 import b64decode
from dataclasses import dataclass
from pathlib import Path
from typing import Final

#: Where the console draws the uploaded logo from, a path on the install's own origin.
LOGO_PATH: Final = "/brand/logo"

#: The file's name in the directory beside the wizard's draft.
LOGO_FILE_NAME: Final = "company-logo"

#: The largest file accepted, in bytes. See the module note.
MAX_LOGO_BYTES: Final = 256 * 1024

#: The first bytes of each kind accepted, and the media type served for it.
SIGNATURES: Final[tuple[tuple[bytes, str], ...]] = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
)

#: Why an SVG is not accepted.
AN_SVG_IS_A_DOCUMENT_THAT_CAN_CARRY_SCRIPT: Final = (
    "A logo is served from the install's own origin to every browser that opens the console. An "
    "SVG can carry script, so accepting one would let whoever uploads it run code in every "
    "colleague's console. A raster image cannot."
)


class LogoRefusedError(Exception):
    """The upload cannot be kept. The message is a sentence a person can act on."""


@dataclass(frozen=True)
class Logo:
    """A checked image and the media type to serve it as."""

    media_type: str
    data: bytes


def checked(data: bytes) -> Logo:
    """The image these bytes are, or a refusal saying what to do."""
    if not data:
        msg = "The file is empty. Choose your logo again."
        raise LogoRefusedError(msg)
    if len(data) > MAX_LOGO_BYTES:
        msg = (
            f"The file is larger than {MAX_LOGO_BYTES // 1024} KiB. Export your logo at about "
            "twice the height it is drawn and try again."
        )
        raise LogoRefusedError(msg)
    for signature, media_type in SIGNATURES:
        if data.startswith(signature):
            return Logo(media_type, data)
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return Logo("image/webp", data)
    head = data[:512].lstrip().lower()
    if head.startswith((b"<?xml", b"<svg", b"<!doctype svg")) or b"<svg" in head:
        msg = "An SVG cannot be used here, because it can carry script. Export it as a PNG."
        raise LogoRefusedError(msg)
    msg = "That is not an image this system can use. Choose a PNG, JPEG, GIF or WebP file."
    raise LogoRefusedError(msg)


def from_base64(text: str) -> Logo:
    """The image a base64 string holds, checked."""
    try:
        data = b64decode(text.strip(), validate=True)
    except (binascii.Error, ValueError):
        msg = "The file did not arrive intact. Choose your logo again."
        raise LogoRefusedError(msg) from None
    return checked(data)


def keep(directory: Path, logo: Logo) -> None:
    """Put the file down whole, replacing any earlier one, so a reader never sees half of it."""
    directory.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=directory, prefix=".logo-")
    try:
        with os.fdopen(handle, "wb") as written:
            written.write(logo.data)
        Path(temporary).chmod(0o644)
        Path(temporary).replace(directory / LOGO_FILE_NAME)
    except BaseException:
        with contextlib.suppress(OSError):
            Path(temporary).unlink()
        raise


def read(directory: Path) -> Logo | None:
    """The kept logo, held to the same rule again, or None when there is none or it fails it."""
    try:
        data = (directory / LOGO_FILE_NAME).read_bytes()
    except OSError:
        return None
    try:
        return checked(data)
    except LogoRefusedError:
        return None
