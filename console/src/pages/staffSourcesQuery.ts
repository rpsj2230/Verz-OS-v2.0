/**
 * What the Staff sources screen asks the API for, and what may come back. No React.
 *
 * The split is `governQuery.ts`'s and `installQuery.ts`'s: this decides what may be asked and
 * what a payload is, the page renders it. A module of its own rather than four more exports on
 * `governQuery.ts`, because that one is four screens served by one router with one refusal shape
 * and a database behind every listing, and this screen is served by `brain.staff_source_routes`,
 * which refuses nobody on its listing and has no database at all.
 *
 * **Nothing here decides who may see what.** The request is identical for every caller. A reader
 * whose grant is scoped to a department reaches no staff source, because
 * `brain.console.staff_source_view` places one at `brain.console.govern.NOWHERE`, and they are
 * answered an empty page computed from grants this browser never receives.
 *
 * **Two addresses and the second is pressed rather than loaded.** The trial reads the chosen
 * source, which is a call to a server outside the install, and it names the company's staff,
 * which is a wider disclosure than the screen it sits on. `TRIAL_API_PATH` is therefore not
 * fetched when the page mounts; see `A_TRIAL_IS_A_REQUEST_SOMEBODY_MAKES`.
 *
 * **There is no control here for choosing a source or pointing it anywhere, and that is not a
 * gap in this file.** The choice and the location are installation settings, written once by the
 * setup wizard into the install's own environment and read by `brain.install.value_of`; no route
 * in the API writes an installation setting. The API sends the sentence saying so and this page
 * renders it, rather than composing one in a browser or drawing a form that would post to
 * nothing. See `A_CONTROL_THAT_POSTS_TO_NOTHING_IS_WORSE_THAN_NO_CONTROL`.
 *
 * **No count of anything, anywhere.** The options are the whole of what an install may choose or
 * none of them, and a trial is the whole plan or a refusal, so there is no partial answer for a
 * number to sit beside; `docs/screens.html` puts a count in the filter bar of every screen it
 * draws and that is the one convention this screen cannot carry. See
 * `THE_DESIGN_COUNTS_AND_THIS_SCREEN_CANNOT`.
 */

import type { components } from "../api/schema";
import { wasRead, type Read } from "./installQuery";

/**
 * Re-exported so a page reads one module. The helper is `installQuery.ts`'s and is not copied:
 * a second `wasRead` would be a second answer to whether a surface was read at all, and the
 * two would agree until somebody changed one of them.
 */
export { wasRead };
export type { Read };

/** One answer this install could give to where it keeps its staff list. */
export type SourceOption = components["schemas"]["SourceOptionView"];
/** Which one it has chosen, and what stands between that and being read. */
export type Selection = components["schemas"]["SelectionView"];
/** The whole page, as `brain.staff_source_routes.StaffSourcesView` sends it. */
export type StaffSources = components["schemas"]["StaffSourcesView"];
/** One trial, as `TrialView` sends it: a run, or the reason there is none. */
export type TrialAnswer = components["schemas"]["TrialView"];
/** One run of the chosen source that wrote nothing. */
export type TrialRun = components["schemas"]["TrialRunView"];

/**
 * Written down because fetching the trial with the page is the obvious simplification.
 */
export const A_TRIAL_IS_A_REQUEST_SOMEBODY_MAKES =
  "The trial asks the API to read this company's staff list from Google, Microsoft, Lark, a " +
  "sheet or a directory, and to name who would be added and who has gone missing. It is an " +
  "outbound call to somebody else's server and it is a wider disclosure than the rest of this " +
  "screen, at the content plane rather than the configuration one. A console that fetched it " +
  "on mount would contact a client's directory every time anybody opened the page, and would " +
  "make a reader who holds only the configuration grant issue a request they cannot be " +
  "answered. So there is a button, and nothing is asked until it is pressed.";

/**
 * Written down because the absence of a form on a configuration screen reads as unfinished.
 */
export const A_CONTROL_THAT_POSTS_TO_NOTHING_IS_WORSE_THAN_NO_CONTROL =
  "Which staff list this install reads and where that list is are installation settings. The " +
  "setup wizard writes them once at first run into the install's own environment and nothing " +
  "in the API writes one afterwards, so a picker or a text box here would collect an answer " +
  "and have nowhere to send it. The sentence the API returns says where the values are set " +
  "instead. It is carried on the response rather than written here for the reason every " +
  "sentence on these screens is: a console that composed its own would be a second account of " +
  "how this product is configured, out of step with the API within a release.";

/**
 * Written down because this screen is the one place the design of record cannot be followed.
 */
export const THE_DESIGN_COUNTS_AND_THIS_SCREEN_CANNOT =
  "Every screen in docs/screens.html puts a figure in its filter bar: 126 people, 34 " +
  "synthetic users, a budget used against a ceiling. This screen carries none, and the reason " +
  "is the disclosure rule rather than taste. Every listing on it is narrowed per caller by a " +
  "grant this browser never sees, so a number beside it is the subtraction CLAUDE.md forbids: " +
  "it would say how many sources a reader was not shown. ui/Chip.tsx already states the same " +
  "rule about itself, and the trial's plan is lists of people rather than counts of them for " +
  "the reason brain.identity.staff_sync.DryRun gives: an operator reading that four people " +
  "would be removed cannot tell whether the four are the four they expect.";

