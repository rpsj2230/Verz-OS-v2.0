"""The transport a skill import runs over: one GET, to the address the rule checked, as the name.

`brain.tools.fetch` decides where a skill may be fetched from and follows the chain, and says in
`Fetchable` that it cannot make a transport connect to the address it checked rather than to the
name. Until this module nothing implemented its `Fetcher`, so importing a skill from GitHub or a
URL had no caller: the rule was written, tested and reached by nothing. This is the `Fetcher` an
install uses, and `brain.skill_routes` hands it to the fetch.

**The connection goes to the checked address, and TLS and HTTP speak as the name.** That is
`brain.ops.webhook_delivery._PinnedHTTPSConnection`, reused rather than written again: its one
overridden method is the one that would resolve the name a second time, and a second copy of that
method is a second place for DNS rebinding to come back in. The certificate is verified against
the name, so an address that answers for a different name is a failed connection.

**One hop, and a redirect is handed back rather than followed**, because the chain is where the
address rule and the host list are applied (`brain.tools.fetch.Fetcher`'s own argument). The next
address is resolved against the one that sent it, so a relative `Location` is a whole address when
the rule sees it.

**Anything the network did is a `SkillError` in words, never the answer's body.** A 404 is "the
host answered 404"; a timeout, a refused connection or a certificate for another name is "could
not be reached". The body of a refusal is the far side's text, and the person importing reads the
message this module raises, so it carries the status and the host and nothing the host wrote.

**The body is read to one byte past the ceiling and no further.** `brain.tools.fetch.fetch`
refuses anything longer, so a host sending a gigabyte has sent the ceiling and a byte before the
connection is closed.

Task ids: M12.2.2, M12.2.3
"""

from __future__ import annotations

import http.client
import ssl
from typing import Final
from urllib.parse import urljoin, urlsplit

from brain.ops.webhook_delivery import HTTPS_PORT, SystemResolver, _PinnedHTTPSConnection
from brain.tools.fetch import FetchedBytes
from brain.tools.skills import SkillError

#: How long one hop may take, connect to last byte. A skill tarball is small; a host that takes
#: longer than this holds a request an administrator is waiting on.
FETCH_TIMEOUT_SECONDS: Final = 20.0

#: What a host sees as the client. Names the product and nothing about the install.
USER_AGENT: Final = "company-brain-skill-import/1"

#: The statuses that name the next address rather than answering.
REDIRECT_STATUSES: Final[frozenset[int]] = frozenset({301, 302, 303, 307, 308})

#: The one status that is an answer.
OK_STATUS: Final = 200

__all__ = ["FETCH_TIMEOUT_SECONDS", "USER_AGENT", "HttpsFetcher", "SystemResolver"]


class HttpsFetcher:
    """`brain.tools.fetch.Fetcher` over `http.client`, to the checked address.

    `context` is a parameter so a test can trust its own certificate; the default verifies
    against the system's authorities and the name, which is what every install uses.
    """

    def __init__(
        self,
        *,
        timeout_seconds: float = FETCH_TIMEOUT_SECONDS,
        context: ssl.SSLContext | None = None,
    ) -> None:
        self._timeout = timeout_seconds
        self._context = context if context is not None else ssl.create_default_context()

    def get_once(self, url: str, *, address: str, max_bytes: int) -> FetchedBytes | str:
        parts = urlsplit(url)
        host = parts.hostname
        if parts.scheme != "https" or not host:
            # Not reachable through `brain.tools.fetch.fetch`, whose hops have passed the https
            # rule; refused here too because this is the class that opens the socket.
            msg = f"{url!r} is not an https address"
            raise SkillError(msg)
        path = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
        connection = _PinnedHTTPSConnection(
            host,
            parts.port or HTTPS_PORT,
            address=address,
            timeout=self._timeout,
            context=self._context,
        )
        try:
            connection.request("GET", path, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
            answer = connection.getresponse()
            if answer.status in REDIRECT_STATUSES:
                location = answer.getheader("Location")
                if not location:
                    msg = f"{host} answered {answer.status} and named no address to go to"
                    raise SkillError(msg)
                return urljoin(url, location)
            if answer.status != OK_STATUS:
                msg = f"{host} answered {answer.status}, so there is nothing to import"
                raise SkillError(msg)
            return FetchedBytes(body=answer.read(max_bytes + 1), final_url=url)
        except TimeoutError:
            msg = f"{host} did not answer within {self._timeout:g} seconds"
            raise SkillError(msg) from None
        except (OSError, http.client.HTTPException) as failed:
            msg = f"{host} could not be reached ({type(failed).__name__})"
            raise SkillError(msg) from None
        finally:
            connection.close()
