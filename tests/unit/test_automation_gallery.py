"""The automation gallery's decisions: what a template may hold, who may install one, what the
person confirms, and what one confirmed install produces.

Everything here is `brain.console.automation_gallery` with no server and no database. The HTTP
order is `tests/unit/test_automation_gallery_routes.py`, and the row, the registry entry read back
out of it and the ledger entry its trigger appends are `tests/unit/test_agent_automation_store.py`.

**Every refusal has a sibling proving the permitted case**, which is CLAUDE.md's rule about a guard
tested only by its refusals. A function refusing every install would satisfy the refusals and none
of the siblings.

Task ids: M39.6.1.3
"""

from __future__ import annotations

import inspect
import re
from dataclasses import dataclass, replace
from datetime import UTC, datetime

import pytest

from brain.agents.model import AgentAudience, AgentAuthority, AgentRecord, entitlement_ceiling
from brain.audit.ledger import FIELD_NAME
from brain.console import agent_automations
from brain.console import automation_gallery as gallery_module
from brain.console.agent_automations import (
    Automation,
    AutomationSurfaceError,
    RegistryEntry,
    may_change_schedule,
    register,
)
from brain.console.automation_gallery import (
    AUTOMATION_AUTHORITY,
    AUTOMATION_PART,
    BUILT_IN,
    GALLERY_TAB,
    INSTALL_REASON,
    AutomationTemplate,
    Cadence,
    Every,
    GalleryError,
    Installation,
    NotConfirmedError,
    gallery,
    install,
    install_row,
    may_install,
    may_open_gallery,
    new_automation_id,
    preview,
    template_by_id,
)
from brain.console.reads import Plane, plane_capability
from brain.console.workspace import Tab, intersections_in, tab
from brain.core.entitlement import Capability, EntitlementSet, Grant
from brain.core.principal import Employment, Principal, PrincipalKind
from brain.core.scope import Clause, Op, Scope
from brain.gate.admission import Assurance, admit
from brain.gate.context import Channel
from brain.identity.first_administrator import ADMINISTRATION
from brain.knowledge.visibility import Visibility
from brain.ops.automation import flow_reach
from brain.ops.automation_owner import AUTOMATION_ASSURANCE, AUTOMATION_CHANNEL, AUTOMATION_ID
from brain.ops.jobs import reach_carrying_fields

AGENT = "quote_helper"
INSTALLER = "u_installer"
TEMPLATE = BUILT_IN[0]

#: Far from any plausible wall clock, for CLAUDE.md's reason about a fixture that is a clock.
LATER = datetime(2999, 1, 4, 9, 0, tzinfo=UTC)

EVERYWHERE = Scope.unrestricted()
TAB_READ = tab(Tab.AUTOMATIONS).read.requires
CONFIGURATION = plane_capability(Plane.CONFIGURATION)
EXISTENCE = plane_capability(Plane.EXISTENCE)


def grant(capability: Capability | str, scope: Scope = EVERYWHERE) -> Grant:
    value = capability if isinstance(capability, Capability) else Capability(value=capability)
    return Grant(capability=value, scope=scope)


def reach(*grants: Grant, principal: str = INSTALLER) -> EntitlementSet:
    return EntitlementSet(principal_id=principal, grants=grants)


def on_agent(agent_id: str) -> Scope:
    return Scope(clauses=(Clause(field="agent_id", op=Op.EQ, value=agent_id),))


def person(principal_id: str = INSTALLER) -> Principal:
    return Principal(
        id=principal_id,
        kind=PrincipalKind.HUMAN,
        employment=Employment.STAFF,
        display_name=f"Person {principal_id}",
    )


def an_agent(*capabilities: str, agent_id: str = AGENT) -> AgentRecord:
    """One agent whose ceiling admits exactly these capabilities, company-wide."""
    return AgentRecord(
        agent_id=agent_id,
        display_name="Quote helper",
        persona="Answers pricing questions.",
        audience=AgentAudience(level=Visibility.COMPANY, owner_id="u_steward"),
        authority=AgentAuthority(capabilities=tuple(Capability(value=one) for one in capabilities)),
        created_by="u_builder",
    )


def installer_reach() -> EntitlementSet:
    """An installer holding two reads, a write and the authority, company-wide."""
    return reach(
        grant("read:client.name"),
        grant("read:invoice.total"),
        grant("write:ticket"),
        grant(AUTOMATION_AUTHORITY),
    )


# ------------------------------------------------------------------ the catalogue


