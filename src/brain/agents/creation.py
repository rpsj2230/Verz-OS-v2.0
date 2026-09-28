"""A new agent from a published version: an install, and a duplicate of an agent already installed.

`brain.agents.install` is the wizard and `brain.agents.install_store.StoredAgentInstalls.finish` is
the end of it, and nothing turned a press in the console into a draft either of them takes. This
module is that step, for the two ways the console makes an agent, and it adds three decisions the
wizard never needed: what a new agent is called in the address bar, who can see it the moment it
exists, and what a copy of an agent may reach.

**A duplicate is an install of the same version with the source's overlay, and nothing else.**
Not a copy of the agent's row, which would skip `install`'s signature check and `settle`'s binding
and arrive as the second finishing path that
`brain.agents.install.AN_AGENT_IS_FINISHED_FROM_A_MANIFEST_IN_ONE_PLACE` refuses. Not a copy of the
effective manifest as a new template either: that is authoring (`brain.agents.authoring.author`),
which has a leak scan and a publish gate, and a duplicate that went round both would be a publish
without either. So `duplicate_draft` opens the version the source pins and answers every path the
source's overlay sets, and the name, and hands the draft to the same `complete` an install is
finished by. The placeholder answers are not carried, because nothing stores them
(`brain.agents.install` rejected the column), so a duplicate of a template with required
placeholders is incomplete and says so. See `A_DUPLICATE_IS_AN_INSTALL_OF_THE_SAME_VERSION`.

**A duplicate never reaches more than its source, and the comparison is the builder's.** Same
version and same overlay should mean same ceiling, and on the day the source was installed it did.
What moves in between is this install's tool registry: a second system registered for an entity
the template reads binds a second tool, so the copy would reach a source the original was never
bound to. `widened` compares the two stored records the way
`brain.builder.publish.widened_capabilities` compares a publish, plus the tools and the side
effect, and a copy wider in any part is refused with the parts named rather than narrowed in
silence: narrowing would store an agent that its own next upgrade widens again, because `settle`
binds from the registry every time. See
`A_DUPLICATE_NEVER_REACHES_MORE_THAN_ITS_SOURCE`.

**A new agent's id is minted, never typed.** The id is the primary key of `agent.agent`, the
instance's id and the workspace's address, so an install that took an id from the browser would
answer "that id is taken" for an agent the person may not see, which is
`brain.agents.model.A_HIDDEN_AGENT_AND_A_MISSING_AGENT_ARE_ONE_ANSWER` broken by a form field: try
slugs, read which are taken. `mint_agent_id` builds a slug from the name and a random suffix, so a
collision says nothing about any agent anybody holds. See `A_NEW_AGENT_ID_IS_MINTED_NOT_CHOSEN`.

**A new agent is seen by whoever made it, or by their department, and by nobody else yet.** The
audience is `brain.agents.install.THE_OFFER_AUDIENCE_IS_NOT_THE_AGENT_AUDIENCE`'s own argument:
the installer chooses it. Two choices are offered and a third is not. The company is a publication,
which `brain.agents.lifecycle.publish` gates behind a second person, and an install that could
choose it would be a publish without that person. Another department is an agent its maker cannot
see, so the lifecycle routes would answer them 404 for the agent they just made. See
`A_NEW_AGENT_IS_SEEN_BY_WHOEVER_MADE_IT`.

**The offer goes through `TemplateCatalogue.open_for`.** `brain.agents.install.begin` says an offer
comes from `open_for` or `blank_offer` and from nowhere else. A published version is offered here
to the one person installing it, which is what reading the gallery behind its screen's grant
already decided, and `open_for` is then asked for it, so there is still no third constructor.

Task ids: M27.11.6, M27.11.7
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import datetime
from typing import Final

from pydantic import JsonValue

from brain.agents.install import InstallDraft, TemplateCatalogue, answer, begin
from brain.agents.model import (
    AgentAudience,
    AgentRecord,
    AgentViewer,
    entitlement_ceiling,
)
from brain.agents.template import SignedManifest, TemplateError, TemplateInstance
from brain.builder.publish import widened_capabilities
from brain.core.entitlement import Capability
from brain.gate.catalogue import SIDE_EFFECT_ORDER
from brain.knowledge.visibility import Visibility

# ------------------------------------------------------------------ written-down reasons

#: Why a duplicate is a new install and not a copied row.
A_DUPLICATE_IS_AN_INSTALL_OF_THE_SAME_VERSION: Final = (
    "A duplicate opens the version its source pins, answers every path the source's overlay "
    "sets and a new name, and is finished by the same complete an install is. Copying the row "
    "would skip the signature check and the tool binding, and copying the effective manifest "
    "into a template would be authoring without the leak scan or the publish gate."
)

#: Why a copy wider than its source is refused rather than narrowed.
A_DUPLICATE_NEVER_REACHES_MORE_THAN_ITS_SOURCE: Final = (
    "The same version and overlay bind to whatever this install registers today, so a tool "
    "registered since the source was installed would put a source in the copy's reach that the "
    "original never had. A copy wider than its source in any capability, scope, tool or side "
    "effect is refused with those parts named. Narrowing it quietly would store an agent that "
    "its next upgrade widens again, because binding reads the registry every time."
)

#: Why the id of a new agent is not something a person types.
A_NEW_AGENT_ID_IS_MINTED_NOT_CHOSEN: Final = (
    "An agent's id is a primary key in one namespace. A typed id refused as taken would tell "
    "the person an agent by that name exists, whether or not they may see it, and a loop over "
    "slugs would list the company's agents. The id is minted from the name and a random "
    "suffix, so a collision says nothing about anybody's agent."
)

#: Why the maker chooses between themselves and their own department.
A_NEW_AGENT_IS_SEEN_BY_WHOEVER_MADE_IT: Final = (
    "A new agent is visible to the person who made it, or to their own department. The whole "
    "company is a publication, which a second person approves, and another department is an "
    "agent its maker could not see or administer the moment it existed."
)

# ------------------------------------------------------------------------------ the figures

#: Installs a published version as a new agent and duplicates an installed one, held in a scope
#: admitting the new agent's row and, for a duplicate, the source's row too.
#:
#: Its own capability rather than `brain.agents.lifecycle.AGENT_LIFECYCLE_CAPABILITY`, because
#: making an agent is a different act from switching one: it decides that a ceiling exists at all,
#: and somebody trusted to turn a department's agents off has not been asked whether they may add
#: one. The verb is `admin`, which the gate admits only at strong assurance.
AGENT_INSTALL_CAPABILITY: Final = Capability(value="admin:agent_install")

#: How much of the name reaches the id. Leaves room for the separator and the suffix inside
#: `brain.agents.model.AGENT_ID_CHARS`, which `test_a_minted_id_is_a_slug_the_agent_table_admits`
#: holds.
ID_STEM_CHARS: Final = 40

#: What the id is called when the name has no letter or digit in it at all.
ID_STEM_WHEN_UNNAMED: Final = "agent"

#: The path a new agent's name is answered on.
NAME_PATH: Final = "identity.display_name"

_WORDS = re.compile(r"[a-z0-9]+")
_LEADING_NON_LETTERS = re.compile(r"^[^a-z]+")


# ------------------------------------------------------------------------------ the decisions


def mint_agent_id(display_name: str, *, suffix: str) -> str:
    """A slug for a new agent: the name's words joined, bounded, and `suffix` after them.

    `suffix` is a parameter so a test can hold the shape, and the route passes random hex. The
    stem starts with a letter because the slug grammar requires one, and is cut at a word
    boundary's underscore rather than left trailing one. See `A_NEW_AGENT_ID_IS_MINTED_NOT_CHOSEN`.
    """
    stem = _LEADING_NON_LETTERS.sub("", "_".join(_WORDS.findall(display_name.lower())))
    stem = stem[:ID_STEM_CHARS].rstrip("_") or ID_STEM_WHEN_UNNAMED
    return f"{stem}_{suffix}"


def new_audience(maker_id: str, department: str | None) -> AgentAudience:
    """Who sees a new agent: its maker, or the department named, and never the company.

    `department` is the maker's own, which the caller reads off the signed-in principal; there
    is no parameter that could name the company. See `A_NEW_AGENT_IS_SEEN_BY_WHOEVER_MADE_IT`.
    """
    if department:
        return AgentAudience(level=Visibility.DEPARTMENT, owner_id=maker_id, department=department)
    return AgentAudience(level=Visibility.PERSONAL, owner_id=maker_id)


def _opened(signed: SignedManifest, *, agent_id: str, maker_id: str) -> InstallDraft:
    """A draft of one version for one person, through `open_for`. See the module docstring."""
    shelf = TemplateCatalogue()
    shelf.offer(signed, audience=AgentAudience(level=Visibility.PERSONAL, owner_id=maker_id))
    offer = shelf.open_for(signed.manifest.identity.template_id, AgentViewer(principal_id=maker_id))
    return begin(offer, instance_id=agent_id, installer=maker_id)


def _named(draft: InstallDraft, display_name: str | None) -> InstallDraft:
    """The draft with its name answered, or unchanged when no name was given or it is the
    template's own, so an install that keeps the name has no overlay to diverge by."""
    wanted = (display_name or "").strip()
    if not wanted or wanted == draft.offer.signed.manifest.identity.display_name:
        return draft
    return answer(draft, NAME_PATH, wanted)


