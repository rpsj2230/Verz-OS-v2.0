/**
 * What can be done to a source from the Connectors module, and for each act either where it works
 * or the one sentence saying why it cannot be pressed yet.
 *
 * **Measured against the routes on this branch, not against the design.** On 2026-09-28 the API
 * served, for one source: connecting it (`POST /connectors`), disconnecting it
 * (`POST /connectors/{name}/disconnect`), editing its settings as one change
 * (`POST /connectors/{name}/edit`), replacing its key (`POST /connectors/{name}/key`), exporting its
 * record (`GET /console/connectors/{name}/export`), and Connect Lark (`/connectors/lark-app`). It
 * served no route that tests a connection: a probe needs the key, which only the worker reads, and a
 * successful probe has no outcome the worker's record can hold without claiming a full read, so it
 * waits on a decision. That act is an `UNAVAILABLE` sentence below and is drawn as
 * `kit/UnavailableAction`.
 *
 * **When a route lands, its sentence goes and a live control takes its place, in the same commit.**
 * `tests/connectors-page.test.tsx` reads every `retiredBy` against the API document, so this table
 * cannot go on saying "coming soon" about something that has arrived.
 *
 * Task ids: M27.11.9, M27.15.8
 */

/** Why each act that has no route cannot be pressed, and the shape of the path that retires it. */
export const UNAVAILABLE = Object.freeze({
  test: {
    reason:
      "Coming soon: testing a connection with one throttled call. Until then the worker's own reads show whether it works.",
    retiredBy: /^\/api\/v1\/connectors\/\{[^}]+\}\/(test|probe)$/,
  },
});

export type UnavailableAct = keyof typeof UNAVAILABLE;

/** The labels of the acts, one spelling each, so a menu and a test agree. */
export const ACT_LABELS = Object.freeze({
  open: "Open",
  connect: "Connect",
  connectLark: "Connect Lark",
  edit: "Edit settings",
  key: "Replace key",
  export: "Export record",
  disconnect: "Disconnect",
  test: "Test connection",
});
