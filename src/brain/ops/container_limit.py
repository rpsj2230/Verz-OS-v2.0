"""The memory a worker container was actually given, and how much of it a slot plan may spend.

`brain.ops.worker` planned its slots against `brain.ops.wiring`'s figure for the container, which
is the number the compose file was held equal to by a test. Two things were wrong with that, and
the owner's install showed both on 2026-10-13.

**The plan spent 336 of 384 MiB on itself, 87.5%, and left the rest of Python the other 48.**
`concurrency_gaps` refused an allocation only when it was over the limit, so a plan that filled the
limit to within one slot was a plan that passed, and the interpreter, the imports, the connection
pool, the page cache the cgroup also counts and the acceptance run that lives in the same container
were all left to fit in what remained. One process measured about 339 MB of anonymous memory when
the kernel killed it, about every half hour, thirty times in a day, and the acceptance run in it
died each time. **A slot plan may spend `SLOT_SHARE_OF_LIMIT` of the limit and no more**, and the
rest is the process's own: the plan's cost is a working set for jobs, and a limit that is only just
above it is a limit the first allocation outside it breaks.

**The limit it was checked against was a constant, not the container's.** A limit raised by hand on
a server (the compose file's copy on a panel can be) left the worker printing the product's figure,
and a limit lowered by hand left it planning against memory it did not have. The kernel states the
truth in `memory.max` (cgroup v2) or `memory.limit_in_bytes` (v1), so `cgroup_limit_mib` reads it,
and the worker plans against what it finds. Where there is none to read (a laptop, a container
with no limit, a file that says `max` or holds the kernel's "unlimited" number) the product's own
budget stands, because a worker that cannot see a ceiling must not invent a larger one.

**Over the share is an advisory and over the limit is a refusal, and that split is deliberate.** A
container still at its old 384 MiB after an upgrade holds 336 MiB of slots, which is over 75% and
under the limit: refusing to start would turn a release that added a margin into an outage of every
background job on a server whose stored compose file nobody has edited. So the worker starts, says
in its log what the margin is and what to raise, and the product's own budget is held to the share
by test so that no install made from it begins short. Rejected: shrinking the slot count to fit,
which silently changes how much work an install does; and refusing, for the reason above.

Task ids: M32.4.1.4
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Final

#: The most of a worker's memory limit its slots may be planned to spend. The rest is the process's
#: own, and the measurement behind the figure is in `brain.ops.wiring` (`brain-worker`).
SLOT_SHARE_OF_LIMIT: Final = 0.75

#: Where the kernel states a container's memory limit: cgroup v2, then cgroup v1.
CGROUP_LIMIT_FILES: Final[tuple[str, ...]] = (
    "/sys/fs/cgroup/memory.max",
    "/sys/fs/cgroup/memory/memory.limit_in_bytes",
)

#: Why a limit the kernel does not state is not a limit.
AN_UNLIMITED_CGROUP_IS_NOT_A_BIGGER_BUDGET: Final = (
    "A cgroup that says `max`, or holds the number the kernel prints for no limit, bounds nothing, "
    "so the planner keeps the budget the product declared for the container instead of treating "
    "the machine's whole memory as room for slots."
)

#: cgroup v1 prints a number near 2**63 for no limit, and nothing real is within a thousandth of it.
UNLIMITED_BYTES: Final = 2**60

MIB: Final = 1024 * 1024


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def cgroup_limit_mib(
    read: Callable[[str], str] = _read, files: tuple[str, ...] = CGROUP_LIMIT_FILES
) -> int | None:
    """The memory limit this container was given, in whole MiB, or None when none is stated.

    Each file in turn, v2 first. A file that is missing or unreadable is skipped, which is how a
    laptop and a v1 host differ from a v2 one; a file that says `max` or holds a number at or above
    `UNLIMITED_BYTES` is the answer None, see `AN_UNLIMITED_CGROUP_IS_NOT_A_BIGGER_BUDGET`; text
    that is not a positive number is skipped as though absent. The reader is a parameter because a
    function that could only ever read this machine's files could not be shown to fail.
    """
    for path in files:
        try:
            text = read(path).strip()
        except OSError:
            continue
        if text == "max":
            return None
        try:
            value = int(text)
        except ValueError:
            continue
        if value <= 0:
            continue
        if value >= UNLIMITED_BYTES:
            return None
        return max(value // MIB, 1)
    return None


def given_limit_mib(budget_mib: int, cgroup_mib: int | None) -> int:
    """The limit to plan against: what the kernel states, else the product's own budget."""
    return budget_mib if cgroup_mib is None else cgroup_mib


def planned_share_mib(limit_mib: int) -> int:
    """The most of `limit_mib` a slot plan may spend, rounded down to whole MiB."""
    return int(limit_mib * SLOT_SHARE_OF_LIMIT)


def limit_findings(
    slots: int, mib_per_slot: int, limit_mib: int, *, where: str
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """(refusals, advisories) for a standard-slot plan against the limit the container has.

    Over the limit is a refusal: the kernel will kill the container the first time the slots are
    all busy. Over the share and under the limit is an advisory: the plan fits and leaves the
    process less than it needs. See the module docstring for why they differ.
    """
    wanted = slots * mib_per_slot
    if wanted > limit_mib:
        return (
            (
                f"{slots} slots at {mib_per_slot} MiB is {wanted} MiB, over the {limit_mib} MiB "
                f"limit {where}",
            ),
            (),
        )
    share = planned_share_mib(limit_mib)
    if wanted > share:
        return (
            (),
            (
                f"{slots} slots at {mib_per_slot} MiB is {wanted} MiB of the {limit_mib} MiB "
                f"limit {where}, over the {share} MiB ({int(SLOT_SHARE_OF_LIMIT * 100)}%) a plan "
                "may spend, which leaves the rest of the process too little and is how this "
                "container comes to be killed by the kernel while the queue looks idle; raise "
                f"the container's memory limit to at least {-(-wanted * 4 // 3)} MiB, or "
                "allocate fewer slots",
            ),
        )
    return (), ()