def test_the_product_ships_templates_each_one_once_and_each_one_findable_by_its_id() -> None:
    """The Automations tab is marked populated for every agent on the strength of this gallery.
    Delete this and `BUILT_IN` can be emptied, drawing a heading over nothing, or carry one id
    twice, so an install pins one of two different templates under one name."""
    ids = [one.template_id for one in BUILT_IN]

    assert BUILT_IN
    assert len(ids) == len(set(ids))
    assert all(
        template_by_id(one) is next(t for t in BUILT_IN if t.template_id == one) for one in ids
    )
    assert template_by_id("no_such_template") is None


def test_no_built_in_template_names_a_company_a_domain_an_address_or_a_person() -> None:
    """`A_GENERIC_OUTCOME_IS_PRODUCT_CONTENT_AND_A_COMPANYS_OWN_IS_CONFIGURATION`, as far as text
    can hold it. Delete this and a template carrying one company's channel, domain or mailbox can
    ship to every install; the sibling check proves the pattern would find one."""
    company_detail = re.compile(r"@|://|\b[a-z0-9-]+\.(?:com|net|org|io|co|sg|uk|my)\b", re.I)
    texts = [text for one in BUILT_IN for text in (one.name, one.summary, one.guards, one.task)]

    assert company_detail.search("post the numbers to finance@example.com")
    assert not [text for text in texts if company_detail.search(text)]


def test_a_template_has_no_field_that_could_hold_a_grant() -> None:
    """`A_TEMPLATE_HAS_NOWHERE_TO_HOLD_A_GRANT`, asked of the class by the check `brain.ops.jobs`
    asks of a job row. Delete this and a `capabilities` field can be added to a template, and a
    gallery install becomes a way to widen whoever presses it. The sibling class proves the check
    is not vacuous."""

    @dataclass(frozen=True)
    class Widening:
        template_id: str
        needs: tuple[Capability, ...]

    assert reach_carrying_fields(AutomationTemplate) == ()
    assert reach_carrying_fields(Widening) == ("needs",)


@pytest.mark.parametrize(
    ("change", "refused"),
    [
        ({"template_id": "No-Caps"}, "is not a template id"),
        ({"version": 0}, "versions start at one"),
        ({"name": "When a form arrives, send the webhook"}, "named badly"),
        ({"summary": " "}, "needs a summary"),
        ({"summary": "x" * 241}, "needs a summary"),
        ({"task": "work_summary"}, "is not an automation task"),
        ({"guards": "it matters"}, "does not say what breaks"),
    ],
)
def test_a_template_that_could_not_be_installed_honestly_is_refused_at_construction(
    change: dict[str, object], refused: str
) -> None:
    """Each rule the installed automation or its registry entry would otherwise refuse later, or
    that a card would draw wrong. Delete this and a template with a wiring name or no sentence
    about what breaks ships, and its install fails at the constructor after the person confirmed.
    The built-in templates constructing at import is the sibling."""
    fields = {
        "template_id": TEMPLATE.template_id,
        "version": TEMPLATE.version,
        "name": TEMPLATE.name,
        "summary": TEMPLATE.summary,
        "task": TEMPLATE.task,
        "cadence": TEMPLATE.cadence,
        "guards": TEMPLATE.guards,
    }
    fields.update(change)

    with pytest.raises(GalleryError, match=refused):
        AutomationTemplate(**fields)  # type: ignore[arg-type]


def test_a_cadence_says_its_zone_and_names_a_day_exactly_when_it_is_weekly() -> None:
    """Delete this and "every day on Friday" can be written, or an hour read in whichever zone the
    reader happens to sit in."""
    assert Cadence(every=Every.WEEK, hour_utc=15, weekday=4).words() == "every Friday at 15:00 UTC"
    assert Cadence(every=Every.DAY, hour_utc=7).words() == "every day at 07:00 UTC"
    assert Cadence(every=Every.WEEKDAY, hour_utc=9).words() == "every weekday at 09:00 UTC"
    for refused in (
        {"every": Every.DAY, "hour_utc": 24},
        {"every": Every.WEEK, "hour_utc": 9},
        {"every": Every.DAY, "hour_utc": 9, "weekday": 1},
        {"every": Every.WEEK, "hour_utc": 9, "weekday": 7},
    ):
        with pytest.raises(GalleryError):
            Cadence(**refused)  # type: ignore[arg-type]


# ------------------------------------------------------------------ the gallery


