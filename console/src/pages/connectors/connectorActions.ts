/**
 * What can be done to a source from the Connectors module, and for each act either where it works
 * or the one sentence saying why it cannot be pressed yet.
 *
 * **Measured against the routes on this branch, not against the design.** On 2026-09-29 the API
 * served, for one source: connecting it (`POST /connectors`), disconnecting it
 * (`POST /connectors/{name}/disconnect`), editing its settings as one change
 * (`POST /connectors/{name}/edit`), replacing its key (`POST /connectors/{name}/key`), exporting its
 * record (`GET /console/connectors/{name}/export`), testing its connection
 * (`POST /connectors/{name}/probe`, made by the worker and read back at
 * `GET /console/connectors/{name}/probe`), and Connect Lark (`/connectors/lark-app`). Every act on a
 * source works, so `UNAVAILABLE` is empty.
 *
 * **When a route lands, its sentence goes and a live control takes its place, in the same commit.**
 * `tests/connectors-page.test.tsx` reads every `retiredBy` against the API document, so this table
 * cannot go on saying "coming soon" about something that has arrived. Testing a connection left it
 * on 2026-09-29 (needs-rupash 107).
 *
 * Task ids: M27.11.9, M27.15.8
 */

/** One act that cannot be pressed yet: the sentence saying why, and the path that retires it. */
export interface Unavailable {
  readonly reason: string;
  readonly retiredBy: RegExp;
}

/** Why each act that has no route cannot be pressed. Empty: every act on a source has one. */
export const UNAVAILABLE: Readonly<Record<string, Unavailable>> = Object.freeze({});

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