def install_draft(
    signed: SignedManifest, *, agent_id: str, maker_id: str, display_name: str | None
) -> InstallDraft:
    """A published version opened as a new agent's draft, with a name when one was given."""
    return _named(_opened(signed, agent_id=agent_id, maker_id=maker_id), display_name)


def duplicate_draft(
    signed: SignedManifest,
    source: TemplateInstance,
    *,
    agent_id: str,
    maker_id: str,
    display_name: str,
) -> InstallDraft:
    """The version `source` pins, opened again with every path its overlay sets and a new name.

    Refuses a manifest that is not the one `source` pins, by template, version or digest, because
    a duplicate of one version finished against another is an upgrade nobody accepted. Each
    overlaid path goes through `answer`, which is `check_overlay`, so a sealed path somebody wrote
    into the source's row by hand is refused here with the seal's own sentence rather than carried
    into the copy. See `A_DUPLICATE_IS_AN_INSTALL_OF_THE_SAME_VERSION`.
    """
    identity = signed.manifest.identity
    if (identity.template_id, identity.version, signed.content_digest) != (
        source.template_id,
        source.template_version,
        source.content_digest,
    ):
        msg = (
            f"{source.instance_id!r} pins version {source.template_version} of "
            f"{source.template_id!r}, and a duplicate is made from that version and no other"
        )
        raise TemplateError(msg)
    draft = _opened(signed, agent_id=agent_id, maker_id=maker_id)
    overlay: Mapping[str, JsonValue] = source.overlay
    for path in sorted(overlay):
        # The source's name is the one path not carried: a copy is named by whoever makes it,
        # and a copy named the template's own name has no overlay for it at all.
        if path != NAME_PATH:
            draft = answer(draft, path, overlay[path])
    return _named(draft, display_name)


def widened(source: AgentRecord, copy: AgentRecord, *, now: datetime) -> tuple[str, ...]:
    """Every part of `copy`'s authority wider than `source`'s, named, or nothing.

    Capabilities and scope through `brain.builder.publish.widened_capabilities`, over the two
    ceilings `brain.agents.model.entitlement_ceiling` builds, so a copy is judged by the same
    comparison a publish is. Then every allowed tool the source was not allowed, and the side
    effect when it ranks higher on `brain.gate.catalogue.SIDE_EFFECT_ORDER`. Required tools are
    not compared: they are a subset of the allowed ones by `AgentCeiling`'s own rule, so a wider
    required set is already a wider allowed set. See
    `A_DUPLICATE_NEVER_REACHES_MORE_THAN_ITS_SOURCE`.
    """
    grown = list(
        widened_capabilities(entitlement_ceiling(source), entitlement_ceiling(copy), now=now)
    )
    grown.extend(sorted(copy.authority.allowed_tools - source.authority.allowed_tools))
    if SIDE_EFFECT_ORDER.index(copy.authority.max_side_effect) > SIDE_EFFECT_ORDER.index(
        source.authority.max_side_effect
    ):
        grown.append(copy.authority.max_side_effect.value)
    return tuple(grown)
