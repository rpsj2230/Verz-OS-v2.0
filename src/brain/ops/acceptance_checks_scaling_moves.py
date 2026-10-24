"""Install check for the Capacity screen's scaling moves: what is due, measured, and not measured.

`brain.ops.scaling` declared four scaling moves and the predicate that says when each is due, and
until `GET /install/capacity` served them nothing called it: its own table said each was "a
decision for a person asked when someone looks", and nobody was ever shown the question. The route
now serves one line per declared trigger, and this check asks it as a reader of the screen.

**What is held is that the line says what it could and could not know.** The ledger's move is
decided from the window the retention policy keeps and the partition the install cuts, both
declared elsewhere; the host move is the arithmetic `brain.ops.wiring` already does over the
measured host; and the two moves whose input nothing here measures (console reads in flight, a
report screen's time) are served as not measured, never as not due. A check that only asserted a
due flag would pass a route that reported "not due" for everything it had never looked at, which
is the reading `report_is_due` refuses to give for an unmeasured report. See
`A_MOVE_NOTHING_MEASURES_IS_NOT_A_MOVE_THAT_IS_NOT_DUE`.

**It is held against the table and the install, never against itself.** The set of lines is
`brain.ops.scaling.TRIGGERS`; the ledger line's window is the retention policy's own; the host
line's count is `budget_breaches` for this install's profile, asked again here.

Task ids: M36.1.1.4, M36.1.4.3, M36.1.2.4, M36.1.3.3
"""

from __future__ import annotations

from typing import Any, Final

from brain.ops import read_load
from brain.ops.acceptance import RESERVED_DEPARTMENTS, CheckFailedError, CheckNotRunError, check
from brain.ops.acceptance_operations_console import asking_as, console_for, refused, screen_grants
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 2125

A, _B = RESERVED_DEPARTMENTS

#: Why a move nothing measures is served as not measured.
A_MOVE_NOTHING_MEASURES_IS_NOT_A_MOVE_THAT_IS_NOT_DUE: Final = (
    "An unmeasured report is not a fast one. A line that reads 'not due' for a move whose input "
    "nobody records sends the owner away believing nothing is wrong, so a move with no "
    "measurement is served with no flag at all and a sentence saying nothing measures it."
)


@check(
    leaves=("M36.1.1.4", "M36.1.4.3"),
    sentence=(
        "The Capacity screen's route serves one line for every scaling trigger the product "
        "declares: the ledger's partitioning is stated due from the retention window and the "
        "partition size, the host split from this install's own memory arithmetic, and a move "
        "nothing here measures carries no due flag and says so; a person without the screen is "
        "refused."
    ),
)
async def each_scaling_move_says_when_it_is_due_and_what_it_cannot_say(
    h: Harness,
) -> None:
    from brain.install_routes import capacity
    from brain.ops.retention import METADATA_LEDGER_RETENTION_DAYS
    from brain.ops.scaling import PARTITION_ANCHOR, TRIGGERS
    from brain.ops.wiring import budget_breaches

    await h.found_departments()
    reader, nobody = h.principal(A, "capacity"), h.principal(A, "nobody")
    await h.person(reader, department=A, grants=screen_grants("connections"))
    await h.person(nobody, department=A)
    console = console_for(h)
    if not await refused(capacity(console.request(), await asking_as(h, nobody))):
        raise CheckFailedError("a person without the Capacity screen was shown the scaling moves")

    # A counter of its own, empty, so the lines nothing measures are the check's whatever this
    # process has been asked since it started.
    with read_load.observing(read_load.ReadLoad()):
        served = await capacity(console.request(), await asking_as(h, reader))
    lines = {(one.move, one.observable): one for one in served.moves}
    wanted = {(one.move.value, one.observable.value) for one in TRIGGERS}
    if set(lines) != wanted or len(served.moves) != len(wanted):
        raise CheckFailedError("the Capacity screen did not serve one line for every trigger")
    for one in served.moves:
        if not one.said.strip():
            raise CheckFailedError("a scaling move said nothing about its state")
        if (one.due is None) != (one.measured is None) and one.observable != "retained_window_days":
            raise CheckFailedError("a scaling move had a due flag beside nothing measured")
        if (
            one.due is None
            and "not measured" not in one.said.lower()
            and "decision" not in one.said
        ):
            raise CheckFailedError("a scaling move with no flag did not say nothing measures it")

    ledger = lines[("partition_the_ledger", "retained_window_days")]
    if ledger.measured != float(METADATA_LEDGER_RETENTION_DAYS) or ledger.threshold != float(
        PARTITION_ANCHOR.value
    ):
        raise CheckFailedError("the ledger move was not held against the retention window")
    if ledger.due is not (PARTITION_ANCHOR.value < METADATA_LEDGER_RETENTION_DAYS):
        raise CheckFailedError("the ledger move was not due for a window longer than a partition")
    host = lines[("split_the_hosts", "profile_does_not_fit")]
    breaches = len(budget_breaches(h.settings.profile))
    if host.measured != float(breaches) or host.due is not (breaches > 0):
        raise CheckFailedError("the host move was not this install's own memory arithmetic")
    for key in (
        ("read_replica", "console_reads_in_flight"),
        ("materialised_reports", "report_p95_ms"),
        ("split_the_hosts", "single_host_failure_is_acceptable"),
    ):
        if lines[key].due is not None:
            raise CheckFailedError("a move nothing measures was served with a due flag")


