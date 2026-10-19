"""Whether the host can give a part what it cannot hand back, judged at the moment it would load.

The release's plan costs this container's limit against what the other containers are allowed
(`brain.ops.overlays.plan`), and that is the right question for a decision made once, at deploy. It
is the wrong one for a decision made every time a model is loaded, for two reasons that point in
opposite directions. Limits say nothing about what the neighbours are using now: on the owner's
server a container with a 1,024 MiB limit may be holding 90, and one with none may be holding 800.
And limits count cache as spent, where the kernel counts it as spare: `MemAvailable` is free memory
plus the page cache and slab it would give back, 7.4 GB on the day it was measured against 3.9 GB
that nothing could take back.

**So this asks the kernel the one question it answers well**: how much could be given to a new
process without taking anything that is held. A part's anonymous need is compared with that, less a
reserve for the host's own work and for the neighbours to grow by while the part loads. The weights
a part maps are not in the comparison, because the kernel will evict cache to make room for them
before it will refuse; they are in the container's limit, which is the other check.

**What a refusal does.** The supervisor answers a status the application reads as an outage, so the
work waits in its queue and the part is tried again on the next request. Nothing is loaded and
nothing is lost, and the sentence says what was short, so a person reading the server's log can act.
Rejected: loading anyway and letting the kernel's out-of-memory killer decide, which kills the
largest process on the host and not necessarily this one; and waiting inside the request for memory
to appear, which holds a queue slot for the length of somebody else's problem.

**Unreadable is admitted, and says so.** A host whose `/proc/meminfo` cannot be read (a developer's
machine, a test) cannot be judged, and refusing everything there would be a server that is down for
a reason nobody can see. The cgroup limit is still the backstop.

Task ids: M7.2.1, M7.3.3
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

#: What the host keeps for itself and for its other containers to grow by while a part loads, in
#: MiB. A judgement in the register of `brain.ops.wiring.HOST_RESERVE_MIB`, which keeps 256 for the
#: kernel and a login; this is that and the same again for a neighbour's growth.
RESERVE_MIB: Final = 512

_MEMINFO: Final = Path("/proc/meminfo")


def mem_available_mib(path: Path = _MEMINFO) -> int | None:
    """`MemAvailable` in MiB, or None where the file is missing or says no such thing."""
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) // 1024
    except (OSError, ValueError, IndexError):
        return None
    return None


@dataclass(frozen=True)
class Admission:
    """The decision and the sentence for it."""

    admitted: bool
    words: str


def admit(
    part: str, *, need_mib: int, available_mib: int | None, reserve_mib: int = RESERVE_MIB
) -> Admission:
    """May this part be loaded now. Its non-reclaimable need against what the host can give."""
    if available_mib is None:
        return Admission(True, "the host's available memory could not be read; it was not judged")
    spare = available_mib - reserve_mib
    if need_mib <= spare:
        return Admission(True, f"{part} needs {need_mib} MiB and the host can give {spare}")
    return Admission(
        False,
        f"the host cannot give the {part} part the {need_mib} MiB it cannot hand back: "
        f"{available_mib} MiB is available and {reserve_mib} MiB is kept for the host, so "
        f"{max(spare, 0)} MiB is free to give. Nothing was loaded and the work waits.",
    )
