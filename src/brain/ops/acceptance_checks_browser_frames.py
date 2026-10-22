"""Install acceptance check: a judge of a finished run is shown no picture taken beside a
credential.

**What this joins.** `verification.admit_frames` decides which pictures a second-pass judge may
see, from a trajectory, the frames and the snapshots in which a bound value was found. Each was
tested with values built by hand. Nothing built them from a run: the trajectory's records carried
no placeholder (the record line has no such field and the replay would not believe a container's
word about it), the frames were lines in a transcript, and the sequences a value was seen in were a
function nobody called. `driver.run_envelope` now returns all three, from what this side sent and
what the runner reported, and this check sends a sealed typing step through it to the product's own
runner and gives the result to `admit_frames` as it stands:

- **The frame beside the opening is admitted** (the page the run chose to go to).
- **The frame from the typing onwards is withheld** until the run opens a declared surface again
  (M19.4.5): a page copies a value out of its own input and draws it anywhere, and the page after
  a login is usually the login's own reply.
- **A frame whose tree held the value is withheld** whatever else is true of it, and the reason
  names the tree and never the value.

The page, the vault and the runner's picture are stand-ins, as in
`acceptance_checks_browser_credentials`: what is not shown is a canvas that draws a value with no
text node behind it, which `admit_frames` says it does not catch.

The check writes nothing and needs no database.

Task ids: M19.4.5
"""

from __future__ import annotations

from typing import Final

from brain.ops.acceptance import CheckFailedError, check
from brain.ops.acceptance_checks_browser_credentials import (
    ORIGIN,
    SECRET,
    _Page,
    _Vault,
    typing_run,
)
from brain.ops.acceptance_run import Harness

#: Where this module's check stands on the Install page, after the card check's (2309).
CHECK_ORDER: Final = 2310

THE_RUN_RETURNED_NO_EVIDENCE: Final = (
    "a run that took pictures returned no frame, no record or no placeholder for the judge"
)
A_FRAME_BESIDE_A_CREDENTIAL_WAS_ADMITTED: Final = (
    "a picture taken after a credential was typed, before the run opened a page again, was admitted"
)
A_CLEAN_FRAME_WAS_WITHHELD: Final = "a picture taken before any credential was typed was withheld"
A_PAGE_OPENED_AFTER_TYPING_WAS_NOT_ADMITTED: Final = (
    "a picture of a page the run chose to open after typing was withheld without a value in it"
)
A_FRAME_WITH_THE_VALUE_IN_ITS_TREE_WAS_ADMITTED: Final = (
    "a picture whose tree held the credential value was admitted"
)
A_REASON_NAMED_THE_VALUE: Final = "a reason for withholding a picture quoted the credential"


@check(
    leaves=("M19.4.5",),
    sentence=(
        "A judge of a finished run is shown the picture of a page the run chose to open and no "
        "picture taken from the typing of a credential until the run opens a page again, and none "
        "whose tree held the value."
    ),
)
async def a_judge_is_shown_no_picture_beside_a_credential(h: Harness) -> None:
    from brain.browsing.driver import Instruction
    from brain.browsing.targets import Verb
    from brain.browsing.verification import (
        CREDENTIAL_TYPED_HERE,
        SECRET_IN_THE_TREE,
        admit_frames,
    )

    reopen = Instruction(surface="login", verb=Verb.OPEN)

    async def admitted(page: _Page) -> tuple[set[int], dict[int, str]]:
        result, _ = await typing_run(h, page, _Vault(h.now), ORIGIN, then=[reopen])
        if len(result.frames) != 3:
            raise CheckFailedError(THE_RUN_RETURNED_NO_EVIDENCE)
        if [one.action.placeholder != "" for one in result.records] != [False, True, False]:
            raise CheckFailedError(THE_RUN_RETURNED_NO_EVIDENCE)
        shown = admit_frames(
            result.trajectory(), result.frames, secret_sequences=result.echoed_sequences
        )
        if any(SECRET in reason for _, reason in shown.withheld):
            raise CheckFailedError(A_REASON_NAMED_THE_VALUE)
        return {one.sequence for one in shown.frames}, dict(shown.withheld)

    # A page that shows nothing back: the opening, the typing and the opening again.
    sequences, withheld = await admitted(_Page())
    if 2 in sequences or withheld.get(2) != CREDENTIAL_TYPED_HERE:
        raise CheckFailedError(A_FRAME_BESIDE_A_CREDENTIAL_WAS_ADMITTED)
    if 1 not in sequences:
        raise CheckFailedError(A_CLEAN_FRAME_WAS_WITHHELD)
    if 3 not in sequences:
        raise CheckFailedError(A_PAGE_OPENED_AFTER_TYPING_WAS_NOT_ADMITTED)

    # A page that shows the value back in its tree once the run has opened it again.
    sequences, withheld = await admitted(_Page(shows_back=True))
    if 3 in sequences or withheld.get(3) != SECRET_IN_THE_TREE:
        raise CheckFailedError(A_FRAME_WITH_THE_VALUE_IN_ITS_TREE_WAS_ADMITTED)
