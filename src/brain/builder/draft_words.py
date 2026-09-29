"""The closed words an agent's draft is described in: its kind, its acts, the ledger's words and
its state.

Their own module, with nothing imported, because the table that stores a draft
(`brain.tables.manifest_draft`) checks its columns against them and the tables are imported by
modules `brain.builder.agent_drafts` itself imports; the words cannot sit behind that module
without a cycle. `brain.builder.agent_drafts` is where they are argued and used.

Task ids: M27.11.6
"""

from __future__ import annotations

import enum


class DraftKind(enum.StrEnum):
    """What a draft is for. Two, and a third would be a lineage nobody has argued for."""

    #: Makes an agent that does not exist yet, under the id minted when the draft started.
    NEW = "new"
    #: Changes an agent that exists, starting from its configuration when the draft started.
    EDIT = "edit"


class DraftAct(enum.StrEnum):
    """What a person did to one revision, each at most once per revision.

    Kept as rows beside the revisions rather than as a state column on the draft, because a state
    column is overwritten and "who asked, who approved and when" is the question an auditor asks.
    """

    #: The check found nothing that stops a publish.
    CHECKED = "checked"
    #: A wider publish was asked for and waits for a second person.
    REQUESTED = "requested"
    #: The second person agreed. The publish follows in the same act.
    APPROVED = "approved"
    #: The second person sent it back.
    DECLINED = "declined"
    #: The agent is what this revision says.
    PUBLISHED = "published"


class DraftChange(enum.StrEnum):
    """The words `0149`'s trigger writes to the ledger, in the order a draft meets them."""

    DRAFTED = "drafted"
    SAVED = "saved"
    CHECKED = DraftAct.CHECKED.value
    REQUESTED = DraftAct.REQUESTED.value
    APPROVED = DraftAct.APPROVED.value
    DECLINED = DraftAct.DECLINED.value
    PUBLISHED = DraftAct.PUBLISHED.value


class DraftState(enum.StrEnum):
    """Where a draft stands, read off its latest revision's acts. Never stored."""

    DRAFT = "draft"
    CHECKED = "checked"
    WAITING = "waiting"
    DECLINED = "declined"
    PUBLISHED = "published"
