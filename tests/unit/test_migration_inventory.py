"""The migration register: what was surveyed, what happens to it, what the permissions become."""

from __future__ import annotations

from pathlib import Path

import pytest

from brain.core.entitlement import Capability
from brain.migration.inventory import (
    CAN_BE_CARRIED_ACROSS,
    Agreed,
    Catalogue,
    Decision,
    Disposition,
    Holding,
    Item,
    MigrationError,
    PermissionMapping,
    agree,
    cannot_be_carried,
    catalogue_gaps,
    contradicted,
    mapped_twice,
    undecided,
    unmapped,
)
from brain.status import leaf_sentences

WBS = Path("docs/wbs.json")

ALL_KINDS = frozenset(Holding)


def a_knowledge_item(item_id: str = "k1", **kw: object) -> Item:
    fields: dict[str, object] = {
        "item_id": item_id,
        "holding": Holding.KNOWLEDGE,
        "name": "Leave policy",
    }
    fields.update(kw)
    return Item(**fields)  # type: ignore[arg-type]


def a_full_survey(*items: Item) -> Catalogue:
    return Catalogue(surveyed=ALL_KINDS, items=items)


def a_decision(item_id: str = "k1", disposition: Disposition = Disposition.MIGRATE) -> Decision:
    return Decision(item_id=item_id, disposition=disposition, because="still current")


def a_mapping(old: str = "editor") -> PermissionMapping:
    return PermissionMapping(
        old=old,
        capabilities=(Capability(value="read:client.name"),),
        because="they could open every client record and nothing else",
    )


# ------------------------------------------------------------ the vocabulary is the leaf's
def test_the_kinds_surveyed_are_the_kinds_the_leaf_names() -> None:
    """**The four kinds are M37.1.1.1's list, not a list invented in this module.**

    The leaf says knowledge, prompts, tool definitions and conversation history, and the enum
    says the same four things. Compared against the leaf sentence rather than against a tuple
    written in this file, because a tuple here is written by the same person on the same
    afternoon as the enum and agrees with it for every value either could hold.

    The count is checked as well as the words. Adding a fifth kind without the leaf listing it
    is exactly the drift this catches: the words alone stay green while the survey grows a
    kind nobody agreed to survey.

    Delete this and the register can quietly stop covering something the plan promised."""
    sentence = leaf_sentences(WBS)["M37.1.1.1"]
    listed = sentence.split(":", 1)[1]
    for kind in Holding:
        assert kind.value in listed.casefold(), kind
    assert len(listed.split(",")) == len(Holding)


def test_the_three_dispositions_are_the_leaf_s_three_words() -> None:
    """M37.1.1.2 says migrate, rebuild or retire, and a fourth disposition here would be one
    the plan never agreed to. Read from the leaf for the same reason as above.

    Delete this and a fourth option can be added, which is how "defer" becomes a disposition
    and every deferred item is carried across by the exporter anyway."""
    sentence = leaf_sentences(WBS)["M37.1.1.2"].casefold()
    listed = sentence.split(":", 1)[1]
    for one in Disposition:
        assert one.value in listed, one
    assert len(listed.replace(" or ", ", ").split(",")) == len(Disposition)


def test_only_knowledge_may_be_carried_across_unchanged() -> None:
    """The set is one kind, and this is the assertion that says so out loud.

    Asserted as a set equality rather than by checking that prompts are absent, because
    absence is satisfied by an empty set and an empty set would refuse a migration of
    anything at all while looking like a stricter rule.

    Delete this and `CAN_BE_CARRIED_ACROSS` can grow a kind with every guard below still
    green, because those guards read the set."""
    assert {Holding.KNOWLEDGE} == CAN_BE_CARRIED_ACROSS


# ---------------------------------------------------------------------------- the items
def test_an_item_with_no_id_is_refused() -> None:
    """An item nothing can name is an item no decision can attach to, so it is carried across
    by the exporter and appears on no register.

    Delete this and the blank-id branch is unreachable, which is the shape of defect this
    repository has found forty times: a validator that is written and never run."""
    with pytest.raises(MigrationError, match="no id"):
        a_knowledge_item(item_id="   ")


