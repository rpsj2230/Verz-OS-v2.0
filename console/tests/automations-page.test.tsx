/**
 * The Automations module on the shared page kit: the list of every automation a reader may see, one
 * automation's page in its three views, and the five confirmed changes.
 *
 * The failures worth testing here are not layout failures. They are: a change sent without the
 * confirmation the page was sent, or without the person agreeing to it; a change offered that the
 * API said this reader may not make; a schedule form that says what it accepts only after a
 * refusal; a figure drawn where nothing records one; an internal id in the page's text; and an act
 * called "not available yet" whose route has arrived.
 *
 * **Reachable means through the application's own route table**, as the other page tests mount it:
 * `routes` from `src/App.tsx` on a memory router, signed in through the real session modules and
 * answered by a stand-in API. The request bodies are held against the API document.
 *
 * Task ids: M27.12.3, M27.15.37, M39.6.1.5, M27.16.1
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import { NOT_RECORDED, UNAVAILABLE_MARK } from "../src/components/kit";
import { ACT_LABELS, UNAVAILABLE } from "../src/pages/automations/automationActions";
import { HOUR_LABEL, DAY_LABEL, EVERY_LABEL, REVIEW_SCHEDULE } from "../src/pages/automations/AutomationActs";
import { AUTOMATIONS_HEADING } from "../src/pages/automations/AutomationsPage";
import { AUTOMATIONS_ADDRESS, readAutomationRows } from "../src/pages/automations/automationsQuery";
import { fakeIdentityProvider, loadConsole, signIn, type FakeIdp } from "./support/auth";
import { declaredNavigation } from "./support/navigation";
import { apiDocument, declaredPropertyNames, declaredRequestBodySchema } from "./support/openapi";
import { installRadixStubs } from "./support/radix";
import { readConsoleFile } from "./support/repo";

const CONSOLE_ORIGIN = "https://console.test";

/** A principal id nothing else could contain, so finding it in the page's text is a leak. */
const OWNER_ID = "u_owner_sentinel_5a1";
const CONFIRMATION = "c".repeat(64);

beforeAll(async () => {
  installRadixStubs();
  await import("../src/pages/Automation");
}, 60_000);

function aRow(over: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    automation_id: "auto_one",
    name: "I tell you each week which questions went unanswered",
    agent_id: "quote_helper",
    agent_name: "Quote helper",
    owner_name: "Olive Owner",
    schedule: "every Monday at 07:00 UTC",
    state: "running",
    next_run_at: "2019-03-11T07:00:00Z",
    last_run_at: "2019-03-04T07:00:00Z",
    last_outcome: "succeeded",
    ...over,
  };
}

const LIST = {
  items: [
    aRow(),
    aRow({
      automation_id: "auto_gone",
      name: "I list the approvals waiting on you",
      owner_name: "Someone no longer here",
      state: "ownerless",
      next_run_at: null,
      last_run_at: null,
      last_outcome: null,
    }),
  ],
  next_cursor: null,
};

function aDetail(over: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    automation: aRow(),
    guards: "Unanswered questions go unnoticed for a week.",
    stopped_because: null,
    cannot_run: null,
    cadence: { every: "week", hour_utc: 7, weekday: 0 },
    installed_by_name: "Olive Owner",
    installed_at: "2019-02-01T09:00:00Z",
    runs: [
      {
        finished_at: "2019-03-04T07:00:00Z",
        outcome: "succeeded",
        reason: null,
        ran_as_name: "Olive Owner",
        reach: "same",
        result: ["3 asked in web that crm would have answered"],
      },
    ],
    basis: "everyone",
    history: [{ at: "2019-02-01T09:00:00Z", what: "Installed", by_name: "Olive Owner" }],
    confirmation: CONFIRMATION,
    may_pause: true,
    may_resume: false,
    resume_becomes: null,
    may_reschedule: true,
    may_remove: true,
    may_adopt: false,
    schedule_accepts: "Every day, every weekday or one day a week, at a whole hour in UTC (0 to 23).",
    weekdays: ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
    confirm_pause: "It stops running until somebody resumes it.",
    confirm_resume: "It runs again at its next scheduled time.",
    confirm_reschedule: "It will run on the new schedule.",
    confirm_remove: "It never runs again and cannot be resumed.",
    confirm_adopt: "It will run as you.",
    task: "automation.unanswered_questions",
    template_id: "unanswered_questions",
    owner_id: OWNER_ID,
    ...over,
  };
}

