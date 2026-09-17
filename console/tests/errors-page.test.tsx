/**
 * The Errors screen: failed jobs by kind, failed questions by reference, a window that is asked
 * for, a full list said in words, and the log's absence said rather than drawn as nothing.
 *
 * Mounted on its own at its address, because the route table is a shared file this change does not
 * edit. The shapes are read from `brain.error_routes` itself.
 *
 * Task ids: none
 */

import { fireEvent, waitFor } from "@testing-library/react";
import { describe, expect, test } from "vitest";
import {
  ERRORS_API_PATH,
  ERRORS_PATH,
  FULL_LIST,
  LOG_IS_ON_THE_LOGS_SCREEN,
  NO_JOB_FAILURES,
  NO_REQUEST_FAILURES,
  PROCESS_LOG_IS_NOT_KEPT,
} from "../src/pages/errorsQuery";
import { json, mountPage, settled, type Answer } from "./support/pageHarness";
import { backendModelFields } from "./support/python";

const LIST = `GET /api/v1${ERRORS_API_PATH}`;
const ROUTES = "src/brain/error_routes.py";

function page(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    start: "2019-02-27T09:00:00Z",
    end: "2019-03-06T09:00:00Z",
    jobs: [
      {
        control: "spend_report_refresh",
        started_at: "2019-03-06T08:00:00Z",
        finished_at: "2019-03-06T08:00:02Z",
        kind: "IntegrityError",
      },
    ],
    jobs_truncated: false,
    requests: [
      {
        reference: "REFERENCE-SENTINEL",
        received_at: "2019-03-06T08:30:00Z",
        lane: "model",
        status: "degraded",
        duration_ms: 812.4,
      },
    ],
    requests_truncated: true,
    process_log_is_not_kept: true,
    failure_messages_stay_on_the_server: true,
    ...overrides,
  };
}

async function errorsPage(answers: Record<string, Answer>) {
  return mountPage(
    ERRORS_PATH,
    async () => {
      const { Errors } = await import("../src/pages/Errors");
      return <Errors />;
    },
    answers,
  );
}

describe("what the Errors screen draws", () => {
  test("a failed job by its kind, a failed question by its reference, and a full list in words", async () => {
    // What breaks if this is deleted: a failure an administrator was told the reference of that
    // cannot be found on the page, or a truncated list read as every failure there was.
    const { container } = await errorsPage({ [LIST]: () => json(page()) });

    const text = container.textContent ?? "";
    expect(text).toContain("IntegrityError");
    expect(text).toContain("REFERENCE-SENTINEL");
    expect(text).toContain("Degraded");
    expect(text).toContain("812 ms");
    expect(text).toContain(FULL_LIST);
    expect(text).toContain(PROCESS_LOG_IS_NOT_KEPT);
  });

  test("two empty lists are two sentences, and the log sentence leaves when the API stops sending it", async () => {
    // What breaks if this is deleted: empty tables that read as not loaded, or a page that goes
    // on saying the log is not kept after a log store exists.
    const { container } = await errorsPage({
      [LIST]: () =>
        json(page({ jobs: [], requests: [], requests_truncated: false, process_log_is_not_kept: false })),
    });

    expect(container.querySelectorAll("table")).toHaveLength(0);
    expect(container.textContent).toContain(NO_JOB_FAILURES);
    expect(container.textContent).toContain(NO_REQUEST_FAILURES);
    expect(container.textContent).not.toContain(PROCESS_LOG_IS_NOT_KEPT);
    expect(container.textContent).toContain(LOG_IS_ON_THE_LOGS_SCREEN);
    expect(container.querySelector('a[href="/logs"]')).not.toBeNull();
  });

  test("choosing a window asks for that window", async () => {
    // What breaks if this is deleted: a window control that changes the label and not the request.
    const { container, sent } = await errorsPage({ [LIST]: () => json(page()) });

    fireEvent.change(container.querySelector("select") as HTMLSelectElement, { target: { value: "24" } });
    await waitFor(() => {
      expect(sent.map((one) => one.path)).toContain(`/api/v1${ERRORS_API_PATH}?hours=24`);
    });
    await settled(container);
    expect(sent[0]?.path).toBe(`/api/v1${ERRORS_API_PATH}?hours=168`);
  });

  test("every field the page reads is a field the route declares", () => {
    // What breaks if this is deleted: a renamed field that the page goes on reading as empty.
    const body = page();
    expect(Object.keys(body).sort()).toEqual(backendModelFields(ROUTES, "ErrorsPage").sort());
    const job = (body.jobs as Record<string, unknown>[])[0] ?? {};
    const request = (body.requests as Record<string, unknown>[])[0] ?? {};
    expect(Object.keys(job).sort()).toEqual(backendModelFields(ROUTES, "JobFailureView").sort());
    expect(Object.keys(request).sort()).toEqual(backendModelFields(ROUTES, "RequestFailureView").sort());
  });
});
