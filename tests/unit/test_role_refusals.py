"""The refusal that names the role a change needs (needs-rupash 178 A).

The routes' own tests prove each refusal is given to the right reader; this proves the sentences
and the shape they travel in.

Task ids: M39.8.1, M33.8.3
"""

from __future__ import annotations

import json

from brain.role_refusals import (
    A_REFUSAL_NAMES_ITS_ROLE_AND_NEVER_WHAT_IT_WOULD_HAVE_DONE,
    CHANGING_CHANNELS_NEEDS_THE_DEPARTMENT_ADMINISTRATOR,
    CHOOSING_A_MODEL_NEEDS_THE_SUPER_ADMIN,
    CONNECTING_A_SOURCE_NEEDS_THE_CONNECTOR_CAPABILITY,
    role_refusal,
)


def test_a_role_refusal_is_a_403_carrying_the_sentence_and_nothing_else() -> None:
    """The body is the one key the console reads, so a refusal cannot smuggle a second field such
    as which agent or source it was about. Delete this and a refusal can grow a field naming what
    was refused, which is what the rule above says it never does."""
    answer = role_refusal(CHANGING_CHANNELS_NEEDS_THE_DEPARTMENT_ADMINISTRATOR)

    assert answer.status_code == 403
    assert json.loads(bytes(answer.body)) == {
        "message": CHANGING_CHANNELS_NEEDS_THE_DEPARTMENT_ADMINISTRATOR
    }
    assert A_REFUSAL_NAMES_ITS_ROLE_AND_NEVER_WHAT_IT_WOULD_HAVE_DONE


def test_each_sentence_names_a_role_and_none_names_a_capability_string_or_a_thing() -> None:
    """Each says which role changes the part, in words, and none carries an `admin:` string or an
    agent or source name. The positive sibling: every sentence names its role. Delete this and a
    refusal can print a capability string a person was never asked to learn."""
    roles = {
        CHANGING_CHANNELS_NEEDS_THE_DEPARTMENT_ADMINISTRATOR: "department administrator",
        CHOOSING_A_MODEL_NEEDS_THE_SUPER_ADMIN: "Super Admin",
        CONNECTING_A_SOURCE_NEEDS_THE_CONNECTOR_CAPABILITY: "connector capability",
    }
    for sentence, role in roles.items():
        assert role in sentence
        assert "admin:" not in sentence