def test_an_item_with_no_name_is_refused() -> None:
    """A row a person cannot recognise cannot be decided by a person, and deciding it is the
    whole point of the catalogue.

    Delete this and the survey can produce anonymous rows that a screen renders as blanks."""
    with pytest.raises(MigrationError, match="no name"):
        a_knowledge_item(name=" ")


def test_an_item_carrying_a_blank_permission_name_is_refused() -> None:
    """A blank in the permission list becomes a blank in `unmapped`, which reads on a screen
    as a permission called nothing, and somebody maps it.

    Delete this and the mapping register grows a row for the empty string."""
    with pytest.raises(MigrationError, match="blank permission"):
        a_knowledge_item(permissions=("editor", ""))


def test_an_item_valid_in_every_way_is_accepted() -> None:
    """The positive case for all three refusals above. A guard suite with no positive test is
    satisfied by a constructor that refuses everything.

    Delete this and the validators can be tightened until nothing can be catalogued."""
    item = a_knowledge_item(permissions=("editor", "viewer"))

    assert item.item_id == "k1"
    assert item.permissions == ("editor", "viewer")


# ------------------------------------------------------------------------ the catalogue
def test_an_item_of_a_kind_nobody_surveyed_is_refused() -> None:
    """**The central rule of the module.** An item can only have been found by a search, so an
    item of an unsurveyed kind means either the survey record is wrong or the item came from
    somewhere nobody wrote down. Both are worth stopping for, and the alternative is a
    catalogue whose `unsurveyed` list is quietly false.

    Delete this and the survey record and the items can disagree, which makes `unsurveyed`
    report kinds that were in fact looked at and stay silent about kinds that were not."""
    with pytest.raises(MigrationError, match="the survey did not cover"):
        Catalogue(surveyed=frozenset({Holding.KNOWLEDGE}), items=(prompt_item(),))


def test_the_same_item_catalogued_twice_is_refused() -> None:
    """Two rows with one id make `disposition_of` return whichever was written first, and make
    `undecided` satisfied by a decision that only covers one of them.

    Delete this and a merged export from two sources silently halves its own item count."""
    with pytest.raises(MigrationError, match="appears twice"):
        a_full_survey(a_knowledge_item(), a_knowledge_item(name="Leave policy, old"))


def test_an_empty_survey_and_an_unopened_one_are_different_catalogues() -> None:
    """**The distinction the module exists for.** A survey that covered conversations and found
    none, and a survey where nobody opened the conversation history, are the same empty item
    list. One is a system with no history; the other is history a decommission is about to
    delete. Only the surveyed set tells them apart.

    Delete this and the two collapse into one, which is the state every migration spreadsheet
    is already in."""
    looked_and_found_none = Catalogue(surveyed=ALL_KINDS, items=())
    never_looked = Catalogue(surveyed=ALL_KINDS - {Holding.CONVERSATION}, items=())

    assert looked_and_found_none.items == never_looked.items
    assert looked_and_found_none.unsurveyed() == ()
    assert never_looked.unsurveyed() == (Holding.CONVERSATION,)


def test_the_permissions_of_a_catalogue_are_distinct_and_sorted() -> None:
    """The mapping register is built from this list, so a duplicate becomes two rows to map
    and an unsorted list makes the screen reorder itself between exports.

    Delete this and `unmapped` reports the same permission once per item that carries it."""
    catalogue = a_full_survey(
        a_knowledge_item("k1", permissions=("viewer", "editor")),
        a_knowledge_item("k2", permissions=("editor",)),
    )

    assert catalogue.permissions() == ("editor", "viewer")


# -------------------------------------------------------------------------- the decisions
def prompt_item(item_id: str = "p1") -> Item:
    return Item(item_id=item_id, holding=Holding.PROMPT, name="Weekly report prompt")