def test_the_gallery_is_every_template_by_name_whatever_order_it_arrives_in() -> None:
    """Delete this and two readings of an unchanged catalogue can differ, which reads as templates
    having come and gone."""
    expected = sorted(BUILT_IN, key=lambda one: (one.name, one.template_id))

    assert [card.template for card in gallery({})] == expected
    assert [card.template for card in gallery({}, catalogue=BUILT_IN[::-1])] == expected


def test_a_card_is_marked_with_the_readers_own_install_and_with_nothing_else() -> None:
    """Delete this and a card can drop the automation the reader already has, so they install a
    second one, or carry a mark from a mapping the store never read for them."""
    cards = {card.template.template_id: card for card in gallery({TEMPLATE.template_id: "auto_a"})}

    assert cards[TEMPLATE.template_id].installed_as == "auto_a"
    assert all(
        card.installed_as is None for key, card in cards.items() if key != TEMPLATE.template_id
    )


# ------------------------------------------------------------------ who may do which part


def test_the_gallery_opens_for_a_reader_of_the_automations_tab_on_both_counts() -> None:
    """`brain.console.reads.permitted` over the tab's own read. Delete this and the gallery can be
    opened by a reader holding the queue grant without the configuration plane, or refused to one
    holding both."""
    assert GALLERY_TAB is Tab.AUTOMATIONS
    assert may_open_gallery(reach(grant(TAB_READ), grant(CONFIGURATION)))
    assert not may_open_gallery(reach(grant(TAB_READ), grant(EXISTENCE)))
    assert not may_open_gallery(reach(grant(CONFIGURATION)))


def test_installing_needs_the_authority_in_a_scope_that_matches_this_agent() -> None:
    """The authority check. Delete this and an install is admitted with no authority, or with an
    authority written for another department's agents."""
    assert may_install(AGENT, TEMPLATE, reach(grant(AUTOMATION_AUTHORITY)))
    assert may_install(AGENT, TEMPLATE, reach(grant(AUTOMATION_AUTHORITY, on_agent(AGENT))))
    assert not may_install(AGENT, TEMPLATE, reach(grant(AUTOMATION_AUTHORITY, on_agent("other"))))
    assert not may_install(AGENT, TEMPLATE, reach(grant(TAB_READ), grant(CONFIGURATION)))


def test_the_install_scope_is_the_scope_scheduled_work_is_read_under() -> None:
    """Delete this and a grant written for one agent's automations reads one way on the listing and
    another here, because the install matched a row the listing does not build."""
    shown = preview(TEMPLATE, an_agent(), installer=person(), installer_reach=installer_reach())
    made = install(shown, confirmation=shown.confirmation, automation_id="auto_one")

    assert install_row(AGENT, TEMPLATE, INSTALLER) == agent_automations._scope_row(made.automation)


def test_the_authority_is_an_administrative_capability_the_first_administrator_holds() -> None:
    """Delete this and the authority can become a `write:` capability a password-only session
    carries, or be missing from the first administrator, so nobody on a fresh install can install
    anything."""
    assert AUTOMATION_AUTHORITY.value.startswith("admin:")
    assert AUTOMATION_AUTHORITY.value in ADMINISTRATION


def test_a_session_without_a_second_factor_cannot_install_whatever_it_holds() -> None:
    """`brain.gate.admission` withholds `admin:` from anything below a strong session, so the
    reach a password-only console session carries has no authority. Delete this and the authority
    can be renamed to a verb admission lets through."""
    held = installer_reach()

    assert may_install(AGENT, TEMPLATE, admit(held, Channel.CONSOLE, Assurance.STRONG))
    assert not may_install(AGENT, TEMPLATE, admit(held, Channel.CONSOLE, Assurance.AUTHENTICATED))


# ------------------------------------------------------------------ the preview


def test_the_reach_shown_is_flow_reach_of_the_installer_as_an_automation_and_the_ceiling() -> None:
    """The no-widening property. The automation reaches what the installer may read that the
    agent's ceiling also allows: not the ceiling's read the installer lacks, not the installer's
    read the ceiling lacks, and no write or authority at all, because an automation is admitted
    at bound assurance. Delete this and the preview can show, and the install can confirm, a reach
    wider than the one intersection allows."""
    # The ceiling names the installer's write too, so only the admission of an automation at
    # bound assurance keeps it out: a mutation that skipped `admit` survived until it did.
    agent = an_agent("read:client.name", "read:project.hours", "write:ticket")
    shown = preview(TEMPLATE, agent, installer=person(), installer_reach=installer_reach())
    expected = flow_reach(
        admit(installer_reach(), AUTOMATION_CHANNEL, AUTOMATION_ASSURANCE),
        entitlement_ceiling(agent),
    )

    assert shown.reach == expected
    assert "read:client.name" in shown.capabilities
    assert "read:project.hours" not in shown.capabilities
    assert "read:invoice.total" not in shown.capabilities
    assert "write:ticket" in (grant.capability.value for grant in entitlement_ceiling(agent).grants)
    assert not [one for one in shown.capabilities if not one.startswith("read:")]


