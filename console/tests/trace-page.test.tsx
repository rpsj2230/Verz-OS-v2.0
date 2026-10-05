/**
 * Reading a run's trace on a page (M32.5.2.3, M20.2.1): the form, the read, and the graph drawn.
 *
 * `TraceGraph` was a component no page rendered and `/api/v1/traces/{id}/read` a route no page
 * called. These tests hold the page that joins them: it sends nothing until the form holds a
 * trace id and a reason, it sends the reason the route records, it draws each step of a finished
 * run by its name and never a step's payload, it draws the route's one refusal as sent, and it
 * draws nothing for a body that is not a finished run.
 *
 * Task ids: M32.5.2.3, M20.2.1
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { fireEvent, render, waitFor } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import { TRACE_PROBLEMS, traceGraphPayload } from "../src/pages/traceQuery";
import { READ_TRACE_LABEL, TracePage as TraceRead, UNREADABLE_TRACE } from "../src/pages/audit/TracePage";
import { fakeIdentityProvider, loadConsole, signIn } from "./support/auth";
import { installRadixStubs } from "./support/radix";

const CONSOLE_ORIGIN = "https://console.test";
const TRACE = "trace-0a1b2c";
const READ = `/api/v1/traces/${TRACE}/read`;
const MASKED = "[masked:sha256:abcd]";

beforeAll(() => {
  installRadixStubs();
});

interface Sent {
  readonly method: string;
  readonly path: string;
  readonly body: unknown;
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

/** A finished run as `brain.trace_routes.TraceView` sends it: a request, an attempt and a tool call. */
function finished(outcome: string | null = "answered"): unknown {
  return {
    trace_id: TRACE,
    steps: [
      { step: 0, parent: null, kind: "request", name: "answer.request", attributes: outcome === null ? {} : { outcome }, payload_in: MASKED, payload_out: MASKED },
      { step: 1, parent: 0, kind: "model_attempt", name: "model_attempt", attributes: { outcome: "ok" }, payload_in: MASKED, payload_out: MASKED },
      { step: 2, parent: 0, kind: "tool_call", name: "tool_call", attributes: {}, payload_in: MASKED, payload_out: MASKED },
    ],
  };
}

async function tracePage(sent: Sent[], answer: () => Response): Promise<HTMLElement> {
  const idp = fakeIdentityProvider({
    api(url, init) {
      const parsed = new URL(url, CONSOLE_ORIGIN);
      sent.push({
        method: init?.method ?? "GET",
        path: parsed.pathname,
        body: init?.body === undefined ? null : JSON.parse(String(init.body)),
      });
      return parsed.pathname === READ ? answer() : null;
    },
  });
  const loaded = await loadConsole({ idp });
  await signIn(loaded);
  const router = createMemoryRouter([{ path: "/audit/trace", element: <TraceRead /> }], { initialEntries: ["/audit/trace"] });
  return render(<RouterProvider router={router} />).container;
}

function fill(container: HTMLElement, traceId: string, reason: string): void {
  const inputs = container.querySelectorAll("form input");
  fireEvent.change(inputs[0] as HTMLInputElement, { target: { value: traceId } });
  fireEvent.change(inputs[1] as HTMLInputElement, { target: { value: reason } });
  fireEvent.submit(container.querySelector("form") as HTMLFormElement);
}

describe("reading a run's trace", () => {
  test("a finished run is read with its reason and each step is drawn by name, never its payload", async () => {
    // What breaks if this is deleted: the page can stop calling the route, send no reason for the
    // read row, or draw a step's masked payload on a canvas a screenshot carries off.
    const sent: Sent[] = [];
    const container = await tracePage(sent, () => json(finished()));
    fill(container, TRACE, "Incident 42: a wrong answer was reported");
    await waitFor(() => expect(container.textContent).toContain("model_attempt"));
    expect(container.textContent).toContain("answer.request");
    expect(container.textContent).toContain("tool_call");
    expect(container.textContent).not.toContain(MASKED);
    expect(sent.filter((one) => one.method === "POST")).toEqual([
      { method: "POST", path: READ, body: { reason: "Incident 42: a wrong answer was reported" } },
    ]);
  });

  test("nothing is sent until the form holds a trace id and a reason", async () => {
    // What breaks if this is deleted: a read with no reason reaches the route, which refuses it
    // as malformed, and the person is told nothing they can act on.
    const sent: Sent[] = [];
    const container = await tracePage(sent, () => json(finished()));
    fill(container, TRACE, "   ");
    await waitFor(() => expect(container.textContent).toContain(TRACE_PROBLEMS.reason));
    expect(container.textContent).not.toContain(TRACE_PROBLEMS.traceId);
    expect(sent.filter((one) => one.method === "POST")).toEqual([]);
  });

  test("the route's one refusal is drawn as sent and no graph is drawn", async () => {
    // What breaks if this is deleted: a refused read can draw an empty canvas, which reads as a run
    // with no steps, or a sentence telling a reader without the role from a trace that is not there.
    const sent: Sent[] = [];
    const container = await tracePage(sent, () => json({ status: 404, message: "Not found." }, 404));
    fill(container, TRACE, "Checking a reported answer");
    await waitFor(() => expect(container.textContent).toContain("Not found."));
    expect(container.textContent).not.toContain("answer.request");
  });

  test("a body that is not a finished run draws nothing and says so", async () => {
    // What breaks if this is deleted: a trace whose root step names no ending is drawn as though
    // it had ended, which is the live graph graph.ts refuses.
    const sent: Sent[] = [];
    const container = await tracePage(sent, () => json(finished(null)));
    fill(container, TRACE, "Checking a reported answer");
    await waitFor(() => expect(container.textContent).toContain(UNREADABLE_TRACE));
    expect(container.textContent).not.toContain("model_attempt");
  });
});

describe("the read route's answer as a graph", () => {
  test("steps become nodes, parents become edges, and the root's outcome is the ending", () => {
    // What breaks if this is deleted: the page and the route can disagree on the shape, and every
    // read draws nothing, or an edge to the wrong step.
    expect(traceGraphPayload(finished())).toEqual({
      nodes: [
        { id: "0", label: "answer.request", kind: "request" },
        { id: "1", label: "model_attempt", kind: "model_attempt" },
        { id: "2", label: "tool_call", kind: "tool_call" },
      ],
      edges: [
        { from: "0", to: "1" },
        { from: "0", to: "2" },
      ],
      status: "answered",
    });
    expect((traceGraphPayload(finished(null)) as { status: unknown }).status).toBeUndefined();
    expect(READ_TRACE_LABEL).toBe("Read the trace");
  });
});