def test_a_decision_naming_no_item_is_refused() -> None:
    """A disposition with no subject is a row on a screen that looks decided.

    Delete this and `undecided` can be satisfied by a decision that decides nothing."""
    with pytest.raises(MigrationError, match="names no item"):
        Decision(item_id=" ", disposition=Disposition.RETIRE, because="unused")


def test_a_decision_with_no_reason_is_refused() -> None:
    """The reason is the part that is read six months later, and a form with a default
    disposition and no reason field produces exactly this row.

    Delete this and the register answers what was decided and not why, which is the question
    anybody actually asks it."""
    with pytest.raises(MigrationError, match="no reason"):
        Decision(item_id="k1", disposition=Disposition.RETIRE, because="  ")


def test_a_decision_with_an_item_and_a_reason_is_accepted() -> None:
    """The positive case for both refusals above.

    Delete this and `Decision` can be tightened until no decision can be recorded."""
    decided = Decision(item_id="k1", disposition=Disposition.RETIRE, because="nobody has opened it")

    assert decided.disposition is Disposition.RETIRE


def test_an_item_nothing_decided_is_reported_in_catalogue_order() -> None:
    """Catalogue order rather than sorted, because the person working through the list is
    working through the export, and a sorted list makes them find their place twice.

    Delete this and an undecided item is carried or dropped by whatever the exporter does by
    default, which is the decision by omission the module exists to prevent."""
    catalogue = a_full_survey(a_knowledge_item("k2"), a_knowledge_item("k1"))

    assert undecided(catalogue, (a_decision("k1"),)) == ("k2",)


def test_two_people_deciding_one_item_differently_is_a_finding() -> None:
    """Week two of a migration is two people working the same spreadsheet. The finding names
    both dispositions, because the resolution needs to know what the disagreement was.

    Delete this and the conflict resolves silently to whichever row was written last."""
    findings = contradicted(
        (
            a_decision("k1", Disposition.MIGRATE),
            a_decision("k1", Disposition.RETIRE),
        )
    )

    assert findings == ("k1: decided migrate and retire",)


def test_the_same_decision_recorded_twice_is_not_a_finding() -> None:
    """A screen submitted twice is not a disagreement, and refusing it would make the register
    harder to use than the spreadsheet it replaces.

    Delete this and `contradicted` can be written as "more than one decision", which reports
    every double submission as a conflict and trains people to ignore the list."""
    assert contradicted((a_decision("k1"), a_decision("k1"))) == ()


# --------------------------------------------------------------- what may not be carried
def test_a_prompt_set_to_migrate_is_a_finding() -> None:
    """**A prompt was written against a system that narrowed nothing.** Carried across it is a
    prompt written for a ceiling that does not exist here, and the first symptom is a refusal
    it has no wording for.

    Delete this and the leaf's "rebuild rather than import" becomes advice rather than a
    rule, which is what it was in every previous migration."""
    catalogue = a_full_survey(prompt_item())

    findings = cannot_be_carried(catalogue, (a_decision("p1", Disposition.MIGRATE),))

    assert findings == (
        "p1: a prompt is rebuilt or retired, never carried across, because it was written "
        "for a system that narrowed nothing",
    )


def test_a_conversation_set_to_migrate_is_sent_to_the_archive_instead() -> None:
    """A different answer from the prompt one, and the finding says so: history is archived,
    and an import is a decision recorded against the archive.

    Both branches matter because they send somebody to do different things, which is the same
    reason the two role-mismatch sentences in `identity/roles.py` are separate.

    Delete this and a conversation and a prompt get the same sentence, which sends whoever
    reads it to rebuild a conversation."""
    catalogue = a_full_survey(
        Item(item_id="c1", holding=Holding.CONVERSATION, name="Support thread, March")
    )

    findings = cannot_be_carried(catalogue, (a_decision("c1", Disposition.MIGRATE),))

    assert findings == (
        "c1: history is archived rather than imported, and an import is recorded against the "
        "archive by brain.migration.carry",
    )


def test_knowledge_set_to_migrate_is_not_a_finding() -> None:
    """The positive case. A rule that refuses every migration is a rule nobody can satisfy,
    and knowledge is the one kind that carries across as it stands.

    Delete this and `cannot_be_carried` can be written to refuse everything."""
    assert cannot_be_carried(a_full_survey(a_knowledge_item()), (a_decision("k1"),)) == ()


