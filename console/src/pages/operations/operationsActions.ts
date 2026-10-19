/**
 * What can be done from the Operations pages that has no route yet, by its label.
 *
 * **Measured against the routes on main on 2026-09-29.** The API pauses, resumes and runs a job now,
 * lists a job's past runs, exports the log and the audit trail, and reads everything else on these
 * pages. It serves no route that stops a run in progress, starts a backup rehearsal or imports
 * data. Each is drawn as a `kit/Explanation` of the `action` form, so the page shows the act
 * exists and is coming rather than hiding it or faking it, and its sentence is the server's
 * (`operations.stop_run`, `operations.start_rehearsal`, `operations.import_data` in
 * `brain.console.explanations`). Changing a rate limit was on this list until 2026-09-29, when
 * `brain.tuning_routes` landed and the Rate limits page drew the control.
 *
 * **When a route lands, its sentence goes and a live control takes its place, in the same commit.**
 * `tests/unit/test_console_explanations.py` reads every expiry against the routes the application
 * mounts, so a sentence cannot go on saying "coming soon" about something that has arrived.
 *
 * Task ids: M27.16.1, M27.10.2, M27.15.70
 */

/** The labels of the acts that are not built yet, one spelling each. */
export const ACT_LABELS = Object.freeze({
  stopRun: "Stop the run",
  startRehearsal: "Start a rehearsal",
  importData: "Import data",
});

