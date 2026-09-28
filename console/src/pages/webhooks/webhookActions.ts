/**
 * What can be done to a webhook subscriber from the Webhooks module, and for each act either where
 * it works or the one sentence saying why it cannot be pressed yet.
 *
 * **Measured against the routes on this branch.** On 2026-09-29 the API served registering a
 * subscriber (`POST /webhooks/subscribers`), replacing its signing secret
 * (`POST /webhooks/subscribers/{id}/secret`) and switching it off
 * (`POST /webhooks/subscribers/{id}/switch-off`). It served no route that switches one back on or
 * replays a delivery that was given up (M27.15.44). Both need a schema change this package did not
 * take: `ops.webhook_subscriber`'s policy lets a row be changed only while it is switched on, and
 * `ops.webhook_change` has no word for either act, so neither could be recorded. Each is drawn as
 * `kit/UnavailableAction` with the sentence below.
 *
 * **When a route lands, its sentence goes and a live control takes its place, in the same commit.**
 * `tests/webhooks-page.test.tsx` reads every `retiredBy` against the API document.
 *
 * Task ids: M27.8.12, M27.15.44, M27.16.1
 */

export const UNAVAILABLE = Object.freeze({
  switchOn: {
    label: "Switch back on",
    reason:
      "Coming soon: switching a subscriber back on as a recorded change. Until then, register it again under a new id.",
    retiredBy: /^\/api\/v1\/webhooks\/subscribers\/\{[^}]+\}\/(switch-on|reactivation|reactivate)$/,
  },
  replay: {
    label: "Replay",
    reason: "Coming soon: sending a delivery that was given up once more, recorded in the audit trail.",
    retiredBy: /^\/api\/v1\/webhooks\/.*\/(replay|redrive)$/,
  },
});

export type UnavailableAct = keyof typeof UNAVAILABLE;

/** The labels of the acts, one spelling each, so a menu and a test agree. */
export const ACT_LABELS = Object.freeze({
  open: "Open",
  register: "Register a subscriber",
  reviewRegistration: "Register",
  replace: "Replace secret",
  switchOff: "Switch off",
});