def test_a_prompt_set_to_rebuild_is_not_a_finding() -> None:
    """The other half of the positive case: the rule is about migrating, not about prompts.

    Delete this and `cannot_be_carried` can ignore the disposition and report every prompt in
    the catalogue, which makes the finding list unreadable and gets it switched off."""
    catalogue = a_full_survey(prompt_item())

    assert cannot_be_carried(catalogue, (a_decision("p1", Disposition.REBUILD),)) == ()


# ------------------------------------------------------------------ the permission mapping
def test_a_mapping_naming_no_old_permission_is_refused() -> None:
    """A mapping from nothing satisfies `unmapped` for no permission and sits in the register
    looking like work.

    Delete this and the blank branch is unreachable."""
    with pytest.raises(MigrationError, match="names no old permission"):
        PermissionMapping(old="  ", capabilities=(), because="not used here")


def test_a_mapping_with_no_reason_is_refused() -> None:
    """The mapping from an old permission model onto this one is the step of a migration that
    cannot be inferred, so it is the step that most needs its argument written down.

    Delete this and the register accepts a mapping table with an empty reason column, which
    is what an import script produces."""
    with pytest.raises(MigrationError, match="no reason"):
        PermissionMapping(old="admin", capabilities=(), because="")


def test_a_mapping_explained_by_restating_the_old_name_is_refused() -> None:
    """**"admin becomes admin" is what a hurried afternoon writes**, and it reads in a signed
    document as a decision somebody took. It passes every check that looks for words being
    present, which is precisely the failure this repository has twice found in tests satisfied
    by their own docstrings.

    Delete this and the mapping register can be filled in by copying a column."""
    with pytest.raises(MigrationError, match="restating a name"):
        PermissionMapping(old="Admin", capabilities=(), because=" admin ")


def test_a_mapping_explained_by_restating_a_capability_is_refused() -> None:
    """The other direction, and the likelier one, because the capability is the thing being
    typed at the time.

    Delete this and half the restatement rule is unreachable: the old-name half stays green
    while a reason of "read:client.name" passes."""
    with pytest.raises(MigrationError, match="restating a name"):
        PermissionMapping(
            old="editor",
            capabilities=(Capability(value="read:client.name"),),
            because="read:client.name",
        )


def test_a_mapping_onto_nothing_with_a_real_reason_is_accepted() -> None:
    """**An empty mapping is an answer, not a gap.** An old system's permissions include ones
    this model has no equivalent for, and recording that is the register of what somebody
    loses on cutover day.

    Delete this and the obvious tightening is to require at least one capability, which turns
    every honest "this does not exist here" into a permission mapped onto something close."""
    mapping = PermissionMapping(
        old="billing_admin",
        capabilities=(),
        because="invoicing stays in the finance system and nothing here reaches it",
    )

    assert mapping.capabilities == ()


def test_a_permission_the_catalogue_carries_and_nothing_maps_is_reported() -> None:
    """M37.1.1.3 asks for the mapping to be explicit rather than by assumption, and this is
    the half of "explicit" that a mapping table cannot satisfy by being long. The direction
    is the point. Mapping the permissions somebody remembered leaves the ones
    only the export knows about, and those get mapped at cutover by whoever is at the keyboard.

    Delete this and the mapping register can be complete while the catalogue carries names
    nothing has ever considered."""
    catalogue = a_full_survey(a_knowledge_item(permissions=("editor", "auditor")))

    assert unmapped(catalogue, (a_mapping("editor"),)) == ("auditor",)


def test_a_permission_mapped_in_a_different_case_counts_as_mapped() -> None:
    """Old systems capitalise. "Editor" in the export and "editor" in the mapping table is one
    permission, and reporting it as unmapped sends somebody to write a second mapping for it,
    which `mapped_twice` then reports.

    Delete this and case alone produces a finding and its own duplicate."""
    catalogue = a_full_survey(a_knowledge_item(permissions=("Editor",)))

    assert unmapped(catalogue, (a_mapping("editor"),)) == ()


