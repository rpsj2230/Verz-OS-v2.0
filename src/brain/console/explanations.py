"""Why an act cannot be done, said once, by the server, in the words every screen uses.

`docs/admin-console-architecture.md` 5.2 asks that every act the install cannot yet perform, and
every act a reader cannot perform where they are, is explained in a sentence and never hidden.
Until 2026-10-15 those sentences were typed into the console's source, one constant per page
(`UNAVAILABLE` and `NOT_OFFERED` in a dozen `*Actions.ts` files, a `Note` with its words inline in
a dozen more), drawn by three components that each wrote their own markup. The words and the
markup are both one thing now: this module holds the words, `GET /console/explanations/{act}`
serves one of them, and `console/src/components/kit/explanation.tsx` is the one component that
draws any of them.

**The server holds the sentence because the server is what knows the act is still unbuilt.**
A sentence that says "coming soon" about a route that has landed is a statement the product
makes falsely, and until now the console carried a regular expression per sentence (`retiredBy`)
and a test per page to notice. The expression lives beside its sentence here, and
`tests/unit/test_console_explanations.py` holds it against the routes the application actually
mounts, so a route that lands without its sentence being deleted is a red test in the same
repository, not a stale line in a browser bundle.

**One body for every reader, and that is a rule and not an accident.** A sentence here explains
an act that this install does not perform, or does not offer, for everybody. It is never
computed from the reader's grants and it never says why a particular reader was refused, because
a sentence that differed between the person who may and the person who may not would be a
denial that could be told apart from an absence. `explanation_for` takes no reader, and the route
test asks it as two readers holding different grants and compares the bytes.

**Three forms, because three places need them.** An `action` is a control that cannot be pressed
and carries its reason as its description, and its sentence leads with "Coming soon: " or "Not
available yet: " because it names an act the product means to have. A `line` is a sentence in
place of a control, for something this product deliberately does not offer: a disabled switch
would still say it could be switched on. A `note` is a line saying what is true today, with its
lead ("Coming soon: " or "Not available yet: ") kept apart from the sentence so a page can draw
one beside content.

**Rejected: serving the whole list once and caching it in the browser.** `api/useResource.ts`
says why nothing is cached, and the argument is about facts held past the person they were
computed for. These bodies are the same for everybody, so the argument does not bite, but a
per-sentence read is also what lets a page that shows two explanations ask for two, and it keeps
a sentence that was edited on the server from living on in a tab. **Rejected: one sentence per
page in the page's own source with a server check that it matches**, which is what the console
did and which is a copy that can disagree.

**Not here, deliberately.** A sentence the API composes from a row (a vault that is not ready, a
publish that is held, why a stop was applied) is already served with the row it is about, and
the console draws it through the same component with `told`. Moving those here would put row data
in a table of constants.

Task ids: M27.15.70
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from brain.api import API_PREFIX


class Form(StrEnum):
    """What the console draws for one explanation."""

    ACTION = "action"
    LINE = "line"
    NOTE = "note"


class Lead(StrEnum):
    """What a note leads with, kept apart from its sentence so a page can draw it beside content."""

    NONE = ""
    SOON = "soon"
    NOT_YET = "not-yet"


@dataclass(frozen=True, slots=True)
class Explanation:
    """One sentence, the form it is drawn in and the route whose arrival makes it untrue.

    `retired_by` is a regular expression over a request path, anchored by the author, and empty
    when the sentence is not about something a route could later provide: a thing the product
    deliberately does not offer has no route that retires it.
    """

    act: str
    form: Form
    sentence: str
    lead: Lead = Lead.NONE
    retired_by: str = ""


THE_SAME_SENTENCE_FOR_EVERY_READER: Final = (
    "An explanation is read by act and by nothing else. It is never computed from a reader's "
    "grants and never says why this reader in particular cannot, because a sentence that "
    "differed between the person who may and the person who may not could be told apart from an "
    "absence."
)

SOON: Final = "Coming soon: "
NOT_YET: Final = "Not available yet: "

#: Every explanation, grouped by the page that draws it. Ids are `<noun>.<act>` and never move,
#: because the console names them.
EXPLANATIONS: Final[tuple[Explanation, ...]] = (
    # Controls that cannot be pressed yet.
    Explanation(
        "learning.promote",
        Form.ACTION,
        f"{SOON}promoting a rule once enough separate conversations agree. Nothing records that "
        "agreement yet, so a rule stays in shadow.",
        retired_by=rf"^{API_PREFIX}/govern/learning/promot",
    ),
    Explanation(
        "learning.decide",
        Form.ACTION,
        f"{SOON}deciding a change that would widen who sees what. Nothing records the decision "
        "yet, so it waits here.",
        retired_by=rf"^{API_PREFIX}/govern/learning/(decide|decision)",
    ),
    Explanation(
        "operations.stop_run",
        Form.ACTION,
        f"{NOT_YET}stopping a run that has started. Pausing the job stops the schedule starting "
        "it again.",
        retired_by=rf"^{API_PREFIX}/(jobs|operate/runs)/\{{[^}}]+\}}/(stop|cancel)\b",
    ),
    Explanation(
        "operations.start_rehearsal",
        Form.ACTION,
        f"{SOON}starting a restore rehearsal from here. Today it is run on the server, as the "
        "rehearsal card says.",
        retired_by=rf"^{API_PREFIX}/install/recovery/(drills?|rehearsals?)\b",
    ),
    Explanation(
        "operations.import_data",
        Form.ACTION,
        f"{SOON}importing data from this page. Documents are added on the Knowledge page today.",
        retired_by=rf"^{API_PREFIX}/data-transfer/imports?\b",
    ),
    Explanation(
        "template.author",
        Form.ACTION,
        f"{SOON}publishing a template from one of your agents. It will be checked for company "
        "details before anyone can install it.",
        retired_by=(
            rf"^{API_PREFIX}/(agent-templates/(author|drafts?|publish)"
            r"|agents/\{[^}]+\}/(template|publish-template))\b"
        ),
    ),
    Explanation(
        "automation.reinstate",
        Form.ACTION,
        f"{NOT_YET}bringing back a removed automation. Its runs and history stay on its page.",
        retired_by=rf"^{API_PREFIX}/automations/\{{[^}}]+\}}/(reinstate|restore)$",
    ),
    Explanation(
        "channel.verify",
        Form.ACTION,
        f"{SOON}a check that a request signed with the stored secret is accepted. Until then, a "
        "message sent from the chat shows as accepted under History.",
        retired_by=rf"^{API_PREFIX}/channels/\{{[^}}]+\}}/(verify|verification|check)$",
    ),
    Explanation(
        "credential.check_source",
        Form.ACTION,
        f"{SOON}checking a source's key with its vendor without waiting for the next read.",
        retired_by=rf"^{API_PREFIX}/connectors/\{{[^}}]+\}}/(test|check)$",
    ),
    Explanation(
        "knowledge.export_inventory",
        Form.ACTION,
        f"{SOON}exporting the inventory, recorded on the Exports screen with who took it and why.",
        retired_by=rf"^{API_PREFIX}/knowledge/(inventory|documents/exports?)\b",
    ),
    Explanation(
        "service_account.change_end",
        Form.ACTION,
        f"{SOON}changing when an account stops working. Register a new account to extend one "
        "today.",
        retired_by=(
            rf"^{API_PREFIX}/govern/service-accounts/\{{[^}}]+\}}/(end|lapse|expiry|not-after)\b"
        ),
    ),
    Explanation(
        "skill.try_out",
        Form.ACTION,
        f"{SOON}trying a skill out through an agent in practice mode, as a named person, before "
        "it is assigned for real.",
        retired_by=(
            rf"^{API_PREFIX}/(skills/\{{[^}}]+\}}/(rehearsal|trial)|agents/\{{[^}}]+\}}/rehearse)\b"
        ),
    ),
    # Sentences in place of a control, for what this product does not offer at all.
    Explanation(
        "capability.vocabulary_declared",
        Form.LINE,
        "Capabilities are declared by the product's tools and the sources connected to it, so "
        "they are not added or edited here.",
    ),
    Explanation(
        "channel.bind_for_somebody",
        Form.LINE,
        "People connect their own chat account from My workspace with a one-time code. Nobody "
        "binds another person's account.",
    ),
    Explanation(
        "channel.not_received",
        Form.LINE,
        "This release cannot receive or reply on this channel yet, so there is nothing to set "
        "up here.",
    ),
    Explanation(
        "credential.not_removed",
        Form.LINE,
        "A credential is replaced, never removed: removing one would stop everything that uses "
        "it at once, and the vault gives this system no way to delete one.",
    ),
    Explanation(
        "department.profile_elsewhere",
        Form.LINE,
        "Its lead, teams and scopes are managed on Departments by somebody who may open it.",
    ),
    Explanation(
        "learning.memory_not_edited",
        Form.LINE,
        "A memory is not edited or deleted here. A learning that went wrong is undone on "
        "Learning, and the change shows in this person's history.",
    ),
    Explanation(
        "learning.tier_three_withheld",
        Form.LINE,
        "Where gated changes were routed is shown to a reader who holds the Scopes and "
        "departments screen for the whole company, because each one names the department that "
        "decides it.",
    ),
    Explanation(
        "model.built_in_retire",
        Form.LINE,
        "A built-in provider cannot be retired. Turn it off to stop every question going to it.",
    ),
    Explanation(
        "model.step_restore",
        Form.LINE,
        "A retired step does not come back. Add it again as a new step.",
    ),
    Explanation(
        "person.changed_at_the_source",
        Form.LINE,
        "A person's name, department and employment come from the staff source or the identity "
        "provider, so they are changed there; a change made here would be overwritten by the "
        "next sync.",
    ),
    Explanation(
        "person.department_set_on_people",
        Form.LINE,
        "A person's name and employment come from the staff source or the identity provider, so "
        "they are changed there. Their department is set here: select them on People and press "
        "Move to a department.",
    ),
    Explanation(
        "role.not_edited",
        Form.LINE,
        "What a role grants is not edited here, because a role grants nothing: what somebody "
        "may see is only what their grants say.",
    ),
    Explanation(
        "service_account.change_owner",
        Form.LINE,
        "An account always belongs to the person who registered it, because it acts at their "
        "reach. To hand an integration on, the new owner registers their own account.",
    ),
    Explanation(
        "service_account.rotate",
        Form.LINE,
        "To rotate a key without a gap, issue a new one, move the integration to it, then "
        "revoke the old one.",
    ),
    # Lines saying what is true today, with the lead kept apart.
    Explanation(
        "agent.browser",
        Form.NOTE,
        "browser use. It is built and tested, and has never been switched on for any agent.",
        Lead.NOT_YET,
        retired_by=rf"^{API_PREFIX}/agents/\{{[^}}]+\}}/browser\b",
    ),
    Explanation(
        "agent.overview",
        Form.NOTE,
        "a longer description written by whoever looks after the agent. Today an agent has only "
        "its one-line summary.",
        Lead.SOON,
    ),
    Explanation(
        "agent.practising_only",
        Form.NOTE,
        "every action it takes only practises until a review finds it ready.",
        Lead.NOT_YET,
    ),
    Explanation(
        "agent.size_not_used",
        Form.NOTE,
        "the size is saved and not yet used when it answers.",
        Lead.NOT_YET,
    ),
    Explanation(
        "agent.spend_not_recorded",
        Form.NOTE,
        "spend is not recorded, so the figure is left out rather than drawn as nought.",
        Lead.NOT_YET,
    ),
    Explanation(
        "channel.no_address",
        Form.NOTE,
        "This install names no address of its own yet, so there is no events address to paste. "
        "Set the install's sign-in redirect address first.",
        Lead.NOT_YET,
    ),
    Explanation(
        "job.controls_switched_off",
        Form.NOTE,
        "Pausing a job and running one now are switched off on this install; they are switched "
        "on under Features. A paused job can still be resumed.",
        Lead.NOT_YET,
    ),
    Explanation(
        "job.run_again_switched_off",
        Form.NOTE,
        "running a job that was set aside again is switched off on this install; it is switched "
        "on under Features.",
        Lead.NOT_YET,
    ),
    Explanation(
        "log.export_cut_off",
        Form.NOTE,
        "The period held more rows than one export carries; choose a shorter period for the rest.",
        Lead.NOT_YET,
    ),
    Explanation(
        "prompt.editing_switched_off",
        Form.NOTE,
        "Editing instructions is switched off on this install. An administrator switches it on "
        "under Install, Features. Instructions already changed can still be given back to "
        "their template.",
        Lead.NOT_YET,
    ),
    Explanation(
        "routing.no_golden",
        Form.NOTE,
        "No golden questions are recorded yet, so every change to the failover matrix is held "
        "until one is.",
        Lead.NOT_YET,
    ),
    Explanation(
        "skill.history_elsewhere",
        Form.NOTE,
        "the history of a skill is read from the activity log, which your account cannot open.",
        Lead.NOT_YET,
    ),
    Explanation(
        "tool.no_longer_offered",
        Form.NOTE,
        "This install no longer registers this tool. It is listed because its catalogue row is "
        "kept, so a stop on it still has something to name.",
        Lead.NOT_YET,
    ),
)

#: The explanations by act, for the route and for a lookup that must not scan.
BY_ACT: Final[dict[str, Explanation]] = {one.act: one for one in EXPLANATIONS}

#: What an id may look like: a noun, a dot and an act, lower case with underscores.
ACT_SHAPE: Final = re.compile(r"^[a-z]+(_[a-z]+)*\.[a-z]+(_[a-z]+)*$")


def explanation_for(act: str) -> Explanation | None:
    """The explanation registered under `act`, or none.

    Takes no reader, on purpose. See `THE_SAME_SENTENCE_FOR_EVERY_READER`.
    """
    return BY_ACT.get(act)


def retired_by_a_route(one: Explanation, paths: tuple[str, ...]) -> bool:
    """Whether any of `paths` is a route whose arrival makes this sentence untrue."""
    if one.retired_by == "":
        return False
    pattern = re.compile(one.retired_by)
    return any(pattern.search(path) is not None for path in paths)
