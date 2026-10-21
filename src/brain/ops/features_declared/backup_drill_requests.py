"""The switch on asking the server for a restore rehearsal from the Recovery screen.

Declared here and not in `brain.ops.features`, by that package's own rule: a feature is a file.
Off until the owner has answered needs-rupash item 235, which asks what may start a backup drill now
that nothing the product runs holds the access to start a container. The answer decides whether
this button means anything: under option A the rehearsal is done by hand on the server and a button
would ask for something nobody is listening for, under option B a service the installer sets up on
the server does it, and under option C the worker does it inside the database server. **Turning
this on is the owner's answer to that item** and it should be turned on only on an install where
`brain-drill-service` is running, because a request nothing reads waits in the bucket for ever and
the screen would go on saying it was asked.

What the switch holds back is the one new write: putting a small request object in the backup
bucket, where the application's key could already write. Reading the screen, the copies, the
records and what the last rehearsal found is not behind it, and turning it off again leaves a
request already made in place for the service to answer.

Task ids: M30.3.9
"""

from __future__ import annotations

from typing import Final

from brain.ops.feature_model import Feature

BACKUP_DRILL_REQUESTS: Final = Feature(
    name="backup_drill_requests",
    title="Ask the server for a restore rehearsal from the Recovery screen",
    what=(
        "An administrator holding the install authority may press Start a rehearsal on the Backup "
        "and recovery screen. The press puts a request beside the copies, and the drill service "
        "on the server, when the installer set one up, reads it within about ten minutes, loads "
        "your newest copy into a scratch database, asks it the three questions and writes the "
        "record the screen then reads. The product itself starts nothing."
    ),
    while_off=(
        "The screen still shows the copies, the last rehearsal and whether one is owed, and "
        "says a rehearsal is done on the server. A request already made is left for the service "
        "to answer, and nobody can make another."
    ),
    read_by=(
        "brain.rehearsal_routes:ask_for_a_rehearsal",
        "brain.install_routes:recovery",
    ),
)