const STATS = {
  automation_id: "auto_one",
  basis: "everyone",
  last_run_at: "2019-03-04T07:00:00Z",
  next_run_at: "2019-03-11T07:00:00Z",
  periods: [
    { range: "7d", runs: 1, succeeded: 1, failed: 0, refused: 0 },
    { range: "30d", runs: 4, succeeded: 3, failed: 1, refused: 0 },
  ],
  unrecorded: [{ figure: "run_cost", why: "No automation run records a cost." }],
};

interface Answer {
  readonly status?: number;
  readonly body: unknown;
}

function answers(detail: Record<string, unknown> = aDetail()): Readonly<Record<string, Answer>> {
  return {
    "/api/v1/console/automations": { body: LIST },
    "/api/v1/console/automations/auto_one": { body: detail },
    "/api/v1/console/automations/auto_one/stats": { body: STATS },
  };
}

interface Mounted {
  readonly container: HTMLElement;
  readonly idp: FakeIdp;
}

async function consoleAt(
  path: string,
  given: Readonly<Record<string, Answer>> = answers(),
  posted: Answer = { body: aDetail({ automation: aRow({ state: "paused", next_run_at: null }) }) },
): Promise<Mounted> {
  const idp = fakeIdentityProvider({
    api(url, init) {
      const pathname = new URL(url, CONSOLE_ORIGIN).pathname;
      const answer = init?.method === "POST" ? posted : given[pathname];
      if (answer === undefined) {
        return null;
      }
      return new Response(JSON.stringify(answer.body), {
        status: answer.status ?? 200,
        headers: { "content-type": "application/json" },
      });
    },
  });
  const loaded = await loadConsole({ idp });
  await signIn(loaded);
  const { routes } = await import("../src/App");
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  const { container } = render(<RouterProvider router={router} />);
  await waitFor(() => {
    if (!container.querySelector("h1")) {
      throw new Error("the page has not arrived");
    }
  });
  await waitFor(() => {
    if (container.querySelector('[data-slot="loading-state"]') || container.querySelector('[data-slot="stats-strip"] [role="status"]')) {
      throw new Error("the page is still asking");
    }
  });
  return { container, idp };
}

function posts(idp: FakeIdp): { path: string; body: unknown }[] {
  return idp.calls
    .filter((call) => call.init?.method === "POST" && new URL(call.url, CONSOLE_ORIGIN).pathname.startsWith("/api/"))
    .map((call) => ({
      path: new URL(call.url, CONSOLE_ORIGIN).pathname,
      body: call.init?.body === undefined ? undefined : (JSON.parse(String(call.init.body)) as unknown),
    }));
}

async function press(name: string, within_: HTMLElement | null = null): Promise<void> {
  const button = within_ === null ? screen.getByRole("button", { name }) : within(within_).getByRole("button", { name });
  await act(async () => {
    fireEvent.click(button);
  });
}

