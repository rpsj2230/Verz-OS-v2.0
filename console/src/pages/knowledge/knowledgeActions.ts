/**
 * What can be done to knowledge from its pages that has no route yet, and the one sentence saying
 * why each cannot be pressed, with where the acts that do work are done.
 *
 * **Measured against the routes on this branch, not against the design.** On 2026-10-12 the API
 * served upload, add by link, the bulk queue, verify (one or several), a newer version, asking for
 * the whole company, hand-over, archive, the tasks and captured solutions. It served no route that
 * exports the inventory and records the export on the Exports screen.
 *
 * - **Archive** arrived with `0220`'s `know.archive_item`: a write past `know.item`'s policy, which
 *   admits only live rows, made by a function that repeats the reach the session was told. Its
 *   sentence went, and a live control took its place, in the same commit.
 * - **Export inventory** is recorded in `ops.data_export`, whose data sets are a closed list checked
 *   by the table (`brain.tables.data_export.ExportDataSet`, audit trail only), so a knowledge
 *   inventory is a new member and a migration widening the check. No export is offered meanwhile,
 *   not even of the rows shown: a list of titles leaving the building unrecorded is the channel the
 *   Exports screen exists to watch.
 *
 * **When a route lands, its sentence goes and a live control takes its place, in the same commit.**
 * `tests/knowledge-page.test.tsx` reads every `retiredBy` pattern against the API document, so this
 * table cannot go on saying "coming soon" about something that has arrived.
 *
 * Task ids: M27.15.40, M27.16.1
 */

/** Why each act with no route cannot be pressed, and the shape of the path whose arrival retires it. */
export const UNAVAILABLE = Object.freeze({
  exportInventory: {
    reason: "Coming soon: exporting the inventory, recorded on the Exports screen with who took it and why.",
    retiredBy: /^\/api\/v1\/knowledge\/(inventory|documents\/exports?)\b/,
  },
});

export type UnavailableAct = keyof typeof UNAVAILABLE;

/** Where the acts that happen elsewhere are done, as console addresses. */
export const WORKS_AT = Object.freeze({
  /** Where a request for the whole company is decided. */
  approvals: "/approvals",
  /** Every export taken, with who took it. */
  exports: "/import-export",
  /** Live sources, which are not documents. */
  connectors: "/connectors",
});

/** The five acts a document's page opens in a drawer, when the API offered them. */
export type DocumentAct = "verify" | "version" | "propose" | "handOver" | "archive";