def test_this_module_intersects_nothing_itself() -> None:
    """Delete this and a second implementation of the platform's central rule can be written here,
    beside the one `flow_reach` calls."""
    assert intersections_in(inspect.getsource(gallery_module)) == ()


def test_a_preview_is_refused_a_reach_that_is_not_the_installers() -> None:
    """Delete this and a person can be shown, and confirm, a reach computed from somebody else's
    grants."""
    with pytest.raises(GalleryError, match="was handed the reach of"):
        preview(
            TEMPLATE,
            an_agent("read:client.name"),
            installer=person(),
            installer_reach=reach(grant("read:client.name"), principal="u_someone_else"),
        )


def test_an_install_starts_paused_because_its_principal_could_not_approve_its_schedule() -> None:
    """`AN_INSTALL_CANNOT_BE_THE_WAY_ROUND_A_GATED_SCHEDULE`, held against M39.6.2.2's own rule
    rather than restated: the installer may not approve any next run for what they installed, and
    so the install has none. Delete this and the gallery becomes the way round a gated change."""
    shown = preview(TEMPLATE, an_agent(), installer=person(), installer_reach=installer_reach())
    made = install(shown, confirmation=shown.confirmation, automation_id="auto_one")

    assert shown.next_run_at is None
    assert made.automation.paused and made.entry.next_run_at is None
    assert may_change_schedule(made.automation, becomes=LATER, approved_by=INSTALLER) is False
    assert may_change_schedule(made.automation, becomes=LATER, approved_by="u_other") is True


def test_the_confirmation_moves_with_every_fact_the_person_was_shown() -> None:
    """A stale confirmation is refused because it no longer matches. Delete this and a preview
    taken before a grant was removed, a ceiling was narrowed or the template moved confirms the
    install after, and the person agreed to something that is not what was written."""
    agent = an_agent("read:client.name", "read:invoice.total")
    base = preview(TEMPLATE, agent, installer=person(), installer_reach=installer_reach())
    again = preview(TEMPLATE, agent, installer=person(), installer_reach=installer_reach())
    fewer_grants = preview(
        TEMPLATE,
        agent,
        installer=person(),
        installer_reach=reach(grant("read:client.name"), grant(AUTOMATION_AUTHORITY)),
    )
    narrower_agent = preview(
        TEMPLATE,
        an_agent("read:invoice.total"),
        installer=person(),
        installer_reach=installer_reach(),
    )
    moved_template = preview(
        replace(TEMPLATE, version=TEMPLATE.version + 1),
        agent,
        installer=person(),
        installer_reach=installer_reach(),
    )
    other_agent = preview(
        TEMPLATE,
        an_agent("read:client.name", "read:invoice.total", agent_id="other_agent"),
        installer=person(),
        installer_reach=installer_reach(),
    )

    assert re.fullmatch(r"[0-9a-f]{64}", base.confirmation)
    assert base.confirmation == again.confirmation
    assert (
        len(
            {
                one.confirmation
                for one in (base, fewer_grants, narrower_agent, moved_template, other_agent)
            }
        )
        == 5
    )


# ------------------------------------------------------------------ the install


def test_one_confirmed_install_is_the_automation_and_its_registry_entry_together() -> None:
    """M39.6.1.3's install, the positive case every refusal below is measured against. The
    automation runs as the installer, carries the template's outcome and task, and its registry
    entry is the one `register` derives with the template's sentence. Delete this and the refusals
    are satisfied by an install that never produces anything."""
    shown = preview(TEMPLATE, an_agent(), installer=person(), installer_reach=installer_reach())

    made = install(shown, confirmation=shown.confirmation, automation_id="auto_one")

    assert made.automation == Automation(
        automation_id="auto_one",
        agent_id=AGENT,
        name=TEMPLATE.name,
        runs_as=person(),
        task=TEMPLATE.task,
        next_run_at=None,
    )
    assert made.entry == register(made.automation, guards=TEMPLATE.guards)
    assert (made.template_id, made.template_version, made.installed_by) == (
        TEMPLATE.template_id,
        TEMPLATE.version,
        INSTALLER,
    )