def test_a_permission_mapped_twice_is_a_finding_even_when_the_mappings_agree() -> None:
    """Unlike a repeated decision, a duplicate mapping is always a finding: it is two people
    having the conversation separately, and the next edit changes one of them.

    Delete this and the mapping table can hold two rows for one permission, and which one
    applies depends on iteration order."""
    assert mapped_twice((a_mapping("editor"), a_mapping("Editor"))) == (
        "editor: mapped 2 times, so the next edit changes one of them",
    )


def test_one_mapping_per_permission_is_not_a_finding() -> None:
    """The positive case.

    Delete this and `mapped_twice` can be written to report every mapping."""
    assert mapped_twice((a_mapping("editor"), a_mapping("auditor"))) == ()


# ---------------------------------------------------------------- the register as a whole
def test_an_unsurveyed_kind_is_the_first_finding_of_all() -> None:
    """Ordering is deliberate: an unsurveyed kind is the only finding that says the register
    is measuring the wrong thing, so it is read before the rows.

    Delete this and the loudest finding sits below fifty item rows, where it is scrolled
    past."""
    catalogue = Catalogue(surveyed=frozenset({Holding.KNOWLEDGE}), items=(a_knowledge_item(),))

    findings = catalogue_gaps(catalogue, (), ())

    assert findings[0].startswith("prompt: nobody looked")
    assert findings[3].startswith("k1: catalogued and nothing decided")


def test_a_register_with_nothing_outstanding_yields_the_agreed_migration() -> None:
    """The positive case for the whole module, and the one that proves the refusals are not
    unconditional.

    Delete this and every guard above can be strengthened until no migration is ever
    agreed."""
    catalogue = a_full_survey(a_knowledge_item(permissions=("editor",)))

    agreed = agree(catalogue, (a_decision("k1"),), (a_mapping("editor"),))

    assert isinstance(agreed, Agreed)
    assert agreed.disposition_of("k1") is Disposition.MIGRATE
    assert agreed.capabilities_for("Editor") == (Capability(value="read:client.name"),)


def test_agreeing_a_register_with_gaps_raises_naming_every_one_at_once() -> None:
    """**A register handed back one finding at a time is worked through one finding at a
    time**, and the person doing that stops when the screen goes green rather than when the
    survey is complete.

    Delete this and `agree` can raise on the first finding, which turns a migration review
    into a queue of one."""
    catalogue = Catalogue(
        surveyed=ALL_KINDS - {Holding.TOOL},
        items=(a_knowledge_item(permissions=("editor",)),),
    )

    with pytest.raises(MigrationError) as raised:
        agree(catalogue, (), ())

    said = str(raised.value)
    assert "tool: nobody looked" in said
    assert "k1: catalogued and nothing decided" in said
    assert "editor: reaches something in the catalogue and maps onto nothing here" in said


def test_asking_the_agreed_register_about_an_item_it_does_not_hold_raises() -> None:
    """A lookup that returned `None` would be rendered as a dash on a screen beside items that
    have a real disposition, and a dash reads as "retire" to everybody who sees it.

    Delete this and the branch is unreachable and the screen grows a fourth disposition
    nobody declared."""
    agreed = agree(a_full_survey(a_knowledge_item()), (a_decision("k1"),), ())

    with pytest.raises(MigrationError, match="not in the catalogue"):
        agreed.disposition_of("k404")


def test_asking_the_agreed_register_about_a_permission_it_does_not_hold_raises() -> None:
    """The same argument for the mapping side: an empty tuple would be indistinguishable from
    a permission deliberately mapped onto nothing, which is a real and different answer.

    Delete this and "we decided this maps to nothing" and "we never heard of this" become the
    same result."""
    agreed = agree(a_full_survey(a_knowledge_item()), (a_decision("k1"),), ())

    with pytest.raises(MigrationError, match="not a permission the catalogue carries"):
        agreed.capabilities_for("auditor")
