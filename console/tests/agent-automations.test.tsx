/**
 * The Automations tab's list of installed automations, and the confirmed Start and Stop.
 *
 * **Reachable means through the application's own route table**, mounted and signed in as
 * `tests/automation-gallery.test.tsx` mounts the gallery, so a test that rendered the list alone
 * cannot pass with the tab never wired to it.
 *
 * **What the server decides is not re-tested here.** Who may see, start or stop an automation, and
 * whether a confirmation matches, are `tests/unit/test_automation_schedule_routes.py`'s. What is
 * proved here is the half a browser owns: a control is drawn only where the API sent its digest,
 * nothing is written before the second press, the second press sends that digest and nothing else,
 * a refusal is shown in the API's words, and the list is asked for again after a change.
 *
 * Task ids: M39.6.1.4, M39.6.1.5, M38.2.2.5
 */

import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { act, fireEvent, render, waitFor } from "@testing-library/react";
import { beforeAll, describe, expect, test } from "vitest";
import {
  AUTOMATIONS_LABEL,
  KEEP_LABEL,
  NOT_CHANGED,
  START_LABEL,
  STARTED_TITLE,
  STOP_LABEL,
  startQuestion,
} from "../src/components/AgentAutomations";
import { changeBody, readAgentAutomations, readNotChanged } from "../src/pages/agentAutomationsQuery";
import { fakeIdentityProvider, loadConsole, signIn } from "./support/auth";
import {
  declaredProperty,
  declaredPropertyNames,
  declaredRequestBodySchema,
  declaredResponseSchema,
  resolvedSchema,
} from "./support/openapi";

const CONSOLE_ORIGIN = "https://console.test";
const WORKSPACE = "/api/v1/agents/quote-helper/workspace";
const GALLERY = "/api/v1/agents/quote-helper/automation-templates";
const LIST = "/api/v1/agents/quote-helper/automations";
const START = "/api/v1/agents/quote-helper/automations/auto_one/start";

const START_DIGEST = "a".repeat(64);
const STOP_DIGEST = "b".repeat(64);
const QUESTIONS = "I list the questions I could not answer this week";
const SUMMARY = "I write you a summary of my week's work";

beforeAll(async () => {
  await import("../src/pages/Agent");
}, 60_000);

function workspaceWire(): Record<string, unknown> {
  return {
    agent: { agent_id: "quote-helper", display_name: "Quote Helper", owner_id: "steward-one" },
    tabs: [{ tab: "automations", label: "Automations", purpose: "What this agent runs." }],
    composition: [],
  };
}

function automationWire(extra: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    automation_id: "auto_one",
    name: QUESTIONS,
    runs_as: "u_owner",
    runs_as_name: "Owner Person",
    schedule: "every Monday at 08:00 UTC",
    next_run_at: null,
    paused_because: "Installed and not started yet.",
    last_run: {
      finished_at: "2999-01-01T08:00:00Z",
      outcome: "succeeded",
      reason: null,
      result: ["2 asked in web that crm would have answered"],
    },
    start_confirmation: START_DIGEST,
    start_becomes: "2999-01-07T08:00:00Z",
    stop_confirmation: null,
    cannot_start: null,
    ...extra,
  };
}

function listWire(): Record<string, unknown> {
  return {
    items: [
      automationWire(),
      automationWire({
        automation_id: "auto_summary",
        name: SUMMARY,
        last_run: null,
        start_confirmation: null,
        start_becomes: null,
        cannot_start: "This install cannot perform this outcome yet, so it cannot be started.",
      }),
      automationWire({
        automation_id: "auto_running",
        name: "I check each morning that my sources were refreshed",
        next_run_at: "2999-01-04T07:00:00Z",
        paused_because: null,
        last_run: null,
        start_confirmation: null,
        start_becomes: null,
        stop_confirmation: STOP_DIGEST,
      }),
    ],
    result_rule: "What a run found is shown only to whom it ran as.",
  };
}

type Handler = (body: unknown) => { readonly status?: number; readonly body: unknown };

