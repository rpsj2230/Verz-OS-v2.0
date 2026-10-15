/**
 * What can be done from Access reviews and elevation, and for each act either where it works or the
 * sentence saying why it cannot be pressed yet.
 *
 * **Measured against the routes on this branch.** Keeping and removing a holding, one or several
 * (`POST /govern/access-review/decision` and `/decisions`), asking for an elevation
 * (`POST /govern/elevation/requests`) and approving or denying one
 * (`POST /govern/elevation/{id}/decision`) all work. No act on this page is without a route,
 * so none is drawn as a `kit/Explanation`; one that is added gets a sentence in
 * `brain.console.explanations`, which `tests/unit/test_console_explanations.py` holds against the
 * routes the application mounts.
 *
 * Task ids: M27.7.8, M27.7.9, M27.15.21, M27.16.1
 */

/** The labels of the acts, one spelling each, so a menu, a dialog and a test agree. */
export const ACT_LABELS = Object.freeze({
  open: "Open",
  keep: "Keep",
  remove: "Withdraw",
  keepSelected: "Keep selected",
  removeSelected: "Withdraw selected",
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
