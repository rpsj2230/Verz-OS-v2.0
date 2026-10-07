"""The install acceptance check for the names this company's people have: Chinese, Malay and Tamil.

`brain.ops.acceptance_checks_deployment.singapore_identifiers_are_scrubbed_by_their_kind` proves
the identifiers. A name has no checksum and no fixed shape, and the scrub's own account of it is
that a half-redacted name identifies a person as well as a whole one does and looks handled
(`brain.ops.pii`): the English name recogniser finds `Abdullah` in `Nur Aisyah binti Abdullah` and
reports success. So the local recognisers are built around the connectors, initials and script
that mark where a name starts and ends, and this check asks them, in the worker, of one made-up
name in each of the three forms the leaf names.

**The recognisers are the ones this process runs, and nothing here is a stand-in.** They are
regular expressions in `brain.ops.pii.detect`, which the egress step runs before any text leaves
(`brain.ops.egress`), so what is asked is the installed code on the installed interpreter. Each
sentence is put through `scrub` and the check reads what is left: no part of the name, and its own
kind in its place. Names are made up for the run from syllables that belong to nobody
(`brain.ops.acceptance_checks_names.A_NAME_NOBODY_HAS`), so a result names no person.

**What is not claimed, and is the model's.** A romanised Chinese name with no connector, such as
three capitalised words, has no pattern that does not also match the start of every sentence naming
a product, and `brain.ops.pii` says so and leaves it to the entity model (M32.2.1.2), which this
install runs only once it runs a model server. The check asserts nothing about such a name in either
direction, because asserting that it is found would be false and asserting that it is missed would
make the gap a requirement.

Task ids: M32.2.1.4
"""

from __future__ import annotations

import secrets
from typing import Final

from brain.ops.acceptance import CheckFailedError, check
from brain.ops.acceptance_run import Harness

#: Where this module's checks stand on the Install page. See
#: `brain.ops.acceptance.A_CHECK_MODULE_IS_FOUND_AND_PLACES_ITSELF`.
CHECK_ORDER: Final = 710

#: Why the names are generated.
A_NAME_NOBODY_HAS: Final = (
    "Each name is assembled for the run from syllables chosen at random, so the sentence a result "
    "could quote names nobody, and two runs never send the recognisers the same name."
)

#: The scrub's kinds, restated so a rename in the product fails this check rather than moving it.
CJK: Final = "person_name_cjk"
PATRONYMIC: Final = "person_name_patronymic"
INITIALLED: Final = "person_name_initialled"

#: Han characters, in no name anybody holds: rare enough that no two runs meet a real person's.
HAN_SYLLABLES: Final = "渺澜翎湛琛翊珺骁璟瑄"
MALAY_GIVEN: Final = ("Zulaikha", "Qistina", "Haziqah", "Nurfarah", "Aliyyah")
MALAY_FATHER: Final = ("Khairuddin", "Mazlan", "Rosdi", "Hamdan", "Suhaimi")
TAMIL_SURNAME: Final = ("Thevarajan", "Kandiah", "Sivalingam", "Ratnasingam", "Pathmanathan")

NOT_FOUND: Final = "a name the scrub is built to find was left in the text it sent"
WRONG_KIND: Final = (
    "a name was found as a kind other than its own, so its label tells a reader wrong"
)
OVER_REACHED: Final = "the scrub took words out of a sentence that carried no name"
NOT_A_NAME_CHANGED: Final = "text carrying no name was altered by the scrub"


def _pick(options: tuple[str, ...]) -> str:
    return options[secrets.randbelow(len(options))]


@check(
    leaves=("M32.2.1.4",),
    sentence=(
        "A made-up Chinese name in Han characters, a Malay name with its patronymic and a Tamil "
        "name with its initial and a/l, each in a sentence, are found whole by the recognisers "
        "this install runs and replaced by their own kind with nothing of the name left; a "
        "sentence naming nobody is left as it was. Romanised Chinese names with no connector are "
        "the entity model's and are not claimed."
    ),
)
async def chinese_malay_and_tamil_names_are_scrubbed_whole(h: Harness) -> None:
    from brain.ops.pii import detect, scrub

    del h
    han = "".join(secrets.choice(HAN_SYLLABLES) for _ in range(3))
    malay = f"{_pick(MALAY_GIVEN)} binti {_pick(MALAY_FATHER)}"
    initial = chr(ord("A") + secrets.randbelow(26))
    tamil = f"{initial}. {_pick(TAMIL_SURNAME)} a/l {_pick(TAMIL_SURNAME)}"
    cases = (
        (han, CJK, f"Please call {han} about the invoice."),
        (malay, PATRONYMIC, f"{malay} signed off the quotation."),
        (tamil, INITIALLED, f"Ask {tamil} for the file."),
    )
    for name, kind, sentence in cases:
        found = detect(sentence)
        if not found:
            raise CheckFailedError(NOT_FOUND)
        kinds = {one.kind.value for one in found}
        # A Tamil name with a connector is two spans of two kinds side by side, any other one.
        if kind not in kinds or not kinds <= {kind, PATRONYMIC}:
            raise CheckFailedError(WRONG_KIND)
        scrubbed = scrub(sentence)
        for part in (*name.replace(".", " ").replace("/", " ").split(), name):
            if len(part) > 1 and part in scrubbed:
                raise CheckFailedError(NOT_FOUND)
        if f"[{kind}]" not in scrubbed:
            raise CheckFailedError(WRONG_KIND)
    plain = "The renewal falls due on the first Monday of the month."
    if detect(plain):
        raise CheckFailedError(OVER_REACHED)
    if scrub(plain) != plain:
        raise CheckFailedError(NOT_A_NAME_CHANGED)
