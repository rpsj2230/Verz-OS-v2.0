"""Whether a skill can be tried from Ask: one read, one answer for every no.

The handler is called with the library and the switch stood in; the pin a try adds is
`test_try_a_skill.py`'s.

Task ids: M40.7.2
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from brain import member_try_skill_routes
from brain.console.skill_library import Retirement, added, read_package
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.errors import Absent
from brain.core.scope import Scope
from brain.member_try_skill_routes import (
    CANNOT_BE_TRIED,
    MemberTrySkillView,
    can_try_a_skill,
    router,
)
from tests.unit.test_member_starters import skill_text
from tests.unit.test_skill_library import an_approved_skill

NOW = datetime(2999, 1, 1, tzinfo=UTC)
MEMBER = tuple(
    Grant(capability=Capability(value=one), scope=Scope.unrestricted())
    for one in ("read:member.home", "read:member.content")
)


def asked(*, member: bool = True) -> Any:
    return SimpleNamespace(
        caller=SimpleNamespace(principal=SimpleNamespace(id="u_member")),
        reach=EntitlementSet(principal_id="u_member", grants=MEMBER if member else ()),
        now=NOW,
    )


class Library:
    def __init__(self, *skills: Any, retired: tuple[str, ...] = ()) -> None:
        self.skills = {one.digest: one for one in skills}
        self.retired = retired

    async def skill(self, digest: str) -> Any:
        return self.skills.get(digest)

    async def retirements(self, digests: Any) -> Any:
        return {
            d: Retirement(digest=d, retired=True, set_by="u_admin", at=NOW)
            for d in digests
            if d in self.retired
        }


@pytest.fixture
def served(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    held: dict[str, Any] = {"on": True, "library": Library()}

    async def on(state: Any) -> bool:
        return bool(held["on"])

    monkeypatch.setattr(member_try_skill_routes, "trying_a_skill_is_on", on)
    monkeypatch.setattr(member_try_skill_routes, "library_of", lambda request: held["library"])
    return held


def call(digest: str, who: Any | None = None) -> MemberTrySkillView:
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))
    return asyncio.run(can_try_a_skill(request, digest, who or asked()))  # type: ignore[arg-type]


def test_an_approved_unchanged_skill_can_be_tried_and_is_named(served: dict[str, Any]) -> None:
    """The positive case for the refusals below. Delete this and a route that said no to every
    skill passes them all."""
    one = an_approved_skill(skill_text())
    served["library"] = Library(one)
    assert call(one.digest) == MemberTrySkillView(available=True, name=one.name)


def test_every_reason_a_skill_cannot_be_tried_is_one_answer_with_no_name(
    served: dict[str, Any],
) -> None:
    """Switch off, unknown digest, undecided skill and retired skill answer alike. Delete this and
    a different answer for one tells a person which skills exist or are being reviewed."""
    approved = an_approved_skill(skill_text())
    undecided = added(read_package("SKILL.md", skill_text("other").encode()), by="u_a", at=NOW)
    no = MemberTrySkillView(available=False, told=CANNOT_BE_TRIED)

    served["library"] = Library(approved, undecided, retired=(approved.digest,))
    assert call(approved.digest) == no
    assert call(undecided.digest) == no
    assert call("f" * 64) == no
    from dataclasses import replace

    moved = replace(approved, digest="b" * 64)
    served["library"] = Library(moved)
    assert call(moved.digest) == no
    served["library"] = Library(approved)
    served["on"] = False
    assert call(approved.digest) == no


def test_a_caller_without_the_member_grant_is_refused_in_the_pages_one_sentence(
    served: dict[str, Any],
) -> None:
    """The grant is asked before the switch or the library, so the refusal is the same for a
    skill that exists. Delete this and a person with no member grant can ask about skills."""
    one = an_approved_skill(skill_text())
    served["library"] = Library(one)
    with pytest.raises(Absent) as refused:
        call(one.digest, asked(member=False))
    assert str(refused.value) == "trying a skill is not answerable for this caller"


def test_the_answer_is_three_fields_and_the_route_is_one_read() -> None:
    """Whether, a name, a sentence. Delete this and a field beside them could carry a count or the
    skill's body."""
    from fastapi.routing import APIRoute

    assert set(MemberTrySkillView.model_fields) == {"available", "name", "told"}
    routes = [
        (sorted(one.methods or ()), one.path) for one in router.routes if isinstance(one, APIRoute)
    ]
    assert routes == [(["GET"], "/api/v1/me/skills/{digest}/try")]