/** Where the API keeps this screen, and the trial behind it. */
export const STAFF_SOURCES_API_PATH = "/govern/staff_sources";
export const TRIAL_API_PATH = "/govern/staff_sources/trial";

/**
 * The console address.
 *
 * The screen's own key from `brain.console.screens`, underscore included, because
 * `brain.ops.console_screens.routed_screen_keys` matches the first path segment against that
 * registry and a prettier address would take this screen off the list of reads with no screen
 * while leaving it reachable. `App.tsx` gives the same argument about the five install screens.
 */
export const STAFF_SOURCES_PATH = "/staff_sources";

/** What the navigation calls it: the registry's own title for the screen. */
export const STAFF_SOURCES_LABEL = "Staff sources";

/** An empty page, whichever of the two reasons it is empty. */
const NOTHING: StaffSources = Object.freeze({
  options: [],
  selection: null,
  not_written_here: "",
});

/**
 * Read `brain.staff_source_routes.StaffSourcesView` out of a response body.
 *
 * An unreadable body yields an empty page rather than throwing, which is `readPeoplePage`'s
 * choice and for its reason: the shape is fixed by a response model in this repository, so a
 * body that is not this page is a console built against a different API and there is no
 * sentence worth composing about it.
 *
 * `selection` is carried as null when it is absent, and the page draws nothing where it would
 * be rather than a row with a dash in it. A reader who reaches no source and an install with
 * nothing to show are the same answer, and there is no field saying which.
 */
export function readStaffSources(payload: unknown): StaffSources {
  if (typeof payload !== "object" || payload === null) {
    return NOTHING;
  }
  const body = payload as {
    options?: unknown;
    selection?: unknown;
    not_written_here?: unknown;
  };
  if (!Array.isArray(body.options)) {
    return NOTHING;
  }
  return {
    options: body.options as SourceOption[],
    selection: (body.selection ?? null) as Selection | null,
    not_written_here:
      typeof body.not_written_here === "string" ? body.not_written_here : "",
  };
}

/**
 * The trial run, or the sentence saying there is none.
 *
 * The same shape `installQuery.Read<T>` carries and imported from there rather than declared
 * again, because it is the same decision: an absence turned into a value where a page would
 * otherwise write `trial?.plan ?? []` and draw an empty plan. That expression is one keystroke
 * and it renders "nothing would change" for an install that never looked.
 *
 * A body carrying neither is read as unread with whatever sentence arrived, which fails in the
 * direction that says less rather than the direction that reassures.
 */
export function readTrial(payload: TrialAnswer | null): Read<TrialRun> {
  const run = payload?.trial;
  if (run === null || run === undefined) {
    return { unread: payload?.unread ?? "" };
  }
  return { panel: run };
}

// ============================================================ what the nightly sync did
// Added on 2026-09-21 with `brain.ops.staff_sync_run`. Three reads and two writes, none of which
// applies a plan: the worker applies, and these show what it did, keep the credential it reads
// with, and hand a leaver's agent to whoever takes it on.

/** One scheduled run, as `brain.staff_source_routes.RunView` sends it. */
export type SyncRun = components["schemas"]["StaffSyncRunView"];
/** Whether the credential the sync reads with is held. Never the value. */
export type StaffCredential = components["schemas"]["StaffCredentialView"];
/** One agent whose owner the sync marked as having left. */
export type Transfer = components["schemas"]["TransferView"];

export const RUNS_API_PATH = "/govern/staff_sources/runs";
export const CREDENTIAL_API_PATH = "/govern/staff_sources/credential";
export const TRANSFERS_API_PATH = "/govern/staff_sources/transfers";

/** Where taking on one leaver's agent is posted. */
export function transferApiPath(agentId: string): string {
  return `${TRANSFERS_API_PATH}/${encodeURIComponent(agentId)}`;
}

/**
 * Written down because the runs are loaded with the page while the trial waits for a button.
 */
export const A_RUN_IS_A_RECORD_AND_NOT_A_CALL =
  "A run is a row the worker already wrote, so reading it contacts nobody outside the install, " +
  "unlike the trial. It names people, so the API answers it at the trial's plane and a reader " +
  "below that plane is answered no runs, which this page draws as nothing.";

/** The runs, newest first, or none for an unreadable body. */
export function readRuns(payload: unknown): readonly SyncRun[] {
  if (typeof payload !== "object" || payload === null) {
    return [];
  }
  const runs = (payload as { runs?: unknown }).runs;
  return Array.isArray(runs) ? (runs as SyncRun[]) : [];
}

/** The agents waiting for a new owner, or none for an unreadable body. */
export function readTransfers(payload: unknown): readonly Transfer[] {
  if (typeof payload !== "object" || payload === null) {
    return [];
  }
  const transfers = (payload as { transfers?: unknown }).transfers;
  return Array.isArray(transfers) ? (transfers as Transfer[]) : [];
}

/** The credential's standing, or null for an unreadable body. */
export function readCredential(payload: unknown): StaffCredential | null {
  if (typeof payload !== "object" || payload === null) {
    return null;
  }
  const body = payload as Partial<StaffCredential>;
  return typeof body.slot === "string" && typeof body.form === "string"
    ? (body as StaffCredential)
    : null;
}

/** What a blank credential is told, beside the field, before anything is confirmed or sent. */
export const CREDENTIAL_BLANK = "Paste the credential before replacing the one the sync reads with.";
