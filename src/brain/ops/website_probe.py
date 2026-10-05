"""The transport a website check runs over: one request, to the checked address, as the name.

`brain.tools.website_check` decides which addresses may be contacted and follows the chain, and
says in its docstring that no `Prober` had ever contacted a website, so the tool was registered by
a test and by nothing an install runs. This is the `Prober` an install uses, and
`brain.tools.startup.build_registry` registers the check with it.

**The connection goes to the checked address, and TLS and HTTP speak as the name.** That is
`brain.ops.webhook_delivery._PinnedHTTPSConnection`, reused as `brain.ops.skill_fetch` reuses it:
its one overridden method is the one that would resolve the name a second time, and a second copy
of that method is a second place for DNS rebinding to come back in. The certificate is verified
against the name.

**One hop, the status line and the headers, and no body.** A website check asks whether a page
answers, where it sends a visitor and when its certificate runs out. The body answers none of
that, and reading it would make the check's cost the size of the page. The redirect is reported in
`location` and never followed here, because the chain is where the address rule is applied to
every hop (`website_check.Prober`'s own argument).

**An expired certificate is the commonest reason a check fails, so its date is read anyway.** A
handshake that fails verification is reported as `ProbeFailure.TLS` whatever happens next, and
then one more handshake is made to the same checked address with verification off, only to read
the certificate's expiry. Nothing is sent over it: no request, no header, no path. Rejected:
reporting a TLS failure with no date, which tells a person something is wrong and leaves them to
find out what, when the answer is one field away.

**What a hop took is measured here, from before the connection to the status line.** The tool's
`response_seconds` is what a visitor waits before the page starts; it is not the transfer time of
a body nobody read.

Task ids: M12.4.4
"""

from __future__ import annotations

import asyncio
import http.client
import ssl
import time
from datetime import datetime
from typing import Final
from urllib.parse import urlsplit

from brain.ops.webhook_delivery import HTTPS_PORT, _PinnedHTTPSConnection
from brain.tools.fetch import Fetchable
from brain.tools.website_check import ProbeAnswer, ProbeFailure

#: What a site sees as the client. Names the product and nothing about the install.
USER_AGENT: Final = "company-brain-website-check/1"

__all__ = ["USER_AGENT", "HttpsProber", "certificate_expiry"]


def certificate_expiry(der: bytes) -> datetime | None:
    """The expiry of a certificate given in DER, or None when it cannot be read."""
    from cryptography import x509

    try:
        return x509.load_der_x509_certificate(der).not_valid_after_utc
    except ValueError:
        return None


class HttpsProber:
    """`brain.tools.website_check.Prober` over `http.client`, to the checked address.

    `context` is a parameter so a test can trust its own certificate; the default verifies
    against the system's authorities and the name, which is what every install uses.
    """

    def __init__(self, *, context: ssl.SSLContext | None = None) -> None:
        self._context = context if context is not None else ssl.create_default_context()

    async def probe(self, target: Fetchable, *, timeout_seconds: float) -> ProbeAnswer:
        """One hop, in a thread, so the event loop turns while a slow site is waited on."""
        return await asyncio.to_thread(self._probe, target, timeout_seconds)

    def _probe(self, target: Fetchable, timeout_seconds: float) -> ProbeAnswer:
        parts = urlsplit(target.url)
        port = parts.port or HTTPS_PORT
        path = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
        connection = _PinnedHTTPSConnection(
            target.host,
            port,
            address=target.address,
            timeout=timeout_seconds,
            context=self._context,
        )
        started = time.monotonic()
        try:
            connection.request("GET", path, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
            # Read before the response, which closes the socket of a server that will not keep
            # the connection open.
            der = connection.sock.getpeercert(binary_form=True) if connection.sock else None
            answer = connection.getresponse()
            elapsed = time.monotonic() - started
            return ProbeAnswer(
                elapsed_seconds=elapsed,
                status=answer.status,
                location=answer.getheader("Location") or "",
                certificate_not_after=certificate_expiry(der) if der else None,
            )
        except TimeoutError:
            return ProbeAnswer(
                elapsed_seconds=time.monotonic() - started, failure=ProbeFailure.TIMEOUT
            )
        except ssl.SSLError:
            elapsed = time.monotonic() - started
            return ProbeAnswer(
                elapsed_seconds=elapsed,
                failure=ProbeFailure.TLS,
                certificate_not_after=self._unverified_expiry(target, port, timeout_seconds),
            )
        except (OSError, http.client.HTTPException):
            return ProbeAnswer(
                elapsed_seconds=time.monotonic() - started, failure=ProbeFailure.CONNECTION
            )
        finally:
            connection.close()

    def _unverified_expiry(
        self, target: Fetchable, port: int, timeout_seconds: float
    ) -> datetime | None:
        """The certificate's expiry read from a handshake that sends nothing. See the docstring."""
        looking = ssl.create_default_context()
        looking.check_hostname = False
        looking.verify_mode = ssl.CERT_NONE
        connection = _PinnedHTTPSConnection(
            target.host, port, address=target.address, timeout=timeout_seconds, context=looking
        )
        try:
            connection.connect()
            der = connection.sock.getpeercert(binary_form=True) if connection.sock else None
        except (OSError, http.client.HTTPException):
            return None
        finally:
            connection.close()
        return certificate_expiry(der) if der else None
