/**
 * The Operations pages on the shared page kit: Background jobs and one job's page, Runs and queue,
 * Errors, Logs, Backup and recovery, Rate limits, Capacity, Storage, Artifacts, and Import and
 * export. Vault activity is the Credentials module's (`tests/credentials-page.test.tsx`).
 *
 * **Reachable means through the application's own route table.** Every page is mounted from
 * `src/App.tsx`'s routes on a memory router, signed in through the real session modules and answered
 * by a stand-in API, so a test passes only if the address resolves.
 *
 * **The rules these pages keep, each held once here.** A figure nothing measured reads "Not recorded
 * yet" and never nought; a person is named and never shown as a principal id; every act whose route
 * exists works through a confirmation and every act without one is inert with its reason; a list
 * that nothing looked at is a sentence and never an empty table; and every field a page reads is one
 * the Python model declares, read out of the Python source rather than out of this console.
 *
 * Task ids: M27.8.13, M27.15.47, M27.15.48, M27.16.1
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, test, vi } from "vitest";
import { NOT_RECORDED, UNAVAILABLE_MARK } from "../src/components/kit";
import { durationWords, runningFor } from "../src/pages/liveRunsQuery";
import { LANE_BASIS_WORDS, TIER_BASIS_WORDS } from "../src/pages/errorsQuery";
import { keptUntil, narrowed, NO_ARTIFACT_FILTERS, offeredKinds } from "../src/pages/artifactsQuery";
import { windowOf } from "../src/pages/dataTransferQuery";
import { filtersFrom, logsApiPath, logsExportApiPath, LOGS_PAGE_SIZE } from "../src/pages/logsQuery";
import { UNAVAILABLE } from "../src/pages/operations/operationsActions";
import { jobName } from "../src/pages/operations/parts";
import { NOTHING_LOOKED as NOTHING_LOOKED_AT_COPIES } from "../src/pages/operations/RecoveryPage";
import { NOTHING_LOOKED as NOTHING_LOOKED_AT_WINDOWS } from "../src/pages/operations/LimitsPage";
import { CHANGE_LIMIT, KEEP_LIMIT, SAVE_LIMIT, TUNING_HEADING } from "../src/pages/tuningQuery";
import { NOTHING_RECORDED } from "../src/pages/operations/ArtifactsPage";
import { EXPORT_LABEL, KEEP_LABEL, NOT_A_WINDOW, NOT_EXPORTABLE } from "../src/pages/operations/DataTransferPage";
import { fakeIdentityProvider, loadConsole, signIn, type FakeIdp } from "./support/auth";
import { COMPANY_CONSOLE, NAVIGATION_ADDRESS } from "./support/navigation";
import { apiDocument, declaredRequestBodySchema } from "./support/openapi";
import { backendEnumMembers, backendModelFields } from "./support/python";
import { installRadixStubs } from "./support/radix";
import { readRepoFile } from "./support/repo";

const CONSOLE_ORIGIN = "https://console.test";
const JOBS_ROUTES = "src/brain/jobs_routes.py";
const INSTALL_ROUTES = "src/brain/install_routes.py";
const TUNING_ROUTES = "src/brain/tuning_routes.py";

beforeAll(async () => {
  installRadixStubs();
  await import("../src/pages/Job");
}, 60_000);

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

type Answer = (url: URL, init: RequestInit | undefined) => { readonly status?: number; readonly body: unknown } | null;

interface Mounted {
  readonly container: HTMLElement;
  readonly idp: FakeIdp;
}

async function open(path: string, answers: Readonly<Record<string, Answer>>): Promise<Mounted> {
  const idp = fakeIdentityProvider({
    api(url, init) {
      const parsed = new URL(url, CONSOLE_ORIGIN);
      if (parsed.pathname === NAVIGATION_ADDRESS) {
        return json(COMPANY_CONSOLE);
      }
      const answer = answers[`${(init?.method ?? "GET").toUpperCase()} ${parsed.pathname}`]?.(parsed, init);
      return answer === null || answer === undefined ? null : json(answer.body, answer.status ?? 200);
    },
  });
  const loaded = await loadConsole({ idp });
  await signIn(loaded);
  const { routes } = await import("../src/App");
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  const { container } = render(<RouterProvider router={router} />);
  await settled(container);
  return { container, idp };
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

async function settled(container: HTMLElement): Promise<void> {
  await waitFor(() => {
    if (!container.querySelector("main h1, [data-slot='page-header'] h1, [data-slot='detail-header'] h1")) {
      throw new Error("the page has not arrived");
    }
  });
  await waitFor(() => {
    if (container.querySelector('main [data-slot="loading-state"]')) {
      throw new Error("the page is still asking");
    }
  });
}

function asked(idp: FakeIdp, method = "GET"): URL[] {
  return idp.calls
    .filter((call) => (call.init?.method ?? "GET").toUpperCase() === method)
    .map((call) => new URL(call.url, CONSOLE_ORIGIN))
    .filter((url) => url.pathname.startsWith("/api/v1/") && url.pathname !== NAVIGATION_ADDRESS && url.pathname !== "/api/v1/me");
}

function mainText(container: HTMLElement): string {
  return container.querySelector("main")?.textContent ?? container.textContent ?? "";
}

// --------------------------------------------------------------------------- fixtures

function job(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    control: "spend_report_refresh",
    keeps_true: "KEEPS-TRUE-SENTENCE",
    every_seconds: 3600,
    destructive: false,
    report_only: false,
    runnable: true,
    needs: null,
    last_started_at: "2019-03-06T08:00:00Z",
    last_finished_at: "2019-03-06T08:00:02Z",
    last_outcome: "failed",
    last_report: null,
    last_failure_kind: "IntegrityError",
    last_succeeded_at: null,
    owed: false,
    late_by_seconds: null,
    paused: false,
    pause_changed_by: null,
    pause_changed_at: null,
    run_requested_at: null,
    run_requested_by: null,
    run_pending: false,
    ...overrides,
  };
}

function jobsPage(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    as_of: "2019-03-06T09:00:00Z",
    jobs: [job()],
    controls_switched_on: true,
    may_control: true,
    no_run_can_be_stopped: true,
    every_change_is_in_the_audit_trail: true,
    people: {},
    ...overrides,
  };
}

function period(range: string, started: number): Record<string, unknown> {
  return { range, since: "2019-02-04T09:00:00Z", started, succeeded: started - 3, failed: 2, reported_only: 1 };
}

function jobDetail(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    as_of: "2019-03-06T09:00:00Z",
    job: job({ paused: true, pause_changed_by: "u_admin", pause_changed_at: "2019-03-06T08:30:00Z" }),
    lost_silently: "LOST-SILENTLY-SENTENCE",
    controls_switched_on: true,
    may_control: true,
    periods: [period("7d", 5), period("30d", 12)],
    no_run_can_be_stopped: true,
    every_change_is_in_the_audit_trail: true,
    people: { u_admin: "Ada Admin" },
    ...overrides,
  };
}

function run(id: number, outcome: string, overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    run_id: `00000000-0000-4000-8000-00000000000${String(id)}`,
    started_at: `2019-03-0${String(id)}T08:00:00Z`,
    finished_at: `2019-03-0${String(id)}T08:00:02Z`,
    outcome,
    report_only: false,
    report: outcome === "ok" ? "REPORT-SENTENCE" : null,
    failure_kind: outcome === "failed" ? "TimeoutError" : null,
    ...overrides,
  };
}

const JOB_API = "/api/v1/jobs/spend_report_refresh";

// --------------------------------------------------------------------------- the shapes agree

describe("what the Operations pages agree with the API about", () => {
  test("every field the jobs pages read is a field the jobs routes declare", () => {
    // What breaks if this is deleted: a field renamed in `brain.jobs_routes` that the pages go on
    // reading, which renders as an empty cell or a missing figure on every install.
    expect(Object.keys(jobsPage()).sort()).toEqual(backendModelFields(JOBS_ROUTES, "JobsPage").sort());
    expect(Object.keys(job()).sort()).toEqual(backendModelFields(JOBS_ROUTES, "JobView").sort());
    expect(Object.keys(jobDetail()).sort()).toEqual(backendModelFields(JOBS_ROUTES, "JobDetail").sort());
    expect(Object.keys(period("7d", 1)).sort()).toEqual(backendModelFields(JOBS_ROUTES, "JobPeriodView").sort());
    expect(Object.keys(run(1, "ok")).sort()).toEqual(backendModelFields(JOBS_ROUTES, "JobRunView").sort());
  });

  test("every act drawn as unavailable names no route the API document declares", () => {
    // What breaks if this is deleted: a route for stopping a run, starting a rehearsal or
    // importing lands and the page goes on saying "coming soon" about it.
    const paths = Object.keys((apiDocument()["paths"] ?? {}) as Record<string, unknown>);
    for (const [act, { retiredBy }] of Object.entries(UNAVAILABLE)) {
      expect(paths.filter((path) => retiredBy.test(path)), act).toEqual([]);
    }
    // The positive case: each pattern does match the path it is waiting for.
    expect(UNAVAILABLE.stopRun.retiredBy.test("/api/v1/jobs/{name}/stop")).toBe(true);
    expect(UNAVAILABLE.startRehearsal.retiredBy.test("/api/v1/install/recovery/rehearsals")).toBe(true);
    expect(UNAVAILABLE.importData.retiredBy.test("/api/v1/data-transfer/imports")).toBe(true);
  });

  test("the log page sends only parameters the log and export routes declare", () => {
    // What breaks if this is deleted: a renamed parameter FastAPI discards without a word, so the
    // export carries every level while the page says it carries errors.
    const filters = filtersFrom(new URLSearchParams("level=error&event=x&period=week&order=oldest"));
    const route = readRepoFile("src/brain/log_routes.py");
    const pageSignature = /async def logs\(([\s\S]*?)\) -> LogPage:/.exec(route)?.[1] ?? "";
    const exportSignature = /async def export_logs\(([\s\S]*?)\) -> LogExport:/.exec(route)?.[1] ?? "";
    for (const name of new URL(`${CONSOLE_ORIGIN}${logsApiPath(filters, new Date(), "c1")}`).searchParams.keys()) {
      expect(pageSignature).toMatch(new RegExp(`\\b${name}:`));
    }
    const exported = [...new URL(`${CONSOLE_ORIGIN}${logsExportApiPath(filters, new Date())}`).searchParams.keys()];
    expect(exported.sort()).toEqual(["end", "event", "level", "order", "start"]);
    for (const name of exported) {
      expect(exportSignature).toMatch(new RegExp(`\\b${name}:`));
    }
    expect(LOGS_PAGE_SIZE).toBeLessThanOrEqual(Number(/^MAX_PAGE: Final = (\d+)$/m.exec(readRepoFile("src/brain/ops/log_store.py"))?.[1]));
  });

  test("every lane rule and tier step the API can send has words", () => {
    // What breaks if this is deleted: a rule added to the backend's enum shown as a bare code.
    expect(Object.keys(LANE_BASIS_WORDS).sort()).toEqual(Object.values(backendEnumMembers("src/brain/gate/classify.py", "LaneBasis")).sort());
    expect(Object.keys(TIER_BASIS_WORDS).sort()).toEqual(Object.values(backendEnumMembers("src/brain/models/routing.py", "TierBasis")).sort());
  });

  test("a length of time is said to its two largest units and a run's age against the API's instant", () => {
    // What breaks if this is deleted: "1 hours", or every run drawn as stalled on a laptop whose
    // clock is wrong, because the age was taken from the browser.
    expect(durationWords(59)).toBe("under a minute");
    expect(durationWords(3_660)).toBe("1 hour 1 minute");
    expect(durationWords(2 * 86_400 + 3 * 3_600 + 4 * 60)).toBe("2 days 3 hours");
    expect(runningFor("2019-03-06T07:00:00Z", "2019-03-06T09:00:00Z")).toBe("2 hours");
    expect(jobName("spend_report_refresh")).toBe("Spend report refresh");
  });

  test("a window of whole days includes the last day, and artifacts narrow what the page holds", () => {
    // What breaks if this is deleted: the last day's entries left out of every export, or the
    // artifact list offering a kind nothing on the page is.
    expect(windowOf("2019-03-04", "2019-03-05")).toEqual({ since: "2019-03-04T00:00:00.000Z", until: "2019-03-06T00:00:00.000Z" });
    expect(windowOf("", "2019-03-05")).toBeNull();
    const rows = [artifact({ artifact_id: "old", produced_at: "2019-01-01T00:00:00Z" }), artifact({ artifact_id: "new", kind: "deck" })];
    expect(offeredKinds(rows)).toEqual(["deck", "report"]);
    expect(narrowed(rows, NO_ARTIFACT_FILTERS).map((one) => one.artifact_id)).toEqual(["new", "old"]);
    expect(keptUntil(artifact({ kept_until: "", kept_because: "while the record exists" }))).toBe("while the record exists");
  });
});

// --------------------------------------------------------------------------- background jobs

async function chooseOnRow(name: string, label: string): Promise<void> {
  const trigger = screen.getByRole("button", { name: `Actions for ${name}` });
  trigger.focus();
  await act(async () => {
    fireEvent.keyDown(trigger, { key: "Enter" });
  });
  const menu = await screen.findByRole("menu");
  const item = within(menu).getByRole("menuitem", { name: label });
  item.focus();
  await act(async () => {
    fireEvent.keyDown(item, { key: "Enter" });
  });
}

describe("Background jobs", () => {
  test("each job is named in words with its state and last run, and no identifier or principal id is text", async () => {
    // What breaks if this is deleted: the list goes back to `spend_report_refresh` and "Paused by
    // u_admin", which is what the owner called cluttered.
    const { container } = await open("/jobs", {
      "GET /api/v1/jobs": () => ({ body: jobsPage({ jobs: [job({ paused: true, pause_changed_by: "u_admin" })] }) }),
    });
    const text = mainText(container);
    expect(text).toContain("Spend report refresh");
    expect(text).toContain("Failed: IntegrityError");
    expect(text).toContain("Paused");
    expect(text).not.toContain("spend_report_refresh");
    expect(text).not.toContain("u_admin");
    expect(container.querySelector('a[href="/jobs/spend_report_refresh"]')).not.toBeNull();
  });

  test("pausing is confirmed with what stops being kept true, sent once from the dialog, and the list is asked again", async () => {
    // What breaks if this is deleted: a pause sent without saying what the install stops doing,
    // sent for the wrong job, or a page still drawing the job as running after it was paused.
    let paused = false;
    const { idp } = await open("/jobs", {
      "GET /api/v1/jobs": () => ({ body: jobsPage({ jobs: [job({ paused })] }) }),
      [`POST ${JOB_API}/pause`]: () => {
        paused = true;
        return { body: { control: "spend_report_refresh", paused: true, run_requested_at: null, changed_by: "u_admin", changed_at: "2019-03-06T09:00:00Z" } };
      },
    });
    const listed = asked(idp).length;
    await chooseOnRow("Spend report refresh", "Pause");
    const dialog = await screen.findByRole("alertdialog", { name: "Pause Spend report refresh?" });
    expect(dialog.textContent).toContain("KEEPS-TRUE-SENTENCE");
    expect(asked(idp, "POST")).toEqual([]);
    await act(async () => {
      fireEvent.click(within(dialog).getByRole("button", { name: "Pause" }));
    });
    await screen.findByText("Spend report refresh is paused. The worker will not start it again until it is resumed.");
    expect(asked(idp, "POST").map((url) => url.pathname)).toEqual([`${JOB_API}/pause`]);
    await waitFor(() => expect(asked(idp).length).toBeGreaterThan(listed));
  });

  test("controls follow the API's two presentation facts, and resume survives the switch being off", async () => {
    // What breaks if this is deleted: a Pause offered to a reader who may not control, or a paused
    // job with no way back once the feature was turned off.
    await open("/jobs", {
      "GET /api/v1/jobs": () => ({ body: jobsPage({ controls_switched_on: false, jobs: [job({ paused: true })] }) }),
    });
    screen.getByRole("button", { name: "Actions for Spend report refresh" }).focus();
    await act(async () => {
      fireEvent.keyDown(screen.getByRole("button", { name: "Actions for Spend report refresh" }), { key: "Enter" });
    });
    const menu = await screen.findByRole("menu");
    expect(within(menu).getAllByRole("menuitem").map((one) => one.textContent)).toEqual(["Open", "Resume"]);
  });
});

describe("one background job's page", () => {
  test("the header carries the job's own counts and the history lists its runs by kind, never by message", async () => {
    // What breaks if this is deleted: a job's page with no figures, a failure drawn with its
    // message, or a run history that is not the list route's (M27.15.47).
    const { container, idp } = await open("/jobs/spend_report_refresh", {
      [`GET ${JOB_API}`]: () => ({ body: jobDetail() }),
      [`GET ${JOB_API}/runs`]: () => ({ body: { items: [run(2, "failed"), run(1, "ok")], next_cursor: null, truncated: false } }),
    });
    await waitFor(() => expect(mainText(container)).toContain("TimeoutError"));
    const header = container.querySelector('[data-slot="detail-header"]') as HTMLElement;
    expect(header.querySelector("h1")?.textContent).toBe("Spend report refresh");
    expect(header.textContent).toContain("12");
    expect(mainText(container)).toContain("REPORT-SENTENCE");
    expect(asked(idp).some((url) => url.pathname === `${JOB_API}/runs` && url.searchParams.get("limit") !== null)).toBe(true);
    // The last run finished, so there is no run to stop and nothing offers to stop one.
    expect(container.querySelector(`[${UNAVAILABLE_MARK}]`)).toBeNull();
  });

  test("stopping a run is offered, as not available yet, only while a run is going", async () => {
    // Found on the owner's install on 2026-09-29: a job that had never run offered "Stop the run".
    // What breaks if this is deleted: the unavailable act is drawn on every job again, or a job
    // with a run going stops saying that the run cannot be stopped here.
    const going = jobDetail({ job: job({ last_started_at: "2019-03-06T08:00:00Z", last_outcome: null, last_finished_at: null }) });
    const { container } = await open("/jobs/spend_report_refresh", {
      [`GET ${JOB_API}`]: () => ({ body: going }),
      [`GET ${JOB_API}/runs`]: () => ({ body: { items: [], next_cursor: null, truncated: false } }),
    });
    await waitFor(() => expect(container.querySelector('[data-slot="detail-header"] h1')).not.toBeNull());
    const stop = container.querySelector(`[${UNAVAILABLE_MARK}]`);
    expect(stop?.textContent).toContain(UNAVAILABLE.stopRun.label);
    expect(stop?.getAttribute("aria-disabled")).toBe("true");
  });

  test("the Profile names the person who paused it, and the About keeps the identifier in Advanced", async () => {
    // What breaks if this is deleted: "Paused by u_admin" coming back, or the identifier dropped
    // from the one place a support request can quote it.
    const profile = await open("/jobs/spend_report_refresh/profile", { [`GET ${JOB_API}`]: () => ({ body: jobDetail() }) });
    expect(mainText(profile.container)).toContain("by Ada Admin");
    expect(mainText(profile.container)).not.toContain("u_admin");

    const about = await open("/jobs/spend_report_refresh/about", { [`GET ${JOB_API}`]: () => ({ body: jobDetail() }) });
    expect(mainText(about.container)).toContain("LOST-SILENTLY-SENTENCE");
    const advanced = about.container.querySelector('[data-slot="advanced"]');
    expect(advanced?.textContent).toContain("spend_report_refresh");
  });
});

// --------------------------------------------------------------------------- runs, errors, logs

describe("Runs and queue, Errors and Logs", () => {
  test("a running job, a stalled one and an owed first run are said in words, and the notes follow the API's flags", async () => {
    // What breaks if this is deleted: a stalled run drawn like a healthy one, or a sentence about
    // what the page cannot show going on being said after the API stops sending it.
    const { container } = await open("/runs", {
      "GET /api/v1/operate/runs": () => ({
        body: {
          as_of: "2019-03-06T09:00:00Z",
          running: [{ control: "retention_sweep", keeps_true: "K", started_at: "2019-03-06T07:00:00Z", report_only: true, stalled: true }],
          waiting: [{ control: "canary_run", keeps_true: "K", due_since: "2019-03-06T08:00:00Z", late_by_seconds: 0, first_run: true }],
          stalled_after_seconds: 3600,
          requests_in_flight_are_not_recorded: true,
          queue_is_not_readable: false,
          no_run_can_be_stopped: true,
        },
      }),
    });
    const text = mainText(container);
    expect(text).toContain("Retention sweep");
    expect(text).toContain("2 hours");
    expect(text).toContain("Started over 1 hour ago");
    expect(text).toContain("Never run before");
    expect(text).toContain("Questions and agent runs are listed on Service levels");
    expect(text).not.toContain("queue's tables are not read");
  });

  test("a failed job by its kind and a failed question by its reference, and choosing a window asks for it", async () => {
    // What breaks if this is deleted: a failure with nothing to quote, or a window control that
    // changes the heading and not the request.
    const body = {
      start: "2019-02-27T09:00:00Z",
      end: "2019-03-06T09:00:00Z",
      jobs: [{ control: "spend_report_refresh", started_at: "2019-03-06T08:00:00Z", finished_at: null, kind: "IntegrityError" }],
      jobs_truncated: true,
      requests: [{ reference: "REF-SENTINEL", received_at: "2019-03-06T08:30:00Z", lane: "model", status: "failed", duration_ms: 812 }],
      requests_truncated: false,
      process_log_is_not_kept: false,
      failure_messages_stay_on_the_server: true,
    };
    expect(Object.keys(body).sort()).toEqual(backendModelFields("src/brain/error_routes.py", "ErrorsPage").sort());
    const { container, idp } = await open("/errors", { "GET /api/v1/errors": () => ({ body }) });
    const text = mainText(container);
    expect(text).toContain("IntegrityError");
    expect(text).toContain("REF-SENTINEL");
    expect(text).toContain("This list came back full");
    const window = screen.getByLabelText("Window");
    await act(async () => {
      fireEvent.change(window, { target: { value: "24" } });
    });
    await waitFor(() => expect(asked(idp).some((url) => url.searchParams.get("hours") === "24")).toBe(true));
  });

  test("the log's export asks for the search on screen and saves the file, and a cut-off period says so", async () => {
    // What breaks if this is deleted: an export of the rows paged to rather than the search, an
    // export of a different level from the one on screen, or a cut-off file read as the whole period.
    const created = vi.fn(() => "blob:log");
    vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: created, revokeObjectURL: vi.fn() }));
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    const row = {
      at: "2019-03-06T08:30:00Z",
      last_at: "2019-03-06T08:31:00Z",
      level: "error",
      event: "request failed",
      origin: "brain.app:747",
      reference: "REF-LOG",
      error_type: "TimeoutError",
      repeats: 3,
      fields: { outcome: "denied" },
    };
    const page = { start: "2019-03-05T09:00:00Z", end: "2019-03-06T09:00:00Z", items: [row], next_cursor: null, kept_for_days: 30, debug_is_not_kept: true, info_is_a_sample: true, worker_output_is_not_kept: true };
    expect(Object.keys(page).sort()).toEqual(backendModelFields("src/brain/log_routes.py", "LogPage").sort());
    const exported = { start: page.start, end: page.end, filename: "log.csv", document: "at,level\r\n", cut_off: true, told: "T" };
    expect(Object.keys(exported).sort()).toEqual(backendModelFields("src/brain/log_routes.py", "LogExport").sort());
    const { container, idp } = await open("/logs?level=error&period=week", {
      "GET /api/v1/logs": () => ({ body: page }),
      "GET /api/v1/logs/export": () => ({ body: exported }),
    });
    expect(mainText(container)).toContain("REF-LOG");
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /Export/ }));
    });
    await screen.findByText("The export was saved as a file.");
    await screen.findByText(/choose a shorter period for the rest/);
    const asking = asked(idp).find((url) => url.pathname === "/api/v1/logs/export");
    expect(asking?.searchParams.get("level")).toBe("error");
    expect(asking?.searchParams.get("limit")).toBeNull();
    expect(created).toHaveBeenCalledTimes(1);
  });
});

// --------------------------------------------------------------------------- platform screens

function recovery(panel: unknown, unread = ""): Record<string, unknown> {
  return {
    panel,
    unread,
    rehearsal: {
      every_days: 7,
      copies_kept_days: 35,
      promised_recovery_seconds: 7200,
      manifest_ends: ".manifest.json",
      record_ends: ".drill.json",
      no_control_here: "NO-CONTROL-HERE",
    },
  };
}

describe("Backup and recovery, Rate limits and Capacity", () => {
  test("nothing having looked is a sentence and no figures, and a restore nobody verified is not recorded rather than blank", async () => {
    // What breaks if this is deleted: an install nobody looked at drawn as one whose backups never
    // ran, or "Last verified restore" drawn beside a backup time with nothing in it.
    const unread = await open("/recovery", { "GET /api/v1/install/recovery": () => ({ body: recovery(null, "UNREAD-SENTENCE") }) });
    expect(mainText(unread.container)).toContain(NOTHING_LOOKED_AT_COPIES);
    expect(mainText(unread.container)).toContain("UNREAD-SENTENCE");
    expect(unread.container.querySelector('main [data-slot="kpi-strip"]')).toBeNull();

    const panel = {
      profile: "standard",
      copies: [
        { coverage: "database", facts: [{ name: "n", source: "measured", value: "COPY-VALUE", because: "b" }], within_objective: true, objective_seconds: 3600 },
        { coverage: "files", facts: [{ name: "n", source: "unknown", value: "", because: "NOTHING-COPIES-FILES" }], within_objective: false, objective_seconds: 3600 },
      ],
      last_verified: { name: "last verified restore", source: "unknown", value: "", because: "NEVER-VERIFIED" },
      measured_rto_seconds: null,
      assurance: "never verified",
      says: "SAYS",
      what_to_do: "WHAT-TO-DO",
      drill_is_due: true,
      unreadable: [],
    };
    const read = await open("/recovery", { "GET /api/v1/install/recovery": () => ({ body: recovery(panel) }) });
    const strip = read.container.querySelector('main [data-slot="kpi-strip"]') as HTMLElement;
    expect(strip.textContent).toContain(NOT_RECORDED);
    expect(strip.textContent).toContain("never verified");
    expect(mainText(read.container)).toContain("NOTHING-COPIES-FILES");
    expect(mainText(read.container)).toContain("NO-CONTROL-HERE");
    expect(read.container.querySelector(`[${UNAVAILABLE_MARK}]`)?.textContent).toContain(UNAVAILABLE.startRehearsal.label);
  });

  test("an absent throttling list is a sentence, the windows are listed, and nothing is drawn as coming soon", async () => {
    // What breaks if this is deleted: nothing having looked drawn as nobody being refused, or the
    // "coming soon" act left on the page after the route that changes a limit landed (M22.4.1).
    const body = {
      ceilings: [{ name: "xero", per_day: 5000, raisable: false, derived: false }],
      windows: [{ scope: "principal", applies_to: "each person", period: "minute", limit: 30, window_seconds: 60, raisable: true, when_unreachable: "REFUSES-WHEN-UNREACHABLE" }],
      throttled: null,
      unread: "NOTHING-COUNTS",
      unusual: null,
      unusual_unread: "",
    };
    expect(Object.keys(body).sort()).toEqual(backendModelFields(INSTALL_ROUTES, "LimitsView").sort());
    const { container } = await open("/limits", { "GET /api/v1/install/limits": () => ({ body }) });
    const text = mainText(container);
    expect(text).toContain(NOTHING_LOOKED_AT_WINDOWS);
    expect(text).toContain("NOTHING-COUNTS");
    expect(text).toContain("30 a minute");
    expect(text).toContain("REFUSES-WHEN-UNREACHABLE");
    expect(text).not.toMatch(/\btrue\b|\bfalse\b/);
    expect(container.querySelector(`[${UNAVAILABLE_MARK}]`)).toBeNull();
  });

  test("a reserved figure nobody read is not recorded yet, and a finding is the API's own sentence", async () => {
    // What breaks if this is deleted: "0 MiB reserved" or the declared figure copied into the
    // reserved one, which reads as two measurements agreeing.
    const body = {
      memory: { profile: "standard", host_total_mib: 16000, declared_mib: 4000, deployed_mib: null, breaches: ["BREACH-SENTENCE"], unbudgeted: [] },
      connections: [{ database: "application", admissible: 100, demand: 60, headroom: 40 }],
    };
    const { container } = await open("/connections", { "GET /api/v1/install/capacity": () => ({ body }) });
    const reserved = [...container.querySelectorAll('main [data-slot="stat-card"]')].find((card) =>
      card.textContent?.startsWith("Reserved by the compose files"),
    );
    expect(reserved?.textContent).toContain(NOT_RECORDED);
    expect(reserved?.textContent).not.toContain("MiB");
    expect(mainText(container)).toContain("BREACH-SENTENCE");
    expect(mainText(container)).toContain("application");
  });
});

// --------------------------------------------------------------------------- limits you can change

const LIMITS_BODY = {
  ceilings: [],
  windows: [],
  throttled: [],
  unread: "",
  unusual: null,
  unusual_unread: "NOTHING-COUNTED",
};

function tuningBody(mayChange: boolean, value = 30, saved = false) {
  return {
    knobs: [
      {
        name: "person_per_minute",
        kind: "rate",
        label: "Questions one person may ask a minute",
        unit: "a minute",
        value,
        default: 30,
        lowest: 5,
        highest: 120,
        saved,
        bounds_because: "BOUNDS-BECAUSE",
      },
    ],
    may_change: mayChange,
    in_force: "IN-FORCE-SENTENCE",
  };
}

describe("Limits you can change", () => {
  test("every field the card reads is a field the tuning route declares", () => {
    // What breaks if this is deleted: a field renamed in `brain.tuning_routes` that the card goes
    // on reading, which renders as an empty figure or a control drawn for nobody.
    const body = tuningBody(true);
    expect(Object.keys(body).sort()).toEqual(backendModelFields(TUNING_ROUTES, "TuningView").sort());
    expect(Object.keys(body.knobs[0] ?? {}).sort()).toEqual(backendModelFields(TUNING_ROUTES, "KnobView").sort());
    const declared = declaredRequestBodySchema("/api/v1/install/tuning/{name}", "put");
    expect(Object.keys(declared["properties"] as object)).toEqual(["value"]);
  });

  test("a reader who may not change a limit sees what is in force and between which bounds, and no control", async () => {
    // What breaks if this is deleted: a control drawn for a reader the write refuses, or the
    // figures withheld from a reader of the screen.
    const { container } = await open("/limits", {
      "GET /api/v1/install/limits": () => ({ body: LIMITS_BODY }),
      "GET /api/v1/install/tuning": () => ({ body: tuningBody(false) }),
    });
    const text = mainText(container);
    expect(text).toContain(TUNING_HEADING);
    expect(text).toContain("Questions one person may ask a minute");
    expect(text).toContain("30 a minute");
    expect(text).toContain("5 to 120");
    expect(text).toContain("IN-FORCE-SENTENCE");
    expect(screen.queryByRole("button", { name: new RegExp(`^${CHANGE_LIMIT}:`) })).toBeNull();
  });

  test("a figure outside the bounds is refused before anything is sent, and a figure inside is confirmed and sent", async () => {
    // What breaks if this is deleted: a change sent without its confirmation, a figure the
    // bounds refuse sent anyway, or the new figure not drawn from the API's answer.
    const { container, idp } = await open("/limits", {
      "GET /api/v1/install/limits": () => ({ body: LIMITS_BODY }),
      "GET /api/v1/install/tuning": () => ({ body: tuningBody(true) }),
      "PUT /api/v1/install/tuning/person_per_minute": () => ({ body: tuningBody(true, 12, true) }),
    });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: `${CHANGE_LIMIT}: Questions one person may ask a minute` }));
    });
    const form = container.querySelector('form[aria-label="Questions one person may ask a minute"]') as HTMLFormElement;
    const input = within(form).getByRole("textbox");
    for (const refused of ["0", "121", "2.5", ""]) {
      fireEvent.change(input, { target: { value: refused } });
      await act(async () => {
        fireEvent.submit(form);
      });
      expect(screen.queryByRole("alertdialog")).toBeNull();
    }
    expect(asked(idp, "PUT")).toEqual([]);

    fireEvent.change(input, { target: { value: "12" } });
    await act(async () => {
      fireEvent.submit(form);
    });
    const dialog = await screen.findByRole("alertdialog");
    expect(dialog.textContent).toContain("12 a minute");
    expect(dialog.textContent).toContain("IN-FORCE-SENTENCE");
    await act(async () => {
      fireEvent.click(within(dialog).getByRole("button", { name: KEEP_LIMIT }));
    });
    expect(asked(idp, "PUT")).toEqual([]);

    await act(async () => {
      fireEvent.submit(form);
    });
    await act(async () => {
      fireEvent.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: SAVE_LIMIT }));
    });
    await screen.findByText("Questions one person may ask a minute is now 12 a minute.");
    const sent = idp.calls.find((call) => call.init?.method === "PUT" && call.url.includes("/install/tuning/"));
    expect(JSON.parse(String(sent?.init?.body))).toEqual({ value: 12 });
    expect(mainText(container)).toContain("Set here");
  });
});

// --------------------------------------------------------------------------- storage

describe("Storage", () => {
  test("a counted bucket says what it holds, an uncounted one is not recorded yet, and a floor says at least", async () => {
    // What breaks if this is deleted: a bucket nobody counted drawn as holding nothing.
    const bucket = (name: string, usage: unknown, unread = "") => ({
      name,
      holds: "HOLDS",
      retention_days: 30,
      retention_reason: "R",
      versioned: true,
      public_read: false,
      kinds: [],
      usage,
      usage_unread: unread,
    });
    const body = {
      buckets: [
        bucket("counted", { objects: 3, bytes_stored: 2048, complete: true }),
        bucket("floor", { objects: 1000, bytes_stored: 1024, complete: false }),
        bucket("uncounted", null, "NOT-COUNTED-BECAUSE"),
      ],
      findings: [],
      endpoint: { address: null, prefix: "brain", backend: "s3", from_default: false, told: "TOLD" },
      connection: "CONNECTION",
      usage: "USAGE",
      names: "NAMES",
      retention: "RETENTION",
      manages: "MANAGES",
      read_at: "2019-03-06T09:00:00Z",
    };
    const { container } = await open("/storage", { "GET /api/v1/storage": () => ({ body }) });
    const text = mainText(container);
    expect(text).toContain("3 objects, 2.0 KB");
    expect(text).toContain("At least 1000 objects");
    expect(text).toContain(NOT_RECORDED);
    expect(container.querySelector(`[title="NOT-COUNTED-BECAUSE"]`)).not.toBeNull();
    expect(text).toContain("The address set for the store is not one this page can show.");
  });

});

// --------------------------------------------------------------------------- artifacts and export

function artifact(overrides: Record<string, unknown> = {}): {
  artifact_id: string;
  kind: string;
  agent_id: string;
  produced_for: string;
  produced_at: string;
  state: string;
  superseded_by: string;
  run_id: string;
  agent_version: string;
  kept_as: string;
  kept_until: string;
  kept_because: string;
} {
  return {
    artifact_id: "art_1",
    kind: "report",
    agent_id: "quote_helper",
    produced_for: "u_someone",
    produced_at: "2019-02-01T00:00:00Z",
    state: "current",
    superseded_by: "",
    run_id: "run_1",
    agent_version: "3",
    kept_as: "payload",
    kept_until: "2019-04-03T09:00:00Z",
    kept_because: "kept 30 days",
    ...overrides,
  } as ReturnType<typeof artifact>;
}

describe("Artifacts and Import and export", () => {
  test("nothing recorded is a sentence and never an empty table, and a row's identifiers are hidden columns", async () => {
    // What breaks if this is deleted: an estate nothing records drawn as one that produced
    // nothing, or principal ids and slugs back as the rows' text.
    expect(Object.keys(artifact()).sort()).toEqual(backendModelFields("src/brain/artifact_routes.py", "ArtifactView").sort());
    const unread = await open("/artifacts", { "GET /api/v1/govern/artifacts": () => ({ body: { artifacts: null, unread: "UNREAD", kept_rule: "RULE" } }) });
    expect(mainText(unread.container)).toContain(NOTHING_RECORDED);
    expect(unread.container.querySelector("main table")).toBeNull();

    const listed = await open("/artifacts", { "GET /api/v1/govern/artifacts": () => ({ body: { artifacts: [artifact()], unread: "", kept_rule: "RULE" } }) });
    const text = mainText(listed.container);
    expect(text).toContain("Report");
    expect(text).toContain("kept 30 days");
    expect(text).not.toContain("u_someone");
    expect(text).not.toContain("art_1");
  });

  test("an export is confirmed in the API's words, sends the route's five fields, and blank days send nothing", async () => {
    // What breaks if this is deleted: an export taken with no second step, a body key the route
    // refuses, or a blank window agreed to and then refused.
    vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: vi.fn(() => "blob:doc"), revokeObjectURL: vi.fn() }));
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    const listing = {
      catalogue: [{ key: "audit_trail", label: "Audit trail", direction: "export", carries: "C", runs: true, told: "T" }],
      reasons: ["regulatory_request"],
      exportable: true,
      form: "chain",
      form_told: null,
      exports: [],
      export_told: "EXPORT-TOLD",
      document_told: "DOCUMENT-TOLD",
      own_exports_told: "OWN",
      max_entries: 100000,
    };
    const { container, idp } = await open("/import-export", {
      "GET /api/v1/data-transfer": () => ({ body: listing }),
      "POST /api/v1/data-transfer/exports": () => ({
        body: { export: {}, filename: "audit.jsonl", document: "DOCUMENT-SENTINEL", told: "The export was recorded under your name." },
      }),
    });
    const form = container.querySelector(`form[aria-label="${EXPORT_LABEL}"]`) as HTMLFormElement;
    await act(async () => {
      fireEvent.submit(form);
    });
    expect(mainText(container)).toContain(NOT_A_WINDOW);
    expect(screen.queryByRole("alertdialog")).toBeNull();

    fireEvent.change(within(form).getByLabelText("Reference of the written request"), { target: { value: "MATTER-1" } });
    fireEvent.change(within(form).getByLabelText("First day"), { target: { value: "2019-03-04" } });
    fireEvent.change(within(form).getByLabelText("Last day"), { target: { value: "2019-03-05" } });
    await act(async () => {
      fireEvent.submit(form);
    });
    const dialog = await screen.findByRole("alertdialog");
    expect(dialog.textContent).toContain("EXPORT-TOLD");
    await act(async () => {
      fireEvent.click(within(dialog).getByRole("button", { name: KEEP_LABEL }));
    });
    expect(asked(idp, "POST")).toEqual([]);

    await act(async () => {
      fireEvent.submit(form);
    });
    await act(async () => {
      fireEvent.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: EXPORT_LABEL }));
    });
    await screen.findByText("The export was recorded under your name.");
    const sent = idp.calls.find((call) => call.init?.method === "POST" && call.url.includes("/data-transfer/exports"));
    const bodySent = JSON.parse(String(sent?.init?.body)) as Record<string, unknown>;
    const declared = declaredRequestBodySchema("/api/v1/data-transfer/exports", "post");
    expect(Object.keys(bodySent).sort()).toEqual(Object.keys(declared["properties"] as object).sort());
    expect(bodySent["until"]).toBe("2019-03-06T00:00:00.000Z");
    expect(container.innerHTML).not.toContain("DOCUMENT-SENTINEL");
  });

  test("a reader who may not export is told why and offered no form, and importing is inert", async () => {
    // What breaks if this is deleted: a form offered to somebody the route will refuse after they
    // filled it in, or an import button that reaches nothing.
    const { container } = await open("/import-export", {
      "GET /api/v1/data-transfer": () => ({
        body: {
          catalogue: [],
          reasons: [],
          exportable: false,
          form: null,
          form_told: null,
          exports: [],
          export_told: "E",
          document_told: "D",
          own_exports_told: "O",
          max_entries: 1,
        },
      }),
    });
    expect(mainText(container)).toContain(NOT_EXPORTABLE);
    expect(container.querySelector(`form[aria-label="${EXPORT_LABEL}"]`)).toBeNull();
    expect(container.querySelector(`[${UNAVAILABLE_MARK}]`)?.textContent).toContain(UNAVAILABLE.importData.label);
  });
});