def test_an_install_whose_confirmation_is_not_what_would_be_installed_now_is_refused() -> None:
    """The confirmation refusal. Delete this and an install is written without anybody having seen
    what it would do, or after what they saw had changed."""
    agent = an_agent("read:client.name")
    shown = preview(TEMPLATE, agent, installer=person(), installer_reach=installer_reach())
    stale = preview(TEMPLATE, an_agent(), installer=person(), installer_reach=installer_reach())

    for refused in ("", "0" * 64, stale.confirmation):
        with pytest.raises(NotConfirmedError):
            install(shown, confirmation=refused, automation_id="auto_one")


def test_an_install_never_runs_as_the_agent_it_is_installed_onto() -> None:
    """`AN_AUTOMATION_RUNNING_AS_ITSELF_IS_A_GRANT_NOBODY_CAN_REVOKE`, reached through an install.
    Delete this and a principal named like the agent, or the agent's ceiling id, installs an
    automation nobody can revoke. The sibling is every install above, which runs as a person."""
    for itself in (AGENT, f"agent:{AGENT}"):
        installer = person(itself)
        shown = preview(
            TEMPLATE,
            an_agent(),
            installer=installer,
            installer_reach=reach(grant(AUTOMATION_AUTHORITY), principal=itself),
        )
        with pytest.raises(AutomationSurfaceError, match="the agent it belongs to"):
            install(shown, confirmation=shown.confirmation, automation_id="auto_one")


def test_an_automation_id_is_one_a_credential_can_carry_and_the_ledger_keeps_as_a_reference() -> (
    None
):
    """The ledger entry names the automation, and `redact_details` keeps a value only in the field
    name grammar. Delete this and the reference is stored as the redaction marker, so "what was
    attached to this agent" cannot be answered. The refusal of an id outside the grammar is the
    sibling."""
    fresh = new_automation_id()

    assert re.fullmatch(AUTOMATION_ID, fresh)
    assert re.fullmatch(FIELD_NAME, fresh)
    assert re.fullmatch(FIELD_NAME, AUTOMATION_PART) and re.fullmatch(FIELD_NAME, INSTALL_REASON)
    assert fresh != new_automation_id()
    shown = preview(TEMPLATE, an_agent(), installer=person(), installer_reach=installer_reach())
    with pytest.raises(GalleryError, match="is not an id an automation can carry"):
        install(shown, confirmation=shown.confirmation, automation_id="has.a.stop")


def a_made_installation() -> Installation:
    shown = preview(TEMPLATE, an_agent(), installer=person(), installer_reach=installer_reach())
    return install(shown, confirmation=shown.confirmation, automation_id="auto_one")


def test_an_installation_whose_halves_disagree_cannot_be_built() -> None:
    """`A_SCHEDULE_WITHOUT_A_REGISTRY_ROW_IS_WORK_NOTHING_KNOWS_ABOUT` for an install: an entry for
    another principal, another agent, another task or with a next run, and an automation run as
    somebody other than its installer or already scheduled, each refused. Delete this and one row
    can be written describing two different automations. `a_made_installation` constructing is
    the sibling."""
    made = a_made_installation()
    entry = made.entry
    scheduled = replace(made.automation, next_run_at=LATER)
    other = person("u_other")
    refusals: list[tuple[dict[str, object], str]] = [
        ({"entry": replace(entry, runs_as_id="u_other")}, "does not describe the automation"),
        ({"entry": replace(entry, next_run_at=LATER)}, "does not describe the automation"),
        ({"entry": replace(entry, agent_id="other_agent")}, "names another agent"),
        ({"entry": replace(entry, task="automation.other_task")}, "names another agent"),
        ({"installed_by": "u_other"}, "was installed by"),
        (
            {
                "automation": replace(made.automation, runs_as=other),
                "entry": replace(entry, runs_as_id=other.id),
            },
            "was installed by",
        ),
        (
            {"automation": scheduled, "entry": register(scheduled, guards=entry.guards)},
            "is installed with a next run",
        ),
    ]

    assert isinstance(made.entry, RegistryEntry)
    for change, refused in refusals:
        with pytest.raises(GalleryError, match=refused):
            replace(made, **change)  # type: ignore[arg-type]
