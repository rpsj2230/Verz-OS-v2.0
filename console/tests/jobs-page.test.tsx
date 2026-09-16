/**
 * The Scheduled jobs screen: each job's last run in words, a failure by its kind and never a
 * message, controls drawn only where they can reach something, and every control confirmed.
 *
 * Mounted on its own at its address, because the route table is a shared file this change does not
 * edit. The shapes are read from `brain.jobs_routes` itself.
 *
 * Task ids: M27.8.13
 */

import { fireEvent, waitFor } from "@testing-library/react";
import { describe, expect, test } from "vitest";
import {
  CONTROLS_SWITCHED_OFF,
  JOBS_API_PATH,
  JOBS_PATH,
  MESSAGE_KEPT_ON_THE_SERVER,
  NEVER_RUN,
  NO_JOBS,
  NO_RUN_CAN_BE_STOPPED,
  PAUSE,
  RESUME,
  RUN_NOW,
} from "../src/pages/jobsQuery";
import { button, json, mountPage, settled, type Answer } from "./support/pageHarness";
import { backendModelFields } from "./support/python";

const LIST = `GET /api/v1${JOBS_API_PATH}`;
const ROUTES = "src/brain/jobs_routes.py";

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

function page(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    as_of: "2019-03-06T09:00:00Z",
    jobs: [job()],
    controls_switched_on: true,
    may_control: true,
    no_run_can_be_stopped: true,
    every_change_is_in_the_audit_trail: true,
    ...overrides,
  };
}

async function jobsPage(answers: Record<string, Answer>) {
  return mountPage(
    JOBS_PATH,
    async () => {
      const { Jobs } = await import("../src/pages/Jobs");
      return <Jobs />;
    },
    answers,
  );
}

function names(container: HTMLElement): string[] {
  return [...container.querySelectorAll("tbody button")].map((one) => one.textContent ?? "");
}

describe("what the Scheduled jobs screen draws", () => {
  test("a failed run is drawn by its kind and the page says the message stays on the server", async () => {
    // What breaks if this is deleted: a failure drawn as a bare word with nothing to go on, or a
    // page that implies it is showing everything the run recorded.
    const { container } = await jobsPage({ [LIST]: () => json(page()) });

    const text = container.textContent ?? "";
    expect(text).toContain("Failed: IntegrityError");
    expect(text).toContain("KEEPS-TRUE-SENTENCE");
    expect(text).toContain(MESSAGE_KEPT_ON_THE_SERVER);
    expect(text).toContain(NO_RUN_CAN_BE_STOPPED);
  });

  test("a job never run, a job that cannot start, and an empty list are each said", async () => {
    // What breaks if this is deleted: a job whose runner is not built drawn with a Pause button
    // that is refused every time it is pressed.
    const { container } = await jobsPage({
      [LIST]: () =>
        json(
          page({
            jobs: [
              job({
                runnable: false,
                needs: "NEEDS-SENTENCE",
                last_started_at: null,
                last_outcome: null,
                last_failure_kind: null,
              }),
            ],
          }),
        ),
    });
    expect(container.textContent).toContain(NEVER_RUN);
    expect(container.textContent).toContain("NEEDS-SENTENCE");
    expect(names(container)).toEqual([]);

    const empty = await jobsPage({ [LIST]: () => json(page({ jobs: [] })) });
    expect(empty.container.textContent).toContain(NO_JOBS);
  });

  test("controls follow the API's two presentation facts, and resume survives the switch being off", async () => {
    // What breaks if this is deleted: buttons drawn for a reader who may not control, or a paused
    // job with no way back once the feature was turned off.
    const off = await jobsPage({
      [LIST]: () => json(page({ controls_switched_on: false, jobs: [job({ paused: true, pause_changed_by: "u_admin" })] })),
    });
    expect(names(off.container)).toEqual([RESUME]);
    expect(off.container.textContent).toContain(CONTROLS_SWITCHED_OFF);

    const reader = await jobsPage({ [LIST]: () => json(page({ may_control: false })) });
    expect(names(reader.container)).toEqual([]);

    const on = await jobsPage({ [LIST]: () => json(page()) });
    expect(names(on.container)).toEqual([PAUSE, RUN_NOW]);
  });
});

describe("a control", () => {
  test("is confirmed with what stops being kept true, posted to the job's own path, and re-read", async () => {
    // What breaks if this is deleted: a pause sent without saying what the install stops doing,
    // sent for the wrong job, or a page still drawing the job as running after it was paused.
    let paused = false;
    const pause = `POST /api/v1${JOBS_API_PATH}/spend_report_refresh/pause`;
    const { container, sent } = await jobsPage({
      [LIST]: () => json(page({ jobs: [job({ paused, pause_changed_by: paused ? "u_admin" : null })] })),
      [pause]: () => {
        paused = true;
        return json({
          control: "spend_report_refresh",
          paused: true,
          run_requested_at: null,
          changed_by: "u_admin",
          changed_at: "2019-03-06T09:00:00Z",
        });
      },
    });

    fireEvent.click(button(container, `${PAUSE}: spend_report_refresh`));
    expect(container.querySelector(".confirm")?.textContent).toContain("KEEPS-TRUE-SENTENCE");
    const confirm = [...container.querySelectorAll(".confirm button")].find((one) => one.textContent === PAUSE);
    fireEvent.click(confirm as HTMLButtonElement);

    await waitFor(() => {
      expect(container.textContent).toContain("is paused");
    });
    await settled(container);
    expect(sent.filter((one) => one.method === "POST").map((one) => one.path)).toEqual([
      `/api/v1${JOBS_API_PATH}/spend_report_refresh/pause`,
    ]);
    expect(container.textContent).toContain("Paused by u_admin");
  });

  test("every field the page reads is a field the route declares", () => {
    // What breaks if this is deleted: a renamed field that the page goes on reading as empty.
    expect(Object.keys(page()).sort()).toEqual(backendModelFields(ROUTES, "JobsPage").sort());
    expect(Object.keys(job()).sort()).toEqual(backendModelFields(ROUTES, "JobView").sort());
  });
});
