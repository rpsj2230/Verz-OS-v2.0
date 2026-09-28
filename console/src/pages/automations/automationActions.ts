/**
 * What can be done to an automation from the Automations module, and for each act either where it
 * works or the one sentence saying why it cannot be pressed yet.
 *
 * **Measured against the routes on this branch.** On 2026-09-29 the API served, for one automation:
 * pausing, resuming, changing its schedule, removing and adopting it
 * (`POST /api/v1/automations/{id}/{pause|resume|reschedule|remove|adopt}`), and, from its agent's
 * page, installing one from the gallery and starting and stopping it. It served no route that brings
 * back a removed automation: a removal is final by design, and installing the same outcome again is
 * refused for the same agent and person, so bringing one back waits on a decision. That act is an
 * `UNAVAILABLE` sentence below and is drawn as `kit/UnavailableAction`.
 *
 * **When a route lands, its sentence goes and a live control takes its place, in the same commit.**
 * `tests/automations-page.test.tsx` reads every `retiredBy` against the API document.
 *
 * Task ids: M27.12.3, M27.15.37, M27.16.1
 */

/** Why each act that has no route cannot be pressed, and the shape of the path that retires it. */
export const UNAVAILABLE = Object.freeze({
  reinstate: {
    reason: "Not available yet: bringing back a removed automation. Its runs and history stay on its page.",
    retiredBy: /^\/api\/v1\/automations\/\{[^}]+\}\/(reinstate|restore)$/,
  },
});

export type UnavailableAct = keyof typeof UNAVAILABLE;

/** The labels of the acts, one spelling each, so a menu, a dialog and a test agree. */
export const ACT_LABELS = Object.freeze({
  open: "Open",
  pause: "Pause",
  resume: "Resume",
  reschedule: "Change schedule",
  remove: "Remove",
  adopt: "Adopt",
  reinstate: "Bring back",
  add: "Add an automation",
});