describe("what this module agrees with the API about", () => {
  test("no act called not available yet has a route in the API document", () => {
    // What breaks if this is deleted: a person told they cannot bring an automation back after the
    // route to do it has landed.
    const paths = Object.keys((apiDocument()["paths"] ?? {}) as Record<string, unknown>);
    for (const [one, { retiredBy }] of Object.entries(UNAVAILABLE)) {
      expect(paths.filter((path) => retiredBy.test(path)), one).toEqual([]);
    }
    expect(UNAVAILABLE.reinstate.retiredBy.test("/api/v1/automations/{automation_id}/reinstate")).toBe(true);
    expect(UNAVAILABLE.reinstate.retiredBy.test("/api/v1/automations/{automation_id}/remove")).toBe(false);
  });

  test("each change sends exactly the fields its route declares", () => {
    // What breaks if this is deleted: a body field the route forbids, refused with a 422 naming no
    // field the page can draw, or a change sent without its confirmation.
    for (const one of ["pause", "resume", "remove", "adopt"]) {
      expect(declaredPropertyNames(declaredRequestBodySchema(`/api/v1/automations/{automation_id}/${one}`, "post")), one).toEqual([
        "confirmation",
      ]);
    }
    expect(declaredPropertyNames(declaredRequestBodySchema("/api/v1/automations/{automation_id}/reschedule", "post"))).toEqual([
      "confirmation",
      "every",
      "hour_utc",
      "weekday",
    ]);
    const acts = readConsoleFile("src/pages/automations/AutomationActs.tsx");
    expect(acts).toContain('const body: Record<string, unknown> = { confirmation: detail.confirmation };');
  });

  test("the served menu offers the module as Automations, in Agents and AI", () => {
    // What breaks if this is deleted: the entry drifts to another label or group, and somebody
    // following the design cannot find it.
    const holding = declaredNavigation("company").filter((one) =>
      one.entries.some((entry) => entry.to === AUTOMATIONS_ADDRESS && entry.label === AUTOMATIONS_HEADING),
    );
    expect(holding.map((one) => one.heading)).toEqual(["Agents and AI"]);
  });

  test("a row keeps only what was sent, and nothing reads a total", () => {
    // What breaks if this is deleted: a cell drawn as "unknown" for a field the API did not send, or
    // "showing 2 of 9", which is the disclosure by subtraction.
    const [only] = readAutomationRows({ items: [aRow({ next_run_at: null, schedule: null }), { name: "no id" }] });
    expect(only?.nextRunAt).toBeUndefined();
    expect(only?.schedule).toBeUndefined();
    for (const file of ["src/pages/automations/AutomationsPage.tsx", "src/pages/automations/automationsQuery.ts"]) {
      expect(readConsoleFile(file), file).not.toMatch(/\.total\b|\["total"\]/);
    }
  });
});

describe("the list", () => {
  test("every automation sent is a row with its agent, whom it runs as and its state, and no id", async () => {
    // What breaks if this is deleted: an ownerless automation drawn as running, or a list with a
    // principal id in it.
    const { container } = await consoleAt(AUTOMATIONS_ADDRESS);
    const text = container.textContent ?? "";
    expect(container.querySelector("h1")?.textContent).toBe(AUTOMATIONS_HEADING);
    expect(text).toContain("I tell you each week which questions went unanswered");
    expect(text).toContain("Quote helper");
    expect(text).toContain("Olive Owner");
    expect(text).toContain("Ownerless");
    expect(text).toContain("Running");
    expect(text).not.toContain(OWNER_ID);
    expect(text).not.toContain(" of 2");
  });
});

