/**
 * What can be done to a service account from its pages, and for each act either where it works or
 * the one sentence saying why it cannot be pressed.
 *
 * **Measured against the routes on this branch.** Registering, issuing a key, revoking one and
 * retiring the account are served (`brain.service_account_routes`), and each is a live control.
 * Changing when an account stops working has no route, so it is a `kit/Explanation` of the
 * `action` form (`service_account.change_end`); `tests/unit/test_console_explanations.py` reads its
 * expiry against the routes the application mounts, so the sentence cannot outlive the route's
 * arrival.
 *
 * **Two acts are not offered at all, and say so as a sentence rather than a disabled control.**
 * An account is always its registrant's, because it acts at its owner's reach, so there is no
 * change of owner. Rotation is two presses in order (issue, move the integration, revoke), because
 * one "rotate" press would either revoke a key still in use or leave two live keys the person
 * believes are one.
 *
 * Task ids: M27.11.5, M27.16.1
 */

/** The acts' labels, shared by the list's row menu and the account's page. */
export const ACT_LABELS = Object.freeze({
  register: "Register an account",
  issue: "Issue a key",
  revoke: "Revoke",
  retire: "Retire account",
  open: "Open",
  changeEnd: "Change end date",
});

/** Beside a capability the owner no longer holds, which the account therefore cannot use. */
export const NOT_HELD_MARK = "(you do not hold it now)";
