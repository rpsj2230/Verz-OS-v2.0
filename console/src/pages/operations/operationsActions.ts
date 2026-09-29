/**
 * What can be done from the Operations pages that has no route yet, and the one sentence saying why
 * each cannot be pressed.
 *
 * **Measured against the routes on main on 2026-09-29.** The API pauses, resumes and runs a job now,
 * lists a job's past runs, exports the log and the audit trail, and reads everything else on these
 * pages. It serves no route that stops a run in progress, starts a backup rehearsal or imports
 * data. Each is drawn as `kit/UnavailableAction` with the sentence below, so the page shows the act
 * exists and is coming rather than hiding it or faking it. Changing a rate limit was on this list
 * until 2026-09-29, when `brain.tuning_routes` landed and the Rate limits page drew the control.
 *
 * **When a route lands, its sentence goes and a live control takes its place, in the same commit.**
 * `tests/operations-pages.test.tsx` reads every `retiredBy` against the API document, so this table
 * cannot go on saying "coming soon" about something that has arrived.
 *
 * Task ids: M27.16.1, M27.10.2
 */

export const UNAVAILABLE = Object.freeze({
  stopRun: {
    label: "Stop the run",
    reason:
      "Not available yet: stopping a run that has started. Pausing the job stops the schedule starting it again.",
    retiredBy: /^\/api\/v1\/(jobs|operate\/runs)\/\{[^}]+\}\/(stop|cancel)\b/,
  },
  startRehearsal: {
    label: "Start a rehearsal",
    reason:
      "Coming soon: starting a restore rehearsal from here. Today it is run on the server, as the rehearsal card says.",
    retiredBy: /^\/api\/v1\/install\/recovery\/(drills?|rehearsals?)\b/,
  },
  importData: {
    label: "Import data",
    reason: "Coming soon: importing data from this page. Documents are added on the Knowledge page today.",
    retiredBy: /^\/api\/v1\/data-transfer\/imports?\b/,
  },
});

export type UnavailableAct = keyof typeof UNAVAILABLE;
