/**
 * What can be done from Access reviews and elevation, and for each act either where it works or the
 * sentence saying why it cannot be pressed yet.
 *
 * **Measured against the routes on this branch.** Keeping and removing a holding, one or several
 * (`POST /govern/access-review/decision` and `/decisions`), asking for an elevation
 * (`POST /govern/elevation/requests`) and approving or denying one
 * (`POST /govern/elevation/{id}/decision`) all work. An act with no route is an `UNAVAILABLE`
 * sentence below, drawn as `kit/UnavailableAction`, and `tests/review-pages.test.tsx` reads each
 * `retiredBy` against the API document, so this table cannot go on saying "coming soon" about a
 * route that has arrived.
 *
 * Task ids: M27.7.8, M27.7.9, M27.15.21, M27.16.1
 */

/** Why each act that has no route cannot be pressed, and the shape of the path that retires it. */
export const UNAVAILABLE = Object.freeze({});

/** The labels of the acts, one spelling each, so a menu, a dialog and a test agree. */
export const ACT_LABELS = Object.freeze({
  open: "Open",
  keep: "Keep",
  remove: "Remove",
  keepSelected: "Keep selected",
  removeSelected: "Remove selected",
  decideLater: "Decide later",
  ask: "Ask for access",
  askSend: "Ask for this",
  notNow: "Not now",
  approve: "Approve",
  deny: "Deny",
  exportReport: "Export certification report",
  history: "Access changes",
  person: "Their page",
});