describe("one automation's page", () => {
  test("the dashboard draws the figures sent, the cost as not recorded, and a run's findings", async () => {
    // What breaks if this is deleted: a cost of nought for a figure nothing records.
    const { container } = await consoleAt(`${AUTOMATIONS_ADDRESS}/auto_one`);
    const strip = container.querySelector('[data-slot="kpi-strip"]') as HTMLElement;
    expect(strip.textContent).toContain("4");
    expect(strip.textContent).toContain(NOT_RECORDED);
    expect(container.textContent).toContain("3 asked in web that crm would have answered");
    expect(container.textContent).not.toContain(OWNER_ID);
  });

  test("identifiers are in Advanced on the Profile and nowhere else", async () => {
    // What breaks if this is deleted: a principal id or a task name back in the page's text.
    const { container } = await consoleAt(`${AUTOMATIONS_ADDRESS}/auto_one/profile`);
    const advanced = container.querySelector('[data-slot="advanced"]') as HTMLElement;
    expect(advanced.textContent).toContain(OWNER_ID);
    advanced.remove();
    expect(container.textContent).not.toContain(OWNER_ID);
    expect(container.textContent).not.toContain("automation.unanswered_questions");
  });

  test("only the changes the API offers are drawn, and a pause is sent only once it is confirmed", async () => {
    // What breaks if this is deleted: a resume offered that the API refuses, or a pause sent by one
    // press with nobody having read what it does.
    const { idp } = await consoleAt(`${AUTOMATIONS_ADDRESS}/auto_one`);
    expect(screen.queryByRole("button", { name: ACT_LABELS.resume })).toBeNull();
    expect(screen.queryByRole("button", { name: ACT_LABELS.adopt })).toBeNull();
    await press(ACT_LABELS.pause);
    const dialog = await screen.findByRole("alertdialog");
    expect(dialog.textContent).toContain("It stops running until somebody resumes it.");
    expect(posts(idp)).toEqual([]);
    await press(ACT_LABELS.pause, dialog);
    await waitFor(() => {
      expect(posts(idp)).toEqual([{ path: "/api/v1/automations/auto_one/pause", body: { confirmation: CONFIRMATION } }]);
    });
  });

  test("a change refused because the automation moved says so in the API's words", async () => {
    // What breaks if this is deleted: a stale change reading as a generic failure, or as done.
    await consoleAt(`${AUTOMATIONS_ADDRESS}/auto_one`, answers(), {
      status: 409,
      body: { outcome: "unconfirmed", sentence: "Look again and confirm." },
    });
    await press(ACT_LABELS.remove);
    const dialog = await screen.findByRole("alertdialog");
    await press(ACT_LABELS.remove, dialog);
    await waitFor(() => {
      expect(dialog.textContent).toContain("Look again and confirm.");
    });
  });

  test("the schedule form says what it accepts first, asks the day of a weekly one, and sends it", async () => {
    // What breaks if this is deleted: a schedule change that learns the format from a refusal, or a
    // weekly schedule sent with no day.
    const { idp } = await consoleAt(`${AUTOMATIONS_ADDRESS}/auto_one`);
    await press(ACT_LABELS.reschedule);
    const drawer = await screen.findByRole("dialog");
    expect(drawer.textContent).toContain("at a whole hour in UTC");
    expect(within(drawer).getByLabelText(DAY_LABEL)).toBeTruthy();
    fireEvent.change(within(drawer).getByLabelText(EVERY_LABEL), { target: { value: "day" } });
    expect(within(drawer).queryByLabelText(DAY_LABEL)).toBeNull();
    fireEvent.change(within(drawer).getByLabelText(EVERY_LABEL), { target: { value: "week" } });
    fireEvent.change(within(drawer).getByLabelText(DAY_LABEL), { target: { value: "4" } });
    fireEvent.change(within(drawer).getByLabelText(HOUR_LABEL), { target: { value: "9" } });
    await press(REVIEW_SCHEDULE, drawer);
    const dialog = await screen.findByRole("alertdialog");
    expect(dialog.textContent).toContain("Every Friday at 09:00 UTC");
    expect(posts(idp)).toEqual([]);
    await press(ACT_LABELS.reschedule, dialog);
    await waitFor(() => {
      expect(posts(idp)).toEqual([
        {
          path: "/api/v1/automations/auto_one/reschedule",
          body: { confirmation: CONFIRMATION, every: "week", hour_utc: 9, weekday: 4 },
        },
      ]);
    });
  });

  test("an ownerless automation offers adoption and a removed one offers nothing live", async () => {
    // What breaks if this is deleted: an ownerless automation with no way out of waiting, or a
    // removed one with a live control that pretends it can come back.
    await consoleAt(
      `${AUTOMATIONS_ADDRESS}/auto_one`,
      answers(aDetail({ automation: aRow({ state: "ownerless" }), may_adopt: true, may_pause: false, may_reschedule: false })),
    );
    expect(screen.getByRole("button", { name: ACT_LABELS.adopt })).toBeTruthy();
    document.body.innerHTML = "";

    const { container } = await consoleAt(
      `${AUTOMATIONS_ADDRESS}/auto_one`,
      answers(
        aDetail({
          automation: aRow({ state: "removed", next_run_at: null }),
          may_pause: false,
          may_reschedule: false,
          may_remove: false,
        }),
      ),
    );
    for (const one of [ACT_LABELS.pause, ACT_LABELS.resume, ACT_LABELS.reschedule, ACT_LABELS.remove, ACT_LABELS.adopt]) {
      expect(screen.queryByRole("button", { name: one })).toBeNull();
    }
    const inert = container.querySelectorAll(`[${UNAVAILABLE_MARK}]`);
    expect([...inert].map((one) => one.textContent)).toEqual([ACT_LABELS.reinstate]);
  });
});
