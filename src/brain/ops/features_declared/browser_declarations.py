"""The switch on declaring the websites a browser may be pointed at, and signing for it.

Declared here and not in `brain.ops.features`, by that package's own rule: a feature is a file.
Off until the owner has seen it on his install, because it is the place a person says which
websites an agent's browser may open and which controls it may press, and the place a person signs a
permission for a surface's writes to run with nobody looking. Nothing declared here opens a
browser: `browser_runs` is the switch for that, and a declaration with that off is a record.

Retiring a declaration and revoking a signed permission are never behind this switch, for the
reason `brain.ops.features.A_SWITCH_TURNED_OFF_DOES_NOT_TRAP_WHAT_IT_OPENED` gives: a permission
signed while this was on can always be taken back with it off.

Task ids: M19.2.4, M19.6.7, M19.7.3, M19.9.7
"""

from __future__ import annotations

from typing import Final

from brain.ops.feature_model import Feature

BROWSER_DECLARATIONS: Final = Feature(
    name="browser_declarations",
    title="Declare websites for agents' browsers and sign exceptions",
    what=(
        "An administrator of browsers may declare a website an agent's browser may be pointed at, "
        "with the pages, the fields a read returns, the one control each write is done on and "
        "the vault reference of a sign-in. They may also sign an exception for one page's writes "
        "to run without waiting for a person, and an exemption for a skill to drive a website that "
        "has an API, each with a reason and an end within ninety days. Every signature is in the "
        "audit trail."
    ),
    while_off=(
        "No website can be declared and no exception or exemption signed. What is declared stays, "
        "and a declaration can still be retired and a signed permission revoked."
    ),
    read_by=("brain.browser_routes:declarations_are_on",),
)
