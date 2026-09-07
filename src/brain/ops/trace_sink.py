"""The one destination a post-redaction payload is allowed to go to, and what it does today.

`brain.gate.compose.TraceSink` is a protocol with no implementation anywhere in this
repository, which is why `compose` could not be called from a route: the signature requires a
sink and there was none to hand it. This is one, and it is deliberately the smallest honest
thing rather than the useful one.

**It records that a trace happened and drops the payload.** Not because dropping is good, but
because the alternative available today is worse. A sink that wrote the payload to the
application log would move post-redaction records into a stream governed by whoever can read
logs, which is a different set of people from whoever could read the records, and the whole
point of M3.9.2 having exactly one destination is that the destination's permissions are the
answer's permissions. There is no store yet whose permissions match, so the payload goes
nowhere and this says so plainly instead of finding somewhere convenient.

**What is kept is the shape, and the shape is counts.** The reference, the policy epoch, the
entitlement hash, how many records survived and how many redactions and drops the trace
recorded. `brain.core.redaction.RedactionTrace` is explicit that counts live in the object an
auditor reads and never in `ChannelPayload`, which has no field that could hold one, so a
count in this line is in the half of the system entitled to it. No field names, no values, no
record ids.

**A reference therefore names a log line and not a readable trace**, and that is the gap.
`brain.ops.tracing.TraceRecord` describes the retention a real trace store would have and
`brain.ops.retention` pins a window against it, so the store is designed and unbuilt.
Quoting a reference at somebody today gets them a line saying a trace of that shape existed.
`A_TRACE_NOBODY_CAN_OPEN_IS_A_TRACE_THAT_EXISTS` says which half of the promise is kept.

Task ids: none
"""

from __future__ import annotations

from typing import Final

import structlog

from brain.core.redaction import ChannelPayload, RedactionTrace

log = structlog.get_logger(__name__)

#: Why the payload is dropped rather than written somewhere.
THE_LOG_IS_NOT_A_TRACE_STORE: Final = (
    "A post-redaction payload written to the application log is readable by whoever can read "
    "logs, which is a different set of people from whoever could read the records it came "
    "from. M3.9.2 gives a trace exactly one destination precisely so that the destination's "
    "permissions are the answer's permissions, and a log stream does not have them. There is "
    "no store yet whose permissions match, so the payload goes nowhere, which loses the "
    "trace and discloses nothing. The other order round loses nothing and discloses "
    "everything."
)

#: What a reference gets you today, said so nobody assumes otherwise.
A_TRACE_NOBODY_CAN_OPEN_IS_A_TRACE_THAT_EXISTS: Final = (
    "A trace reference is quotable and carries no authority: it identifies which trace, and "
    "entitlement decides who may open it. Today there is nothing to open. The reference "
    "names a log line recording that a trace of a given shape existed, at a given policy "
    "epoch, for a given reach. That is enough to prove an answer was produced and not enough "
    "to review what it contained, and a person told it is a trace reference should be told "
    "which of the two they have."
)


class CountingTraceSink:
    """Records that a trace happened, in counts, and keeps no payload.

    Stateless and safe to share across requests, unlike a sink holding a connection would be.
    It is the sink `brain.app` installs and the one `brain.gate.answer` is handed.
    """

    def emit(self, reference: str, payload: ChannelPayload, trace: RedactionTrace) -> None:
        """The whole of it. Counts and hashes, never a name and never a value.

        `len` on three tuples rather than anything walked, so there is no path here that
        could read a field. A sink that summarised what was redacted would be describing the
        withheld half of an answer in a stream that is not the answer's.
        """
        log.info(
            "trace",
            reference=reference,
            policy_epoch=trace.policy_epoch,
            ent_hash=trace.ent_hash,
            records=len(payload.records),
            redactions=len(trace.redactions),
            dropped=len(trace.dropped),
            stored=False,
        )