#: Said where the answer path already takes the interactive pool, so no read could be "inside" it.
NO_HEADROOM_TO_EXCEED: Final = (
    "this install's profile leaves the console no headroom in the interactive pool, so a count of "
    "reads cannot be shown inside it"
)


#: Said where this install's profile has no capacity sizing, so the answer path's peak occupancy
#: and the headroom it leaves the console are not worked out.
NO_SIZING_FOR_THIS_PROFILE: Final = (
    "this install's profile has no capacity sizing, so the headroom the answer path leaves the "
    "console is not worked out and reads in flight cannot be held against it"
)


class _Seconds:
    """A clock the check moves by hand, so a report takes exactly as long as the check says."""

    def __init__(self) -> None:
        self.now = 1_000_000.0

    def __call__(self) -> float:
        return self.now


def _load_with(reads_together: int, reports: int, report_seconds: float) -> read_load.ReadLoad:
    """A counter that saw this many reads in flight together and this many reports this slow."""
    clock = _Seconds()
    load = read_load.ReadLoad(clock)
    started = [load.begin("GET", "/api/v1/agents") for _ in range(reads_together)]
    for one in started:
        load.finish(one)
    for _ in range(reports):
        begun = load.begin("GET", "/api/v1/report/spend")
        clock.now += report_seconds
        load.finish(begun)
    return load


@check(
    leaves=("M36.1.2.4", "M36.1.3.3"),
    sentence=(
        "Console reads and report screens this process has counted reach the Capacity screen: "
        "reads in flight beyond the headroom the answer path leaves make the replica move due and "
        "inside it do not, report screens slower than the threshold make materialised reports "
        "due and faster do not, and a process that has counted too few says it has not measured."
    ),
)
async def counted_reads_and_reports_make_their_scaling_moves_due_or_not(h: Harness) -> None:
    from brain.install_routes import capacity

    await h.found_departments()
    reader = h.principal(A, "load")
    await h.person(reader, department=A, grants=screen_grants("connections"))
    console = console_for(h)

    async def moves(load: read_load.ReadLoad) -> dict[str, Any]:
        with read_load.observing(load):
            served = await capacity(console.request(), await asking_as(h, reader))
        return {one.observable: one for one in served.moves}

    quiet = await moves(read_load.ReadLoad())
    if quiet["console_reads_in_flight"].due is not None or quiet["report_p95_ms"].due is not None:
        raise CheckFailedError("a process that counted nothing was served a due flag for a load")
    headroom = quiet["console_reads_in_flight"].threshold
    threshold = quiet["report_p95_ms"].threshold
    if headroom is None:
        raise CheckNotRunError(NO_SIZING_FOR_THIS_PROFILE)
    if threshold is None:
        raise CheckFailedError("the report move was served with no threshold to be held against")

    if headroom < 1:
        raise CheckNotRunError(NO_HEADROOM_TO_EXCEED)
    over = int(headroom) + 1
    busy = await moves(_load_with(over, 25, threshold / 1000.0 + 1.0))
    if busy["console_reads_in_flight"].due is not True or busy[
        "console_reads_in_flight"
    ].measured != float(over):
        raise CheckFailedError("reads in flight beyond the headroom did not make the replica due")
    if busy["report_p95_ms"].due is not True:
        raise CheckFailedError("report screens slower than the threshold did not make views due")

    calm = await moves(_load_with(int(headroom), 25, threshold / 1000.0 / 2.0))
    if calm["console_reads_in_flight"].due is not False:
        raise CheckFailedError("reads in flight inside the headroom made the replica due")
    if calm["report_p95_ms"].due is not False:
        raise CheckFailedError("report screens inside the threshold made views due")

    thin = await moves(_load_with(0, 5, threshold / 1000.0 + 1.0))
    if thin["report_p95_ms"].due is not None or thin["report_p95_ms"].measured is not None:
        raise CheckFailedError("a handful of reports was read as a 95th percentile")
