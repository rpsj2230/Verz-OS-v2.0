"""The install acceptance checks for what an install must not carry over from anywhere: a default
administrator, a secret in a table, a webhook that goes out in the clear, a source with no key.

M42.4.3 asks for an audit of credentials, tokens, webhooks, third-party integrations and default
administrator accounts. The product has no default administrator by design (the first one is
appointed by the person holding the setup code) and keeps secrets in the vault by design, so the
audit is the proof that the design held on this install: that what a copied database, a hand repair
or an old release could have left behind is not there.

**Two checks, and every query is bounded.** The first reads who holds the administrator's authority
and what sessions are open; the second reads the saved installation values, the webhook
subscribers, the connected sources and their credential writes. Each reads a bounded set of rows
(`MOST_ROWS`) ordered by key, never a whole table, and never casts a table to text to search it. A
database with more rows than the bound is audited over its first `MOST_ROWS` and says so in the
docstring and here, not silently: the installs this runs on hold a few hundred people and a few
dozen sources.

**They pass on an install with its own data.** An administrator is a person who holds the
authority and can sign in (the setting-up administrator is bound by the finishing screen, and every
later one by an administrator), a webhook goes to an https address and has its signing secret at a
vault path, a connected source that takes a key has a credential write on record, and the saved
values hold no secret. An install with none of those passes the steps that have nothing to read; a
step is never passed by reading nothing where the install holds something.

**What is not read.** The vault itself: the check asks the credential-write ledger that a key was
written, never the vault whether it is held, because the worker has no business reading a secret
and the Connectors screen already says whether one is held. Tokens are read as sessions: the
identity provider's own tokens are the identity provider's.

Rejected: a denylist of other companies' names. The repository must not contain one (the
independence sweep refuses it), and a list generated from history and shipped hashed is still a
company detail in the source. What "another company's values" means for the stores of a live install
is a question for the owner, `docs/needs-rupash.md` item 269, and M42.4.2 waits on it.

Task ids: M42.4.3
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Final

from sqlalchemy import text

from brain.ops.acceptance import CheckFailedError, check
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page, before every larger key. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 2330

#: The most rows any step reads. See the module docstring.
MOST_ROWS: Final = 2000

#: Names a default administrator account is given, and nobody is called. An install's administrator
#: is a person, so none of these is a display name or a work address's local part there.
DEFAULT_ACCOUNT_NAMES: Final = frozenset(
    {"admin", "administrator", "root", "superuser", "default", "default admin", "test", "demo"}
)

#: How long a session may be open at most, in days. Restated here and not read from the product, so
#: a change to the product's lifetime fails this step instead of moving with it.
LONGEST_SESSION_DAYS: Final = 31

#: What a pasted secret looks like, by the shapes providers hand them out in. Not a scan of values
#: for entropy, which would flag a hash of a file; these are the prefixes people paste.
SECRET_SHAPES: Final = re.compile(
    r"(sk-[A-Za-z0-9_-]{20,}|xox[abprs]-[A-Za-z0-9-]{10,}|gh[pousr]_[A-Za-z0-9]{20,}"
    r"|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----"
    r"|eyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,})"
)


# ------------------------------------------------ 1. administrators and sessions
@check(
    leaves=("M42.4.3",),
    sentence=(
        "Every person who holds the administrator's authority over the whole company can sign in "
        "as themselves and is not called by a name a default account has, and no session is open "
        "for longer than a month."
    ),
)
async def administrators_are_people_with_sign_ins_and_sessions_are_short(
    h: Harness,
) -> None:
    from brain.gate.entitlement_store import entitlements_from
    from brain.identity.first_administrator import holds_everywhere

    now = datetime.now(UTC)
    reaches = (
        await h.execute(
            text(
                "SELECT gate.resolve_entitlements(p.id, :at) FROM "
                "(SELECT id FROM auth.principal ORDER BY id LIMIT :most) AS p"
            ).bindparams(at=now, most=MOST_ROWS)
        )
    ).scalars()
    administrators = [
        one.principal_id
        for one in (entitlements_from(payload) for payload in reaches)
        if holds_everywhere(one, now)
    ]
    if administrators:
        named = (
            await h.execute(
                text(
                    "SELECT lower(btrim(display_name)) FROM auth.principal "
                    "WHERE id = ANY(:ids) ORDER BY id LIMIT :most"
                ).bindparams(ids=administrators, most=MOST_ROWS)
            )
        ).scalars()
        if any(name in DEFAULT_ACCOUNT_NAMES for name in named):
            raise CheckFailedError("an administrator is named as a default account is")
        bound = (
            await h.execute(
                text(
                    "SELECT DISTINCT principal_id FROM auth.principal_identity "
                    "WHERE deleted_at IS NULL AND channel = 'console' "
                    "AND principal_id = ANY(:ids) LIMIT :most"
                ).bindparams(ids=administrators, most=MOST_ROWS)
            )
        ).scalars()
        if set(administrators) - set(bound):
            raise CheckFailedError("an administrator has no sign-in of their own bound to them")

    long_lived = (
        await h.execute(
            text(
                "SELECT count(*) FROM (SELECT 1 FROM auth.session WHERE ended_at IS NULL "
                "AND expires_at - started_at > make_interval(days => :days) "
                "ORDER BY started_at LIMIT :most) AS s"
            ).bindparams(days=LONGEST_SESSION_DAYS, most=MOST_ROWS)
        )
    ).scalar_one()
    if long_lived:
        raise CheckFailedError("a session is open that is allowed to last longer than a month")


# ------------------------------------------------ 2. secrets, webhooks and sources
@check(
    leaves=("M42.4.3",),
    sentence=(
        "No saved installation value is a secret, every active webhook goes to an https address "
        "with its signing secret at a vault path, and every connected source that takes a key has "
        "a credential write on record."
    ),
)
async def settings_hold_no_secret_and_webhooks_and_sources_are_held(
    h: Harness,
) -> None:
    from urllib.parse import urlsplit

    from brain.connectors.declaration import CredentialShape
    from brain.ops.connectable import CONNECTABLE
    from brain.ops.credentials import connector_key_slot
    from brain.ops.install_settings import saved_query, values_from
    from brain.ops.openbao import SIGNING_PREFIX
    from brain.tables.config import SettingRow

    rows = (await h.execute(saved_query().order_by(SettingRow.key).limit(MOST_ROWS))).all()
    saved = values_from(rows)
    if any(SECRET_SHAPES.search(value) for value in saved.values()):
        raise CheckFailedError("a saved installation value is shaped like a key a provider gives")

    hooks = (
        await h.execute(
            text(
                "SELECT endpoint, secret_path FROM ops.webhook_subscriber "
                "WHERE deactivated_at IS NULL ORDER BY subscriber_id LIMIT :most"
            ).bindparams(most=MOST_ROWS)
        )
    ).all()
    if any(urlsplit(str(endpoint).strip()).scheme != "https" for endpoint, _ in hooks):
        raise CheckFailedError("an active webhook goes to an address that is not https")
    if any(not str(path).startswith(SIGNING_PREFIX) for _, path in hooks):
        raise CheckFailedError("an active webhook's signing secret is not at a signing path")

    connected = (
        await h.execute(
            text(
                "SELECT connector FROM ops.connector_connection WHERE disconnected_at IS NULL "
                "ORDER BY connector LIMIT :most"
            ).bindparams(most=MOST_ROWS)
        )
    ).scalars()
    for source in connected:
        kind = CONNECTABLE.get(str(source))
        if kind is None or kind.credential_shape is CredentialShape.NONE:
            continue
        written = (
            await h.execute(
                text("SELECT 1 FROM ops.credential_write WHERE slot = :slot LIMIT 1").bindparams(
                    slot=connector_key_slot(str(source)).path
                )
            )
        ).first()
        if written is None:
            raise CheckFailedError("a connected source that takes a key has no credential written")
