"""What a document read inside the application may cost, which is not what the parse worker may.

The console reads plain text, Markdown, PDF and Word uploads in the request that received them,
through `brain.knowledge.text_path`, and a link's page the same way. That read happens in the
application container. Until 2026-09-29 it was admitted against
`brain.knowledge.parse_budget.parse_budget_bytes()`, which is **the parse worker's** budget:
512 MiB less its 64 MiB reserve, 448 MiB, in a container that is not the one doing the work.
Measured on a staging install that day, the application container held 845 MiB of its 1024 MiB
limit shortly after start and had peaked at 955 MiB. So a 50 MiB PDF, whose declared cost is
300 MiB, was admitted against 448 MiB and read in a container with well under a hundred to
spare: an out-of-memory kill of the application, which ends every request in flight, from one
upload the door said it accepted.

**The budget is the application's own spare memory, shared among its processes.** Three figures
and none of them is chosen here:

- `APP_MEMORY_MIB`, the application service's limit in `docker-compose.yml`. A test reads the
  file and holds this to it, the way `brain.ops.wiring.PRODUCTION_BASELINE_MIB` is held, because
  the value of the number is that it stops matching when somebody changes the file.
- What the container holds before any document is read, `resident_mib`: the supervisor and one
  worker's share for each process, `brain.runtime.RUNTIME_HEADROOM_MB` plus `WORKER_MB` each,
  which are the measured peaks rounded up. **The peak, not the instant**, for the reason
  `brain.ops.wiring` sizes against reservations rather than free memory: what is spare at one
  moment is what is needed on the busy afternoon. A model rather than one measured figure,
  because a container of another size starts another number of processes and each brings its
  own memory; `APP_RESIDENT_MIB` is the measurement the model is held to.
- The number of processes, from `brain.runtime.most_workers`: the memory and pooler ceilings
  the launcher starts against. `_ONE_PARSE_AT_A_TIME` in `brain.knowledge_routes` is a lock inside
  one process, so each of them may be reading a document at the same moment, and the spare
  memory is shared that many ways. Those ceilings rather than the count actually started,
  because the cores can only lower the count, and a lower count only ever makes this budget
  safe with room over.

**A file over the budget is refused before it is opened**, with `ParseCause.OUT_OF_MEMORY`'s
wording, which names the file and never the machine: see
`brain.knowledge.parse_budget.A_REFUSAL_NAMES_THE_FILE_AND_NEVER_THE_QUEUE`. The expansion
factors are the parse worker's, unmeasured, and the argument that they are a rule of thumb
rather than a measurement applies here unchanged.

**The finding is printed, not hidden.** `app_parse_gaps` says when the door admits a text-path
file the application cannot read, naming the largest it can. On the figures above that is every
PDF over a few MiB, which is a real limit on what the console can take in, and it is the owner's
upload-limit question (Needs Rupash, the upload limit item) rather than something to settle by
raising a constant. Two ways it closes: give the application container more memory, or read
large documents in the parse worker instead of in the request.

Rejected: *share one lock across the container, so one parse gets all the spare memory.* It
multiplies the budget by the process count, and it needs a lock the processes share (a file
lock, or the cache), which is a change to how uploads queue in the request and not a budgeting
change. Recorded here so the next person does not mistake the division for an oversight.

Task ids: M7.7.11
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Final

from brain.knowledge.ingest import TYPE_LIMITS, MediaType, ceiling_for
from brain.knowledge.parse_budget import MIB, PARSE_EXPANSION
from brain.knowledge.text_path import TEXT_PATH_TYPES
from brain.runtime import RUNTIME_HEADROOM_MB, WORKER_MB, most_workers

#: The compose service the in-app text path runs in.
APP_SERVICE: Final = "app"

#: `deploy.resources.limits.memory` on `APP_SERVICE` in `docker-compose.yml`, in MiB. Held to the
#: file by `tests/unit/test_app_parse_budget.py`.
APP_MEMORY_MIB: Final = 1024

#: What the deployed application container was measured to hold before it read any document, in
#: MiB: cgroup `memory.peak` on a staging install on 2026-09-29, 955 and then 954 after the next
#: deploy. Not the figure the budget uses: `resident_mib_for` is, and a test holds it to cover
#: this one, so the model can never promise more room than the container was seen to have.
APP_RESIDENT_MIB: Final = 955


def resident_mib_for(memory_mib: int) -> int:
    """What a container of this size holds before any read: the supervisor and each process."""
    return RUNTIME_HEADROOM_MB + most_workers(memory_mib) * WORKER_MB


def app_parse_budget_bytes(
    *, memory_mib: int = APP_MEMORY_MIB, resident_mib: int | None = None
) -> int:
    """The most one document read inside the application may be declared to cost.

    The container's limit less what it holds before any read, shared among the processes that
    may each be reading one at the same time. Nothing when the resident figure meets or passes
    the limit, so a container already full refuses every document rather than admitting one
    against a negative number. Both figures are parameters, so this can be asked of a container
    we do not run.
    """
    held = resident_mib_for(memory_mib) if resident_mib is None else resident_mib
    spare_mib = max(0, memory_mib - held)
    return spare_mib * MIB // most_workers(memory_mib)


def largest_in_app_cost(types: Iterable[MediaType] = TEXT_PATH_TYPES) -> tuple[MediaType, int]:
    """The largest declared cost the door can hand the in-app path, and the type that has it.

    Over the door's own ceilings and the text path's own types, so raising a ceiling or adding a
    type to the text path is answered here on the same commit. Sorted before the choice, so a tie
    names the same type every time.
    """
    costs = {
        media_type: ceiling_for(media_type) * PARSE_EXPANSION[TYPE_LIMITS[media_type].container]
        for media_type in sorted(types, key=lambda one: one.value)
    }
    worst = max(costs, key=lambda media_type: costs[media_type])
    return worst, costs[worst]


def app_parse_gaps(
    *, memory_mib: int = APP_MEMORY_MIB, resident_mib: int | None = None
) -> tuple[str, ...]:
    """Whether the application can read everything the door lets onto the in-app path.

    One finding or none, in words naming the figures and the two ways to close it. Printed by
    the application at start for the operator; never returned to anybody who uploaded something,
    for `A_REFUSAL_NAMES_THE_FILE_AND_NEVER_THE_QUEUE`'s reason.
    """
    held = resident_mib_for(memory_mib) if resident_mib is None else resident_mib
    budget = app_parse_budget_bytes(memory_mib=memory_mib, resident_mib=held)
    media_type, cost = largest_in_app_cost()
    if cost <= budget:
        return ()
    expansion = PARSE_EXPANSION[TYPE_LIMITS[media_type].container]
    readable_mib = budget // expansion / MIB
    return (
        f"the door admits {media_type.value} up to {ceiling_for(media_type) // MIB} MiB, a "
        f"declared cost of {cost // MIB} MiB, and a document read inside the application may cost "
        f"{budget // MIB} MiB ({memory_mib} MiB limit, {held} MiB held before any read, "
        f"{most_workers(memory_mib)} processes), so the largest such file it can read is "
        f"{readable_mib:.1f} MiB and a larger one is refused as too large; give the application "
        "container more memory, or read large documents in the parse worker",
    )
