"""The peak load run against this install (M22.3.3), which spends the install's own model calls.

Off because a run is a spend and a load: it asks the install's real answer route two questions a
second for ten minutes at the stated peak, and most of what it asks is answered by the model the
install is configured with. Nothing starts one by itself. `python -m brain.ops.load_peak` is a
command a person runs in the application's container, it refuses before sending anything while
this is off, and `brain.ops.load_run_store` is where the switch is read.

Task ids: M22.3.3
"""

from __future__ import annotations

from typing import Final

from brain.ops.feature_model import Feature

LOAD_TEST: Final = Feature(
    name="load_test",
    title="Allow the peak load test to be run against this install",
    what=(
        "An administrator may run the peak load test from the application's container. It asks "
        "the install's own answer route, as the test people set aside for it and nobody else, at "
        "the rate this install's profile states for its busiest minute, and keeps each lane's "
        "measured 95th percentile and success rate against the service levels. It spends model "
        "calls, it never sends more than the number its operator confirms, and it stops sending "
        "if the install starts refusing most of what it is asked."
    ),
    while_off=(
        "The command refuses before it sends anything. The install's checks still prove the "
        "machinery cheaply, with a short run inside a transaction that is rolled back and no "
        "model called."
    ),
    read_by=("brain.ops.load_run_store:load_test_is_on",),
)
