/**
 * What can be done to a service account from its pages, and for each act either where it works or
 * the one sentence saying why it cannot be pressed.
 *
 * **Measured against the routes on this branch.** Registering, issuing a key, revoking one and
 * retiring the account are served (`brain.service_account_routes`), and each is a live control.
 * Changing when an account stops working has no route, so it is an `UNAVAILABLE` sentence drawn as
 * `kit/UnavailableAction`; `tests/service-accounts-page.test.tsx` reads its `retiredBy` pattern
 * against the API document, so the sentence cannot outlive the route's arrival.
 *
 * **Two acts are not offered at all, and say so as a sentence rather than a disabled control.**
 * An account is always its registrant's, because it acts at its owner's reach, so there is no
 * change of owner. Rotation is two presses in order (issue, move the integration, revoke), because
 * one "rotate" press would either revoke a key still in use or leave two live keys the person
 * believes are one.
 *
 * Task ids: M27.11.5, M27.16.1
 */

/** Why each act that has no route cannot be pressed, and the API path whose arrival retires it. */
export const UNAVAILABLE = Object.freeze({
  changeEnd: {
    reason: "Coming soon: changing when an account stops working. Register a new account to extend one today.",
    retiredBy: /^\/api\/v1\/govern\/service-accounts\/\{[^}]+\}\/(end|lapse|expiry|not-after)\b/,
  },
});

/** Acts this product does not offer, each as the sentence drawn in its place. */
export const NOT_OFFERED = Object.freeze({
  changeOwner:
    "An account always belongs to the person who registered it, because it acts at their reach. To hand an integration on, the new owner registers their own account.",
  rotate: "To rotate a key without a gap, issue a new one, move the integration to it, then revoke the old one.",
});

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
