"""The switch on starter questions built from what a department's connected sources hold.

Off because it makes Ask suggest questions from the install's own data instead of from three fixed
templates. The suggestion is only ever about a kind of record the person already reaches in their
own department, but a suggestion built from data is a statement about what is indexed, and an
install should choose the day Ask starts making it. `brain.welcome_routes` asks the switch; the
fixed templates it has always offered are not behind it.

Task ids: M34.1.1.2, M34.1.1.3
"""

from __future__ import annotations

from typing import Final

from brain.ops.feature_model import Feature

STARTER_QUESTIONS_FROM_DATA: Final = Feature(
    name="starter_questions_from_data",
    title="Suggest first questions built from what a person's department has connected",
    what=(
        "Before a person has asked anything, Ask offers up to three more questions about the "
        "kinds of record their own department's connected sources actually hold and that they "
        "may read, each saying which system to open to check the answer against. A kind of "
        "record the person may not read is never suggested, and none is suggested for a source "
        "a person cannot check in its own interface."
    ),
    while_off=(
        "Ask offers only the fixed starter questions it always offered. Nothing a person asked is "
        "affected."
    ),
    read_by=("brain.welcome_routes:starter_from_data_is_on",),
)
