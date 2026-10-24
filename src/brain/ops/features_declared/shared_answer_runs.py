"""The switch on answering one question once when people of equal reach ask it together.

Declared here and not in `brain.ops.features`, by that package's own rule: a feature is a file.
Off because it holds a request back for the run already answering the same question, which is a
change to when a person's answer arrives, and the owner has not yet seen it work. With it off every
request is answered on its own, as it always was. The rule for who may share a run is the answer
cache's key and nothing looser. See `brain.ops.shared_answers`.

Task ids: M36.2.3.1, M36.2.3.2
"""

from __future__ import annotations

from typing import Final

from brain.ops.feature_model import Feature

SHARED_ANSWER_RUNS: Final = Feature(
    name="shared_answer_runs",
    title="Answer a question once when people with the same reach ask it at the same time",
    what=(
        "When a question is being answered and somebody whose reach is exactly the same asks the "
        "same question of the same agent, the second waits for the first, for up to forty-five "
        "seconds, and is then given the answer the first stored, with its age, instead of paying "
        "for a second model run. A reach that differs in anything is never shared, however close "
        "it is, and a question about now is never shared."
    ),
    while_off=(
        "Every question is answered on its own. A question asked again after the first has been "
        "answered is still served from the answer cache where the install keeps one."
    ),
    read_by=("brain.ops.shared_answers:answers_are_shared",),
)
