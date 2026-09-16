/**
 * The Live runs screen: what it draws, the three things it says it cannot draw, and the four
 * states it keeps apart.
 *
 * The failures worth testing here are the ones that look like the screen working. An empty table
 * looks like an idle install and is the same pixels as a parse failure; a stop button looks like
 * the Operate section of the design and reaches nothing. Both are asserted against over the
 * rendered page rather than over a constant this file agrees with itself about.
 *
 * **The page is mounted on its own**, at the address the route table will give it, because the
 * route table is a shared file this change does not edit. `.scratch/wire_live_runs_models.md`
 * holds the route and the menu row, and `tests/phone-width.test.tsx` holds every registered route
 * to a phone once it is added.
 *
 * **The shapes are read from the API's own source**, so a field renamed in
 * `brain.operate_routes` fails here rather than rendering nothing in production.
 *
 * Task ids: M27.2.2, M27.2.6
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { render, waitFor } from "@testing-library/react";
import { describe, expect, test } from "vitest";
import {
  durationWords,
  FIRST_RUN,
  LIVE_RUNS_API_PATH,
  LIVE_RUNS_PATH,
  NO_RUN_CAN_BE_STOPPED,
  NOTHING_RUNNING,
  NOTHING_WAITING,
  QUEUE_IS_NOT_READABLE,
  readLiveRuns,
  REPORT_ONLY,
  ACTING,
  REQUESTS_IN_FLIGHT_ARE_NOT_RECORDED,
  runningFor,
  SOMETHING_DID_NOT_WORK,
  stalledNote,
  THE_BRAIN_COULD_NOT_BE_REACHED,
  UNREADABLE_ANSWER,
} from "../src/pages/liveRunsQuery";
import { fakeIdentityProvider, loadConsole, signIn, type FakeIdp } from "./support/auth";
import { backendModelFields } from "./support/python";

const CONSOLE_ORIGIN = "https://console.test";
const OPERATION = `/api/v1${LIVE_RUNS_API_PATH}`;
const ROUTES = "src/brain/operate_routes.py";

/** A far-off instant, so nothing here is decided by the day the test runs. */
const AS_OF = "2019-03-06T09:00:00Z";

/** One answer in the shape `brain.operate_routes.LiveRunsView` serialises. */
function liveRuns(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    as_of: AS_OF,
    running: [
      {
        control: "retention_sweep",
        keeps_true: "SWEEP-SENTENCE",
        started_at: "2019-03-06T07:00:00Z",
        report_only: true,
        stalled: true,
      },
      {
        control: "denial_digest",
        keeps_true: "DIGEST-SENTENCE",
        started_at: "2019-03-06T08:55:00Z",
        report_only: false,
        stalled: false,
      },
    ],
    waiting: [
      {
        control: "canary_run",
        keeps_true: "CANARY-SENTENCE",
        due_since: "2019-03-06T06:00:00Z",
        late_by_seconds: 3 * 3600,
        first_run: false,
      },
      {
        control: "restore_drill",
        keeps_true: "DRILL-SENTENCE",
        due_since: AS_OF,
        late_by_seconds: 0,
        first_run: true,
      },
    ],
    stalled_after_seconds: 600,
    requests_in_flight_are_not_recorded: true,
    queue_is_not_readable: true,
    no_run_can_be_stopped: true,
    ...overrides,
  };
}

type Answer = () => Response;

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

/** Mount the page on its own at its address, against a stand-in API. */
async function livePage(answer: Answer): Promise<{ container: HTMLElement; idp: FakeIdp }> {
  const idp = fakeIdentityProvider({
    api(url) {
      return new URL(url, CONSOLE_ORIGIN).pathname === OPERATION ? answer() : null;
    },
  });
  const loaded = await loadConsole({ idp });
  await signIn(loaded);
  const { LiveRuns } = await import("../src/pages/LiveRuns");
  const router = createMemoryRouter([{ path: LIVE_RUNS_PATH, element: <LiveRuns /> }], {
    initialEntries: [LIVE_RUNS_PATH],
  });
  const { container } = render(<RouterProvider router={router} />);
  await waitFor(() => {
    if (container.querySelector("h1") === null || container.textContent?.includes("Loading.")) {
      throw new Error("the page has no answer yet");
    }
  });
  return { container, idp };
}

