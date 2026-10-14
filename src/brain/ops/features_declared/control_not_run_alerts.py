"""The switch on telling the holders of the operations alert that a safety mechanism has not run.

Declared here and not in `brain.ops.features`, by that package's own rule: a feature is a file.
Off until the owner has seen it on his install (decision 221, option C): it is a new message sent
to people unasked, in the chat tool each last used and, when nobody who holds the alert has used
one for a week, by email to the address the install names. The notice itself has no switch, by
`brain.ops.notices.A_NOTICE_THAT_EXISTS_TO_CATCH_MISUSE_HAS_NO_SWITCH`; this is the switch on the
new way of sending it, and is there to be removed once it is proved. See
`brain.control_not_run_told.A_SWITCH_ON_THE_NEW_PATH_IS_NOT_A_SWITCH_ON_THE_NOTICE`.

Task ids: M17.7.2
"""

from __future__ import annotations

from typing import Final

from brain.ops.feature_model import Feature

CONTROL_NOT_RUN_ALERTS: Final = Feature(
    name="control_not_run_alerts",
    title="Tell the people who hold the operations alert when a safety mechanism has not run",
    what=(
        "When a scheduled safety mechanism has not run in the window it is expected to, whoever "
        "holds the operations alert and may open Incidents is told once, in the chat tool they "
        "last used, naming the mechanism and how long it has been. Those who hold the incident "
        "alert are told too when the mechanism is one a person is woken for. When none of them "
        "has used a chat tool in the last seven days, the address on Install, Settings is sent "
        "the same sentence by email."
    ),
    while_off=(
        "Nobody is sent a message about a mechanism that has not run. The Incidents screen and the "
        "System health check still say which guarantees are held, and a message already sent "
        "stays sent."
    ),
    read_by=("brain.control_not_run_told:control_alerts_are_on",),
)