async function consoleAt(handlers: Record<string, Handler>) {
  const sent: { readonly method: string; readonly path: string; readonly body: unknown }[] = [];
  const idp = fakeIdentityProvider({
    api(url, init) {
      const path = new URL(url, CONSOLE_ORIGIN).pathname;
      const method = (init?.method ?? "GET").toUpperCase();
      const handler = handlers[`${method} ${path}`];
      if (handler === undefined) {
        return null;
      }
      const body: unknown = typeof init?.body === "string" ? JSON.parse(init.body) : null;
      sent.push({ method, path, body });
      const answer = handler(body);
      return new Response(JSON.stringify(answer.body), {
        status: answer.status ?? 200,
        headers: { "content-type": "application/json", "x-trace-id": "trace-automations" },
      });
    },
  });
  const loaded = await loadConsole({ idp });
  await signIn(loaded);
  const { routes } = await import("../src/App");
  const router = createMemoryRouter(routes, { initialEntries: ["/agents/quote-helper/automations"] });
  const { container } = render(<RouterProvider router={router} />);
  await waitFor(() => {
    if (!container.querySelector(`[aria-label="${AUTOMATIONS_LABEL}"] li`)) {
      throw new Error("the list has not arrived");
    }
  });
  return { container, sent };
}

const ANSWERING: Record<string, Handler> = {
  [`GET ${WORKSPACE}`]: () => ({ body: workspaceWire() }),
  [`GET ${GALLERY}`]: () => ({ body: { items: [], installing: "Installing starts it paused." } }),
  [`GET ${LIST}`]: () => ({ body: listWire() }),
};

function button(container: HTMLElement, label: string): HTMLButtonElement | undefined {
  return [...container.querySelectorAll<HTMLButtonElement>("button")].find(
    (one) => one.getAttribute("aria-label") === label,
  );
}

function choice(container: HTMLElement, label: string): HTMLButtonElement {
  const found = [...container.querySelectorAll<HTMLButtonElement>("section.confirm button")].find(
    (one) => one.textContent === label,
  );
  if (!found) {
    throw new Error(`No choice labelled ${label} in an open confirmation.`);
  }
  return found;
}

