/**
 * What can be done to a person from their pages, and for each act with no route the one sentence
 * saying why it cannot be pressed yet.
 *
 * **Measured against the routes on this branch.** A person is listed and opened
 * (`/govern/directory`), granted one capability or several people one at once, all or nothing
 * (`/govern/grants`, `/govern/grants/several`), given a pack (`/govern/packs/assignment`), has a
 * direct grant removed (`/govern/grants/removal`) or a pack taken away by the access review's
 * decision, is disabled and reinstated (`/govern/people/disable`, `/enable`), has a session ended or
 * every session ended (`/govern/sessions/end`, `/end-several`), has a sign-in linked or unlinked,
 * has an agent they steward handed on (`/agents/{agent_id}/transfer`, the Agents pages' own act) or a
 * leaver's agent taken on by the reader (`/govern/staff_sources/transfers/{agent_id}`); an install
 * with no staff source adds a person by hand (`POST /govern/directory`). A run through an agent is
 * previewed for this person by `POST /agents/{agent_id}/preview` since 2026-09-29
 * (`PersonPreview.tsx`), which retired the one inert act this table held.
 *
 * **When a route lands, its sentence goes and a live control takes its place, in the same commit.**
 * `tests/people-access-pages.test.tsx` reads every `retiredBy` against the API document, so this
 * table cannot go on calling something "coming soon" once it has arrived.
 *
 * Task ids: M27.11.2, M27.11.3, M27.16.1
 */

export const UNAVAILABLE: Readonly<Record<string, { readonly reason: string; readonly retiredBy: RegExp }>> = Object.freeze({});

export type UnavailableAct = keyof typeof UNAVAILABLE;

/** Said where an edit of a person's name or department would be, which this product does not offer. */
export const EDITED_AT_THE_SOURCE =
  "A person's name, department and employment come from the staff source or the identity provider, so they are changed there; a change made here would be overwritten by the next sync.";

/** The same, on an install whose departments are managed on People (M1.6.19). */
export const DEPARTMENT_SET_ON_PEOPLE =
  "A person's name and employment come from the staff source or the identity provider, so they are changed there. Their department is set here: select them on People and press Move to a department.";

/** A role grants nothing: said beside every role a person holds. */
export const A_ROLE_GRANTS_NOTHING =
  "A role says what somebody is appointed to do on this platform. It grants nothing: what they may see is only what their grants say.";

/** What the console needs a second factor for, said to an administrator looking at somebody else. */
export const WHAT_NEEDS_A_SECOND_FACTOR =
  "Approvals and administration need a sign-in with a second factor. Reading and asking do not.";

/** Where the acts that do work but live elsewhere are, as console addresses. */
export const WORKS_AT = Object.freeze({
  signInLinks: "/sign-in-links",
  sessions: "/sessions",
  accessReview: "/access_review",
  departments: "/departments",
  roles: "/roles",
  audit: "/audit",
  staffSources: "/staff_sources",
});