function rowsOf(container: HTMLElement, caption: string): string[][] {
  const table = [...container.querySelectorAll("table")].find(
    (one) => one.querySelector("caption")?.textContent === caption,
  );
  if (table === undefined) {
    return [];
  }
  return [...table.querySelectorAll("tbody tr")].map((row) =>
    [...row.querySelectorAll("td")].map((cell) => cell.textContent ?? ""),
  );
}

describe("what the live runs screen draws", () => {
  test("each running control is a row with its sentence, its start, its age in words and its mode", async () => {
    // What breaks if this is deleted: a control in the middle of a sweep drawn without the
    // sentence saying what it keeps true, or with its mode inverted, so an administrator reads a
    // sweep that is only reporting as one that is deleting.
    const { container } = await livePage(() => json(liveRuns()));

    const rows = rowsOf(container, "Scheduled controls that have started and not finished");

    expect(rows.map((row) => row[0])).toEqual(["retention_sweep", "denial_digest"]);
    expect(rows[0]?.[1]).toBe("SWEEP-SENTENCE");
    expect(rows[0]?.[2]).toBe("2019-03-06T07:00:00Z");
    expect(rows[0]?.[3]).toContain("2 hours");
    expect(rows[0]?.[4]).toBe(REPORT_ONLY);
    expect(rows[1]?.[3]).toBe("5 minutes");
    expect(rows[1]?.[4]).toBe(ACTING);
  });

  test("a stalled run carries the scheduler's line in words and a running one does not", async () => {
    // What breaks if this is deleted: a run whose process died an hour ago reads exactly like
    // one that started a minute ago, which is the one question this screen can raise about it.
    const { container } = await livePage(() => json(liveRuns()));

    const rows = rowsOf(container, "Scheduled controls that have started and not finished");

    expect(rows[0]?.[3]).toContain(stalledNote(600));
    expect(stalledNote(600)).toContain("10 minutes");
    expect(rows[1]?.[3]).not.toContain(stalledNote(600));
  });

  test("an owed control says how late it is in words, and a first run says so instead", async () => {
    // What breaks if this is deleted: a control that has never run reads as a control on time,
    // and a control three hours late reads as a bare number of seconds nobody converts.
    const { container } = await livePage(() => json(liveRuns()));

    const rows = rowsOf(container, "Scheduled controls owed a run and not yet started");

    expect(rows.map((row) => [row[0], row[3]])).toEqual([
      ["canary_run", "3 hours"],
      ["restore_drill", FIRST_RUN],
    ]);
    expect(rows[0]?.[1]).toBe("CANARY-SENTENCE");
  });

  test("the three things the API says the screen cannot show are said, and only while it says so", async () => {
    // What breaks if this is deleted: the sentences that stop an empty table reading as an idle
    // install disappear, or they stay on the page after the API stops sending the fact behind
    // them, which is a console going on saying a queue is unreadable after somebody made it
    // readable.
    const said = (await livePage(() => json(liveRuns()))).container.textContent ?? "";
    const unsaid =
      (
        await livePage(() =>
          json(
            liveRuns({
              requests_in_flight_are_not_recorded: false,
              queue_is_not_readable: false,
              no_run_can_be_stopped: false,
            }),
          ),
        )
      ).container.textContent ?? "";

    for (const sentence of [REQUESTS_IN_FLIGHT_ARE_NOT_RECORDED, QUEUE_IS_NOT_READABLE, NO_RUN_CAN_BE_STOPPED]) {
      expect(said).toContain(sentence);
      expect(unsaid).not.toContain(sentence);
    }
  });

  test("two empty lists are two sentences and no table", async () => {
    // What breaks if this is deleted: a caption over no rows, which reads as a table that has
    // not loaded, or a sentence that mentions other rows and so tells a reader there are some.
    const { container } = await livePage(() => json(liveRuns({ running: [], waiting: [] })));

    expect(container.querySelectorAll("table")).toHaveLength(0);
    expect(container.textContent).toContain(NOTHING_RUNNING);
    expect(container.textContent).toContain(NOTHING_WAITING);
    expect(NOTHING_RUNNING).not.toMatch(/grant|permission|other|hidden|more/i);
  });
});