describe("the installed automations on the Automations tab", () => {
  test("each automation is drawn with what it runs as, when, its last run, and only the controls the API offered", async () => {
    // What breaks if this is deleted: a list that draws a Start the API did not offer, hides why an
    // outcome cannot be started, or drops what the last run found for whom it ran as.
    const { container } = await consoleAt(ANSWERING);
    const items = [...container.querySelectorAll(`[aria-label="${AUTOMATIONS_LABEL}"] > ul > li`)];

    expect(items.map((one) => one.querySelector("h4")?.textContent)).toEqual([
      QUESTIONS,
      SUMMARY,
      "I check each morning that my sources were refreshed",
    ]);
    expect(items[0]?.textContent).toContain("Owner Person");
    expect(items[0]?.textContent).toContain("Installed and not started yet.");
    expect(items[0]?.textContent).toContain("2 asked in web that crm would have answered");
    expect(button(container, `${START_LABEL}: ${QUESTIONS}`)).toBeDefined();
    expect(button(container, `${STOP_LABEL}: ${QUESTIONS}`)).toBeUndefined();
    expect(items[1]?.textContent).toContain("cannot perform this outcome yet");
    expect(button(container, `${START_LABEL}: ${SUMMARY}`)).toBeUndefined();
    expect(
      button(container, `${STOP_LABEL}: I check each morning that my sources were refreshed`),
    ).toBeDefined();
  });

  test("a start writes nothing until the second press, which sends the API's digest and nothing else", async () => {
    // What breaks if this is deleted: a Start that changes the schedule on the first press, or one
    // that sends a digest of its own making, which the route refuses and the screen misreports.
    const stand = await consoleAt({
      ...ANSWERING,
      [`POST ${START}`]: () => ({ body: automationWire({ next_run_at: "2999-01-07T08:00:00Z" }) }),
    });
    const opener = button(stand.container, `${START_LABEL}: ${QUESTIONS}`);
    expect(opener).toBeDefined();
    fireEvent.click(opener as HTMLButtonElement);

    await waitFor(() => {
      if (!stand.container.querySelector("section.confirm")) {
        throw new Error("the confirmation has not opened");
      }
    });
    expect(stand.container.textContent).toContain(startQuestion(QUESTIONS));
    expect(stand.container.textContent).toContain("2999-01-07T08:00:00Z");
    expect(stand.sent.filter((one) => one.method === "POST")).toEqual([]);

    const listsBefore = stand.sent.filter((one) => one.method === "GET" && one.path === LIST).length;
    await act(async () => {
      fireEvent.click(choice(stand.container, START_LABEL));
    });
    await waitFor(() => {
      if (!stand.container.textContent?.includes(STARTED_TITLE)) {
        throw new Error("the start has not been told");
      }
    });
    expect(stand.sent.filter((one) => one.method === "POST")).toEqual([
      { method: "POST", path: START, body: { confirmation: START_DIGEST } },
    ]);
    await waitFor(() => {
      const lists = stand.sent.filter((one) => one.method === "GET" && one.path === LIST).length;
      if (lists <= listsBefore) {
        throw new Error("the list was not asked for again");
      }
    });
  });

  test("leaving the confirmation writes nothing, and a refused change is shown in the API's words", async () => {
    // What breaks if this is deleted: Not now that writes anyway, or a 409 drawn as a generic failure
    // so a person cannot tell a stale confirmation from a broken server.
    const stand = await consoleAt({
      ...ANSWERING,
      [`POST ${START}`]: () => ({
        status: 409,
        body: { outcome: "unconfirmed", sentence: "What you confirmed is not what would change now." },
      }),
    });
    fireEvent.click(button(stand.container, `${START_LABEL}: ${QUESTIONS}`) as HTMLButtonElement);
    await waitFor(() => choice(stand.container, KEEP_LABEL));
    fireEvent.click(choice(stand.container, KEEP_LABEL));
    expect(stand.sent.filter((one) => one.method === "POST")).toEqual([]);

    fireEvent.click(button(stand.container, `${START_LABEL}: ${QUESTIONS}`) as HTMLButtonElement);
    await waitFor(() => choice(stand.container, START_LABEL));
    await act(async () => {
      fireEvent.click(choice(stand.container, START_LABEL));
    });
    await waitFor(() => {
      if (!stand.container.textContent?.includes(NOT_CHANGED)) {
        throw new Error("the refusal has not been told");
      }
    });
    expect(stand.container.textContent).toContain("What you confirmed is not what would change now.");
    expect(stand.container.textContent).not.toContain("Something did not work");
  });

  test("the readers are held to the routes' declared schemas", () => {
    // What breaks if this is deleted: a field renamed in the API reaches a list that silently draws
    // nothing, or a start body that grows a field the route refuses.
    const listed = declaredResponseSchema("/api/v1/agents/{agent_id}/automations", "get");
    const item = declaredProperty(listed, "items");
    // A nullable nested model is declared as `anyOf` the model and null, so the model is the branch
    // that names a reference.
    const nullable = (item["properties"] as Record<string, Record<string, unknown>>)["last_run"];
    const branch = (nullable?.["anyOf"] as readonly Record<string, unknown>[] | undefined)?.find(
      (one) => typeof one["$ref"] === "string",
    );
    const run = resolvedSchema(branch ?? {});
    const asking = declaredRequestBodySchema(
      "/api/v1/agents/{agent_id}/automations/{automation_id}/start",
      "post",
    );

    expect(declaredPropertyNames(listed)).toEqual(Object.keys(listWire()).sort());
    expect(declaredPropertyNames(item)).toEqual(Object.keys(automationWire()).sort());
    expect(declaredPropertyNames(run)).toEqual(
      Object.keys(automationWire()["last_run"] as Record<string, unknown>).sort(),
    );
    expect(declaredPropertyNames(asking)).toEqual(Object.keys(changeBody(START_DIGEST)).sort());
    expect(readAgentAutomations(listWire())?.items).toHaveLength(3);
    expect(readAgentAutomations({ items: [automationWire({ start_confirmation: "nope" })], result_rule: "r" })?.items[0]?.start).toBeUndefined();
    expect(readNotChanged({ outcome: "moved", sentence: "Look again." })).toEqual({
      outcome: "moved",
      sentence: "Look again.",
    });
  });
});
