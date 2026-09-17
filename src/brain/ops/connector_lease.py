"""A connector run holds the vault's authority to read its source's key for that run and no longer.

A source's key is issued by its vendor and stays valid until somebody revokes it there, so nothing
can mint a fresh one per run, and `brain.ops.openbao` says so. Until 2026-09-17 that sentence was
also why nothing about reading one was leased: the worker's own token read `connector_keys/data/+`
directly, for as long as the token lived, which is a month renewed for ever. A vault token that can
read every source's key at any moment is a standing credential with extra steps.

**What is leased is the reading, not the key.** Each attempt asks the vault for a child of the
worker's token against the `connector-run` token role, with `RUN_LEASE_TTL`, no renewal and one
policy, `connector-run`, which reads `connector_keys/data/+` and revokes itself. The key is read
through that token, and the token is revoked when the attempt ends, in a `finally`, whatever the
attempt came to. The worker's own policy loses the read, so a worker token copied out of the
environment reads no key without minting a run token, and every mint is an entry in the vault's
audit log with a TTL on it. See `THE_WORKER_READS_A_KEY_ONLY_THROUGH_A_RUN_LEASE`.

**The answer is checked, not trusted.** A token role is configuration on the vault, typed by
whoever ran the installer, and a role configured wider than `ops/openbao/policies/connector-run.hcl`
would hand a run the worker's own reach. So a minted token is refused, and revoked at once, when
the vault says it may be renewed, carries any policy but `RUN_POLICY`, or runs longer than was
asked. See `judge_minted` and `A_RUN_LEASE_THE_VAULT_WIDENED_IS_GIVEN_BACK_UNUSED`.

**How a lease ended is recorded beside the attempt, as one of three words.** `revoked` is the
ordinary end. `expired` is a token whose TTL ran out before the attempt ended, so the revocation
found nothing to take back, which is harmless and worth seeing because it means the TTL is shorter
than a run. `not_revoked` is a token the vault did not confirm taking back while it was still live,
which lives on until its TTL and is the one an operator should look at. `none` is an attempt that
never held one. The Secrets vault screen counts them per source. See `LeaseOutcome`.

**What this does not do, stated.** The key itself, once read, is a string in the worker's memory
for the rest of the attempt, and the vendor accepts it for as long as the vendor does; a lease on
the vault's side cannot shorten that. What the lease bounds is who can read the key out of the
vault and when, which is the half this system controls.

Rejected: one token role and policy per source, generated from the connectable catalogue. It would
narrow a run to its own source's slot, and every release adding a source would need a
policy-writing token on every install to load the new file, which is the root token the installer
revokes. The narrowing to one slot is kept in code instead, before the vault is asked:
`brain.ops.connector_sync_run.WorkerConnectorKeys` refuses a reference that is not the source's own.

Rejected: revoking the token straight after the key is read. The read is the only use, so the
exposure would be shorter, but "revoked when the run ends" would then be a claim about a moment that
is not the run's end, and a run that fails before reading would still need the `finally`.

Task ids: M31.3.2.3, M31.3.2.4
"""

from __future__ import annotations

import enum
from datetime import timedelta
from typing import Final

from brain.ops.secrets import MAX_LEASE

# ------------------------------------------------------------------ written-down reasons

#: Why the worker's policy no longer reads a source's key.
THE_WORKER_READS_A_KEY_ONLY_THROUGH_A_RUN_LEASE: Final = (
    "The worker's token is renewed for as long as the worker runs, so a read granted to it is a "
    "read of every source's key at any moment for ever. The read is granted to the connector-run "
    "policy instead, which only a child token minted per attempt carries, with a TTL, no renewal "
    "and revocation when the attempt ends, and the worker's policy may mint that token and read "
    "nothing under connector_keys itself."
)

#: Why a run token wider than asked for is refused rather than used.
A_RUN_LEASE_THE_VAULT_WIDENED_IS_GIVEN_BACK_UNUSED: Final = (
    "The token role is configuration on the vault, typed at install, and a role left renewable, "
    "given the default policy or another policy, or allowed a longer TTL, would hand a run more "
    "than the connector-run policy. The worker checks what the vault says the token carries and "
    "revokes a token that disagrees before anything is read with it."
)

# ------------------------------------------------------------------------ the lease

#: The token role the installer creates and the worker mints against.
RUN_TOKEN_ROLE: Final = "connector-run"  # noqa: S105

#: The one policy a run token may carry. Its file is `ops/openbao/policies/connector-run.hcl`.
RUN_POLICY: Final = "connector-run"

#: How long a run token lives if nothing revokes it. A run reads its key in its first second and
#: most runs end inside a minute; fifteen minutes covers a run that waits its two minutes for a
#: source's allowance and reads every page, and bounds a token whose revocation was lost.
RUN_LEASE_TTL: Final = timedelta(minutes=15)

#: The token role's own ceiling, as the installer writes it. `MAX_LEASE`, one hour.
RUN_ROLE_MAX_TTL_SECONDS: Final = int(MAX_LEASE.total_seconds())


class LeaseOutcome(enum.StrEnum):
    """How a run's lease ended. `ops.connector_sync.lease` holds one of these per attempt."""

    #: No token was minted: no vault, a vault that refused or did not answer, or a refused token.
    NONE = "none"
    #: The vault confirmed the token revoked when the attempt ended.
    REVOKED = "revoked"
    #: The token's TTL had run out by the time the attempt ended, so nothing was left to revoke.
    EXPIRED = "expired"
    #: The vault did not confirm the revocation while the token was live; it lives until its TTL.
    NOT_REVOKED = "not_revoked"


def judge_minted(
    *, renewable: bool, policies: tuple[str, ...], lease_seconds: int, asked: timedelta
) -> str:
    """Why a minted run token may not be used, or an empty string when it may.

    See `A_RUN_LEASE_THE_VAULT_WIDENED_IS_GIVEN_BACK_UNUSED`. Each refusal is a sentence naming the
    kind of disagreement and never the token.
    """
    if renewable:
        return (
            "the vault minted a run token that may be renewed, so its end is not the TTL asked for"
        )
    if set(policies) != {RUN_POLICY}:
        return f"the vault minted a run token carrying policies other than {RUN_POLICY} alone"
    if lease_seconds <= 0 or lease_seconds > int(asked.total_seconds()):
        return "the vault minted a run token that lives longer than the TTL asked for"
    return ""
