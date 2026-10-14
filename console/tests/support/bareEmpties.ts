/**
 * The sentences a registered page draws, with its lists emptied, in a plain paragraph rather than through
 * `kit/states.tsx` `EmptyList`, by address.
 *
 * `tests/empty-lists.test.tsx` mounts every page that has a list with every list in its answers emptied
 * and reads what it says. A sentence that begins No, Nothing, Nobody or None and is not drawn by an
 * `EmptyList` or an `EmptyState` is one of two things, and each has its own record here.
 *
 * **`BARE_STATES` are not lists.** A fact about the install ("No company budget is set"), a page that is
 * not there ("No provider at this address") and a heading's own explanatory sentence say a thing is not
 * so; there is no table with no rows, so there is no row to say how to add. They are named so that a new
 * one is a decision.
 *
 * **`BARE_LISTS` are the backlog, and it is meant to shrink.** Each is an empty list drawn as a paragraph
 * that does not say what would add a row or who does it. The test holds the set to exactly this, in both
 * directions: a new bare empty list fails, and a sentence converted to an `EmptyList` must be taken out
 * of the record, which is how the number on it is kept true. **It is the count of what `M27.15.69` has
 * not yet done**, and a screen's other views (the tabs a page does not open first) are not mounted by
 * the test at all, so the true figure is larger than this record.
 *
 * Task ids: M27.15.69
 */

/** Why every sentence in `BARE_STATES` is allowed to be a paragraph. */
export const A_STATE_IS_NOT_A_LIST =
  "Each says that a fact about the install, the reader's own figures or the address is not so. There is no table " +
  "with no rows behind it, so there is no row to say how to add.";

/** Sentences that are not about a list, by the address that draws them. */
export const BARE_STATES: Readonly<Record<string, readonly string[]>> = {
  "/access_review/:kind/:rowId": ["No grant to review here"],
  "/agents/new": ["Nothing in a draft is live. Every save is kept as its own version, and the agent changes only when a checked version is published."],
  "/automations/:automationId/:view": ["No run has been resolved yet."],
  "/classification/:entity/:column": ["No column of this classification has that name."],
  "/company/consumption": [
    "No company budget is set, so there is no ceiling to measure this against.",
    "Nothing was spent in this period.",
  ],
  "/compliance/breaches/:caseId": ["No breach case here"],
  "/connections": ["No compose file is mounted where the application runs, so what it reserves is not read here."],
  "/department": ["No source is connected, so every question is answered: UNBROKENxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx Connect a source", "No budget is set for this department."],
  "/departments/:slug": ["No department to show"],
  "/departments/:slug/:view": ["No department to show"],
  "/duplicates": ["None of these changes what reviewers are told about a pair."],
  "/elevation/:requestId": ["No request here"],
  "/features": ["Nothing here reaches the old system: what is recorded is what a person tells it."],
  "/me": ["No budget of your own is set."],
  "/models/:provider": ["No provider at this address"],
  "/models/:provider/:view": ["No provider at this address"],
  "/people": ["No data steward is appointed."],
  "/prompts": [
    "Nothing in the platform sends a prompt to a model yet. An edit changes what an agent would be given from the next request, and no answer anybody has received.",
  ],
  "/retention/holds/:holdId": ["No legal hold here"],
  "/retention/erasures/:requestId": ["No erasure request here"],
  "/routing": [
    "No rule is set, so a question may go to any provider that is turned on.",
    "No person is in the directory yet, so there is nobody to ask a golden question as.",
  ],
  "/routing/:rungId": [
    "No step on the matrix matches this address. Routing",
    "No rule is set, so a question may go to any provider that is turned on.",
    "No person is in the directory yet, so there is nobody to ask a golden question as.",
  ],
  "/spend": ["No currency is set yet, so the amount is shown without one. Set it on Install, Settings.", "Nothing was spent in this period."],
  "/tools/:name": ["No tool by that name is listed on this install."],
  "/webhooks/:id": ["There is no subscriber at this address that you may manage."],
  "/webhooks/:id/:view": ["There is no subscriber at this address that you may manage."],
};

/** Empty lists drawn as a paragraph, by address. The backlog. */
export const BARE_LISTS: Readonly<Record<string, readonly string[]>> = {
  "/access-requests": [
    "Nothing has been handed to you.",
    "None of your questions has been handed to a person.",
    "Nobody has given themselves access to anything you steward.",
  ],
  "/adoption": ["Nobody asked a question in this period."],
  "/agent-templates/:templateId": ["Nothing"],
  "/agents/new": ["No template is offered on this install yet."],
  "/ask/documents/:documentId": ["Nothing in this document is here for you to read."],
  "/audit": ["No pattern of refusals you may be told about."],
  "/classification/:entity": ["Nothing to show."],
  "/classification/:entity/:column": ["Nothing to show."],
  "/connectors/:connector/:view": ["No agent you can see names this source.", "No skill you can see uses its tools."],
  "/credentials/:family/:name": ["No value has been written into this slot from the console or the setup wizard."],
  "/credentials/:family/:name/:view": ["Nothing is recorded about what to ask the issuer of this credential for."],
  "/department": [
    "Nobody you may see is listed in this department.",
    "No agent is listed for you.",
    "No document you may open is filed under this department.",
    "No document you may read is counted for this department.",
  ],
  "/features": ["Nothing has been saved yet."],
  "/install": ["Nothing was reported here."],
  "/library/:itemId": ["Nothing about this document is waiting for you."],
  "/me": [
    "There are no agents you can call.",
    "Nothing learnt about you is shown.",
    "You do not look after any knowledge items.",
    "No source here is connected by each person with their own account.",
    "No chat channel is switched on for you to connect.",
    "Nobody has read your record.",
    "No agent has made anything for you.",
    "Nothing has been shared with you that you can open.",
    "There is no agent you can see and cannot run.",
  ],
  "/memory/:subject": ["None"],
  "/memory/:subject/:view": ["None"],
  "/models": [
    "No model is set up for this level.",
    "No step on the failover matrix names a model yet, and no model has a price.",
  ],
  "/": ["None"],
  "/people/:personId": ["No agent you may open has them as its steward.", "No automation you may open runs as them."],
  "/people/:personId/:view": [
    "No grant you may be told about. Grants only add: a person reaches what their grants say and nothing else.",
    "No role you may see.",
  ],
  "/quality": ["No canary run in this period."],
  "/questions": ["No unanswered question in this period."],
  "/records/:entity": ["Nothing to show."],
  "/roles": [
    "There are no roles to show.",
    "Nothing is waiting for your decision",
    "No directory group maps to a role yet.",
    "Nobody you may see holds one without the other.",
  ],
  "/routing": [
    "No model is set up for this level.",
    "No change to the failover matrix has been decided yet.",
    "No question went past the first step of its level in the last day.",
  ],
  "/routing/:rungId": [
    "No model is set up for this level.",
    "No change to the failover matrix has been decided yet.",
    "No question went past the first step of its level in the last day.",
  ],
  "/spend": ["No cost in this period to rank.", "No budget is stopped."],
  "/staff_sources": ["No run yet", "No sync has run yet.", "No agent is waiting for an owner you may take on."],
  "/updates": ["Nothing was reported here."],
  "/usage": ["No department to show for this period.", "Nobody asked a question in this period."],
  "/vault": ["No connector run held a lease in the last 24 hours."],
};
