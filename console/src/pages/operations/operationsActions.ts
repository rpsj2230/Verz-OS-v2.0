/**
 * What can be done from the Operations pages that has no route yet, and the one sentence saying why
 * each cannot be pressed.
 *
 * **Measured against the routes on main on 2026-09-29.** The API pauses, resumes and runs a job now,
 * lists a job's past runs, exports the log and the audit trail, and reads everything else on these
 * pages. It serves no route that stops a run in progress, changes a rate limit, starts a backup
 * rehearsal or imports data. Each is drawn as `kit/UnavailableAction` with the sentence below, so
 * the page shows the act exists and is coming rather than hiding it or faking it.
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
  changeLimits: {
    label: "Change limits",
    reason:
      "Coming soon: changing a rate limit from here, within bounds the product fixes. Today the limits are the product's own.",
    retiredBy: /^\/api\/v1\/install\/limits\/[^/]+/,
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
