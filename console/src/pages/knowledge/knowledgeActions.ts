/**
 * What can be done to knowledge from its pages, and where the acts that happen elsewhere are done.
 *
 * **Measured against the routes on this branch, not against the design.** On 2026-10-24 the API
 * served upload, add by link, the bulk queue, verify (one or several), a newer version, asking for
 * the whole company, hand-over, archive, the tasks, captured solutions and the inventory export.
 * Nothing on a Knowledge page is waiting on a route, so no sentence about one is kept here.
 *
 * - **Archive** arrived with `0220`'s `know.archive_item`: a write past `know.item`'s policy, which
 *   admits only live rows, made by a function that repeats the reach the session was told.
 * - **Export inventory** arrived with `0276` (M25.3.3): `knowledge` joined the closed list of data
 *   sets `ops.data_export` checks (`brain.tables.data_export.ExportDataSet`), and the route records
 *   the export before it hands the file over. Its "coming soon" sentence went in the same commit.
 *
 * **When a route lands, its sentence goes and a live control takes its place, in the same commit.**
 * `tests/unit/test_console_explanations.py` reads every expiry against the routes the application
 * mounts, so nothing can go on saying "coming soon" about something that has arrived.
 *
 * Task ids: M27.15.40, M27.16.1, M25.3.3
 */

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
