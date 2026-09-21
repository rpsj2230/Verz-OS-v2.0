"""The one way a caught exception's text reaches a log line, a verdict, a report or a page.

Found on the owner's install on 2026-09-21: `post_deploy` printed `f"{type(exc).__name__}: {exc}"`
and psycopg's conninfo parser had quoted a fragment of the database password back in its message,
`invalid percent-encoded token: "..."`. Any driver or settings error can do the same: libpq quotes
the part of the connection string it could not parse, pydantic quotes the value it refused, and a
connection error can carry the whole URL. `describe` keeps the exception class and a sentence with
every URL, userinfo, `password=` pair, quoted literal and known credential taken out.

Rejected: redacting only exceptions that look like database errors. The settings error that quotes
`DATABASE_URL` is a pydantic error, and a list of "dangerous" classes is the list the next leak is
not on. A quoted literal is removed from every message, which costs some detail in harmless
errors; the class name and the rest of the sentence are what an operator reads first anyway.

`tests/invariants/test_exception_text_invariants.py` refuses a raw `{exc}` or `str(exc)` in an
except handler of the modules that open database connections.

Task ids: M38.5.1
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Final
from urllib.parse import quote, unquote

#: What is left of a sentence is cut here, so a message that is a dump stays a line.
MAX_CHARS: Final = 240
REDACTED: Final = "<redacted>"

# `scheme://anything-up-to-whitespace-or-quote`: a URL of any scheme, userinfo and all.
_URL = re.compile(r"[A-Za-z][A-Za-z0-9+.\-]*://[^\s\"'<>]*")
# `user:secret@host` with no scheme in front, as libpq and some clients echo it.
_USERINFO = re.compile(r"[^\s\"'@/:]+:[^\s\"'@/]*@[^\s\"'/]+")
# `password=...` and the rest of a libpq keyword/value string, quoted or not.
_KEY_VALUE = re.compile(
    r"\b(password|passwd|pwd|passfile|sslpassword|dsn|conninfo|url|host|hostaddr|user|dbname)"
    r"\s*[=:]\s*"
    r"('(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"|\S+)",
    re.IGNORECASE,
)
# Anything the message quoted: libpq and pydantic quote exactly the input they refused.
_QUOTED = re.compile(r"\"[^\"]*\"|'[^']*'")
#: A fragment of a known secret shorter than this is not removed; it would match ordinary words.
_MIN_FRAGMENT: Final = 3


def _known_secrets() -> tuple[str, ...]:
    """The passwords in every connection URL this process is configured with.

    Read through `brain.settings` because nothing else may read the environment, and never allowed
    to raise: a describer that fails while describing a failure hides the first one.
    """
    try:
        from brain.settings import Settings

        settings = Settings()
        urls = (
            settings.database_url,
            settings.migration_database_url,
            settings.read_replica_url,
            settings.valkey_url,
        )
    except Exception:
        return ()
    return tuple(p for p in (url_password(u) for u in urls) if p)


def url_password(url: str) -> str:
    """The password in a URL, decoded, or empty. Parsed by hand so it accepts what libpq refuses."""
    _, separator, rest = url.partition("://")
    if not separator:
        return ""
    authority = rest.split("/", 1)[0].split("?", 1)[0]
    userinfo, at, _host = authority.rpartition("@")
    if not at or ":" not in userinfo:
        return ""
    return unquote(userinfo.split(":", 1)[1])


def _secret_variants(secret: str) -> Iterable[str]:
    """The secret as written, encoded, decoded, and every piece of it libpq might quote alone."""
    yield secret
    yield quote(secret, safe="")
    yield unquote(secret)
    for piece in re.split(r"[%$@:/?#&=\s]", secret):
        if len(piece) >= _MIN_FRAGMENT:
            yield piece


def redact(text: str, secrets: Iterable[str] = ()) -> str:
    """`text` with every URL, userinfo, credential pair, quoted literal and known secret removed.

    The configured connection passwords are always among the known secrets; `secrets` adds more.
    """
    # Shapes first: a secret replaced first would cut a URL at `<redacted>` and leave its host.
    text = _URL.sub(REDACTED, text)
    text = _KEY_VALUE.sub(lambda m: f"{m.group(1)}={REDACTED}", text)
    text = _USERINFO.sub(REDACTED, text)
    text = _QUOTED.sub(f'"{REDACTED}"', text)
    known = (*secrets, *_known_secrets())
    for secret in sorted(
        {v for s in known if s for v in _secret_variants(s)}, key=len, reverse=True
    ):
        text = text.replace(secret, REDACTED)
    return text


def describe(exc: BaseException, *, secrets: Iterable[str] = ()) -> str:
    """`ClassName: first line of the message, redacted`: safe for a log, a verdict or a page."""
    name = type(exc).__name__
    message = str(exc).strip().splitlines()
    first = message[0] if message else ""
    sentence = redact(first, secrets)
    if len(sentence) > MAX_CHARS:
        sentence = sentence[: MAX_CHARS - 3] + "..."
    return f"{name}: {sentence}" if sentence else name
