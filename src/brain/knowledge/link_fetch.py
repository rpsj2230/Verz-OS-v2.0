"""The transport a knowledge link is fetched over: one GET, to the address the rule checked.

`brain.tools.fetch` decides where this server may connect and follows the redirect chain, checking
every hop; its `Fetchable` says it cannot make a transport connect to the address it checked
rather than to the name. This is the `Fetcher` that does, for the link an administrator adds to
the knowledge layer (M7.1.2), and `brain.knowledge_intake_routes` hands it to
`brain.knowledge.uploads.receive_page`.

**The connection goes to the checked address and TLS and HTTP speak as the name.** That is
`brain.ops.webhook_delivery._PinnedHTTPSConnection`, reused rather than written again: its one
overridden method is the one that would resolve the name a second time, and a second copy of it is
a second place DNS rebinding could come back in. The certificate is verified against the name.

**One hop, and a redirect is handed back rather than followed**, because the chain is where the
address rule is applied to every hop (`brain.tools.fetch.Fetcher`'s own argument). A relative
`Location` is resolved against the address that sent it, so the rule always sees a whole address.

**Anything the network did is a sentence, never the answer's body.** A 404 is "the site answered
404"; a timeout, a refused connection or a certificate for another name is "could not be reached".
The body of a refusal is the far side's text, and the administrator reads the message raised here.

**The body is read to one byte past the ceiling and no further**, so `brain.tools.fetch.fetch`
refuses an answer over it having received only the ceiling and a byte.

Rejected: sending a browser's user agent to be served what a browser is served. A site that
refuses an honest client is a site whose page should be saved from a browser by a person, and
`ParseCause.SCRIPTED_PAGE` already says so for the commonest case.

The skill importer (T2, `brain.ops.skill_fetch`) carries a transport of the same shape; one of
the two can be folded into the other once both have landed, and neither decides anything the
other depends on.

Task ids: M7.1.2
"""

from __future__ import annotations

import http.client
import ssl
from typing import Final
from urllib.parse import urljoin, urlsplit

from brain.ops.webhook_delivery import HTTPS_PORT, SystemResolver, _PinnedHTTPSConnection
from brain.tools.fetch import FetchedBytes
from brain.tools.skills import SkillError

#: How long one hop may take, connect to last byte. An administrator is waiting on the answer.
LINK_TIMEOUT_SECONDS: Final = 20.0

#: What a site sees as the client. Names the product and nothing about the install.
USER_AGENT: Final = "company-brain-knowledge-link/1"

#: What is asked for: the types a link may answer with, pages first.
ACCEPT: Final = (
    "text/html, text/plain;q=0.9, text/markdown;q=0.9, application/pdf;q=0.8, "
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document;q=0.8"
)

#: The statuses that name the next address rather than answering.
REDIRECT_STATUSES: Final[frozenset[int]] = frozenset({301, 302, 303, 307, 308})

#: The one status that is an answer.
OK_STATUS: Final = 200

__all__ = ["LINK_TIMEOUT_SECONDS", "USER_AGENT", "LinkFetcher", "SystemResolver"]


class LinkFetcher:
    """`brain.tools.fetch.Fetcher` over `http.client`, to the checked address, as the name.

    `context` is a parameter so a test can trust its own certificate; the default verifies
    against the system's authorities and the name, which is what every install uses.
    """

    def __init__(
        self,
        *,
        timeout_seconds: float = LINK_TIMEOUT_SECONDS,
        context: ssl.SSLContext | None = None,
    ) -> None:
        self._timeout = timeout_seconds
        self._context = context if context is not None else ssl.create_default_context()

    def get_once(self, url: str, *, address: str, max_bytes: int) -> FetchedBytes | str:
        parts = urlsplit(url)
        host = parts.hostname
        if parts.scheme != "https" or not host:
            # Unreachable through `brain.tools.fetch.fetch`, whose hops have passed its https
            # rule; refused here as well because this is the class that opens the socket.
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
            connection.request("GET", path, headers={"User-Agent": USER_AGENT, "Accept": ACCEPT})
            answer = connection.getresponse()
            if answer.status in REDIRECT_STATUSES:
                location = answer.getheader("Location")
                if not location:
                    msg = f"{host} answered {answer.status} and named no address to go to"
                    raise SkillError(msg)
                return urljoin(url, location)
            if answer.status != OK_STATUS:
                msg = f"{host} answered {answer.status}, so there is nothing to add"
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