describe("the four states the screen keeps apart", () => {
  test("a refusal is the API's own sentence with its reference, and draws no list", async () => {
    // What breaks if this is deleted: a refusal drawn as an empty page, which tells a reader
    // nothing is running when what happened is that the request was refused.
    const { container } = await livePage(() =>
      json({ message: "I could not find that.", trace_id: "TRACE-SENTINEL" }, 404),
    );

    expect(container.textContent).toContain(SOMETHING_DID_NOT_WORK);
    expect(container.textContent).toContain("I could not find that.");
    expect(container.textContent).toContain("TRACE-SENTINEL");
    expect(container.textContent).not.toContain(NOTHING_RUNNING);
  });

  test("a Brain that cannot be reached is a different sentence from one that refused", async () => {
    // What breaks if this is deleted: a dropped connection reads as a refusal, and an
    // administrator goes looking for a grant when the network is down.
    const { container } = await livePage(() => {
      throw new TypeError("Failed to fetch");
    });

    expect(container.textContent).toContain(THE_BRAIN_COULD_NOT_BE_REACHED);
    expect(container.textContent).not.toContain(SOMETHING_DID_NOT_WORK);
  });

  test("an answer this console cannot read says so rather than drawing an idle install", async () => {
    // What breaks if this is deleted: a response from a different release parsed into two empty
    // lists, which is the install reported idle on the strength of a parse failure.
    const { container } = await livePage(() => json({ running: "not a list" }));

    expect(container.textContent).toContain(UNREADABLE_ANSWER);
    expect(container.textContent).not.toContain(NOTHING_RUNNING);
    expect(readLiveRuns(liveRuns())).not.toBeNull();
    expect(readLiveRuns({ ...liveRuns(), as_of: 5 })).toBeNull();
    expect(readLiveRuns({ ...liveRuns(), waiting: null })).toBeNull();
    expect(readLiveRuns(null)).toBeNull();
  });
});

describe("what the screen asks for and what it offers", () => {
  test("one GET, with no query string, and no control on the page that could send anything else", async () => {
    // What breaks if this is deleted: a stop button that reaches nothing, which is the control
    // `docs/admin-console.md` calls worse than no control, or a parameter the route ignores.
    const { container, idp } = await livePage(() => json(liveRuns()));

    const asked = idp.calls.filter((one) => one.url.includes(OPERATION));
    expect(asked.length).toBeGreaterThan(0);
    expect(asked.every((one) => (one.init?.method ?? "GET") === "GET")).toBe(true);
    expect(asked.every((one) => new URL(one.url, CONSOLE_ORIGIN).search === "")).toBe(true);
    expect(container.querySelectorAll("button, form, input")).toHaveLength(0);
  });

  test("every field the page reads is a field the route declares", () => {
    // What breaks if this is deleted: a field renamed in `brain.operate_routes` that this page
    // goes on reading, which renders as an empty cell on every row in production.
    expect(Object.keys(liveRuns()).sort()).toEqual(backendModelFields(ROUTES, "LiveRunsView").sort());
    const running = (liveRuns().running as Record<string, unknown>[])[0] ?? {};
    const waiting = (liveRuns().waiting as Record<string, unknown>[])[0] ?? {};
    expect(Object.keys(running).sort()).toEqual(backendModelFields(ROUTES, "RunningControlView").sort());
    expect(Object.keys(waiting).sort()).toEqual(backendModelFields(ROUTES, "OwedControlView").sort());
  });
});

describe("how a length of time is said", () => {
  test("to the two largest units, singular where one, and under a minute below one", () => {
    // What breaks if this is deleted: "1 hours", a run of forty seconds said as zero minutes,
    // or a week-old stall said to the minute across three units nobody reads.
    expect(durationWords(0)).toBe("under a minute");
    expect(durationWords(59)).toBe("under a minute");
    expect(durationWords(60)).toBe("1 minute");
    expect(durationWords(3_660)).toBe("1 hour 1 minute");
    expect(durationWords(2 * 86_400 + 3 * 3_600 + 4 * 60)).toBe("2 days 3 hours");
    expect(durationWords(86_400 + 5 * 60)).toBe("1 day 5 minutes");
    expect(durationWords(-30)).toBe("under a minute");
  });

  test("a run's age is measured against the API's instant and not the browser's clock", () => {
    // What breaks if this is deleted: a laptop whose clock is years ahead draws every run as
    // stalled for years, because the age was taken from the wrong clock.
    expect(runningFor("2019-03-06T07:00:00Z", AS_OF)).toBe("2 hours");
  });
});
