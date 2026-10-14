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
 * **One more kind of state: a cell of the owner's drawn failover matrix.** The matrix is a table of the four
 * levels the owner drew (`tests/models-module.test.tsx` holds it to his screenshot: no lede, no paragraph in
 * the card), so a level with no step is a cell that says so and not a list with no rows; the control that adds
 * a step is the card's own.
 *
 * **`BARE_LISTS` is the backlog, and it is empty.** Each entry would be an empty list drawn as a paragraph
 * that does not say what would add a row or who does it. The test holds the set to exactly this, in both
 * directions: a new bare empty list fails, and a sentence converted to an `EmptyList` must be taken out
 * of the record, which is how the number on it is kept true. **Empty means every list on the view a page
 * opens first is drawn with an act and a who**; a screen's other views (the tabs a page does not open
 * first) are not mounted by the render sweep, and only the static checks over every `EmptyList`,
 * `ListPage` and `WholeList` use reach them.
 *
 * Task ids: M27.15.69
 */

/** Why every sentence in `BARE_STATES` is allowed to be a paragraph. */
export const A_STATE_IS_NOT_A_LIST =
  "Each says that a fact about the install, the reader's own figures or the address is not so. There is no table " +
  "with no rows behind it, so there is no row to say how to add. A labelled fact whose value is the word " +
  "None or Nothing is the same: it is one value, not a list.";

/** Sentences that are not about a list, by the address that draws them. */
export const BARE_STATES: Readonly<Record<string, readonly string[]>> = {
  "/": ["None"],
  "/access_review/:kind/:rowId": ["No grant to review here"],
  "/agent-templates/:templateId": ["Nothing"],
  "/agents/new": ["Nothing in a draft is live. Every save is kept as its own version, and the agent changes only when a checked version is published."],
  "/automations/:automationId/:view": ["No run has been resolved yet."],
  "/classification/:entity/:column": ["No column of this classification has that name."],
  "/company/consumption": ["No company budget is set, so there is no ceiling to measure this against.", "Nothing was spent in this period."],
  "/compliance/breaches/:caseId": ["No breach case here"],
  "/connections": ["No compose file is mounted where the application runs, so what it reserves is not read here."],
  "/department": ["No budget is set for this department.", "No source is connected, so every question is answered: UNBROKENxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx Connect a source"],
  "/departments/:slug": ["No department to show"],
  "/departments/:slug/:view": ["No department to show"],
  "/duplicates": ["None of these changes what reviewers are told about a pair."],
  "/elevation/:requestId": ["No request here"],
  "/features": ["Nothing has been saved yet.", "Nothing here reaches the old system: what is recorded is what a person tells it."],
  "/me": ["No budget of your own is set."],
  "/memory/:subject": ["None"],
  "/memory/:subject/:view": ["None"],
  "/models": ["No model is set up for this level."],
  "/models/:provider": ["No provider at this address"],
  "/models/:provider/:view": ["No provider at this address"],
  "/people": ["No data steward is appointed."],
  "/prompts": ["Nothing in the platform sends a prompt to a model yet. An edit changes what an agent would be given from the next request, and no answer anybody has received."],
  "/retention/erasures/:requestId": ["No erasure request here"],
  "/retention/holds/:holdId": ["No legal hold here"],
  "/routing": ["No model is set up for this level.", "No person is in the directory yet, so there is nobody to ask a golden question as.", "No rule is set, so a question may go to any provider that is turned on."],
  "/routing/:rungId": ["No model is set up for this level.", "No person is in the directory yet, so there is nobody to ask a golden question as.", "No rule is set, so a question may go to any provider that is turned on.", "No step on the matrix matches this address. Routing"],
  "/spend": ["No currency is set yet, so the amount is shown without one. Set it on Install, Settings."],
  "/staff_sources": ["No run yet"],
  "/tools/:name": ["No tool by that name is listed on this install."],
  "/webhooks/:id": ["There is no subscriber at this address that you may manage."],
  "/webhooks/:id/:view": ["There is no subscriber at this address that you may manage."],
};

/** Empty lists drawn as a paragraph, by address. The backlog, and it is empty. */
export const BARE_LISTS: Readonly<Record<string, readonly string[]>> = {};
